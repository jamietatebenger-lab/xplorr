#!/usr/bin/env python3
"""Deterministic evidence comparisons: ABN, ACN, tenure ID, party role, source hash.

Reads government-style CSV/GeoJSON/ArcGIS JSON already downloaded locally.
Only attests AGREEMENT WITH PROVIDED DATA. Not statutory-register certification.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tenement_dump_audit import read_rows, field

ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
ACN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 1)
# Patterns are a documented SUBSET of historically used state title grammars.
TITLE_FORMATS = {
    "NT": r"(?:EL|ML|ELR|MLA|ELA|EMEL|EML|MC|MCA)[0-9]{2,7}",
    "WA": r"(?:E|M|L|P|G|R)[0-9]{1,3}/[0-9]{1,7}",
    "QLD": r"(?:EPM|MDL|ML|EPC|EPQ)[0-9]{1,8}",
    "NSW": r"(?:EL|ML|MPL|PPL|AUTH)[0-9]{1,8}",
    "SA": r"(?:EL|ML|RL|PL)[0-9]{1,8}",
    "VIC": r"(?:EL|MIN|RL|PL)[0-9]{1,8}",
    "TAS": r"(?:EL|ML|RL)[0-9]{1,8}(?:/[0-9]{2})?",
}
IDS = ("tenement_id", "title_id", "name", "fmt_tenid", "tenid",
       "permit_number", "authority_number", "fileID")
OWNERS = ("owner", "holder", "holder1", "registered_holder", "title_holder", "parties")
STATUSES = ("status", "wfs_status", "tenstatus", "tenure_status", "title_status")
PARTIES = re.compile(r"(?:^|,|\n)\s*(Holder|Applicant|Agent)\s*[-:]\s*", re.I)


def number(s):
    if not isinstance(s, str) or not re.fullmatch(r"[0-9\s-]+", s, re.ASCII):
        return ""
    return re.sub(r"[\s-]", "", s)


def valid_abn(s):
    s = number(s)
    return len(s) == 11 and s[0] != "0" and sum(
        (int(c)-(i == 0))*w for i, (c, w) in enumerate(zip(s, ABN_WEIGHTS))
    ) % 89 == 0


def valid_acn(s):
    s = number(s)
    return len(s) == 9 and (10-sum(int(c)*w for c, w in zip(s[:8], ACN_WEIGHTS)) % 10) % 10 == int(s[8])


def title_id(s):
    return re.sub(r"\s+", "", str(s or "")).upper()


def title_format(s, state):
    return bool(re.fullmatch(TITLE_FORMATS[state], title_id(s), re.ASCII))


def name_key(s):
    # Equality only; &/AND and trivial presentation differences can be equal.
    # No fuzzy name aliases, no removal of Pty/Ltd, no surname-only matching.
    return " ".join(re.findall(r"[A-Z0-9]+", str(s or "").upper().replace("&", " AND ")))


def role_records(s):
    m = list(PARTIES.finditer(s or ""))
    result = []
    for i, x in enumerate(m):
        end = m[i+1].start() if i+1 < len(m) else len(s)
        n = s[x.end():end].strip(" ,\n\r")
        n = re.sub(r"\s*\(\s*[0-9.]+\s*%\s*\)\s*$", "", n)
        if n:
            result.append((x.group(1).upper(), name_key(n)))
    return result


def source_records(path):
    b = path.read_bytes()
    rows = []
    types = set()
    for props, _geometry, kind in read_rows(path):
        types.add(kind)
        row = {
            "title_id": title_id(field(props, IDS)),
            "owner": field(props, OWNERS),
            "status": field(props, STATUSES),
            "abn": field(props, ("abn",)),
            "acn": field(props, ("acn",)),
        }
        rows.append(row)
    return rows, {
        "filename": path.name, "size": len(b),
        "sha256": hashlib.sha256(b).hexdigest(),
        "record_count": len(rows),
        "type": "ANALYST_TRANSCRIPTION_NOT_ORIGINAL" if "analyst_snapshot" in types
                else "PROVIDED_BYTES_ORIGIN_NOT_INDEPENDENTLY_VERIFIED",
    }


def validate_claim(claim, index, state):
    tid = title_id(field(claim, IDS))
    errors = []
    if not tid:
        return {"title_id": tid, "result": "INVALID_CLAIM", "errors": ["MISSING_ID"]}
    if not title_format(tid, state):
        errors.append("UNKNOWN_TITLE_SYNTAX")
    sources = index.get(tid, [])
    if not sources:
        return {"title_id": tid, "result": "NOT_IN_PROVIDED_DATA",
                "errors": errors, "register_certified": False}
    distinct = {(name_key(v["owner"]), name_key(v["status"])) for v in sources}
    if len(distinct) > 1:
        errors.append("INCONSISTENT_SOURCE_DUPLICATES")
    record = sources[0]
    expected_status = field(claim, STATUSES)
    if expected_status and name_key(expected_status) != name_key(record["status"]):
        errors.append("STATUS_MISMATCH")
    claimant = field(claim, ("holder", "applicant", "owner", "company", "party"))
    claimed_role = field(claim, ("role", "party_role"))
    if claimant:
        roles = role_records(record["owner"])
        if roles:
            matching = [r for r, n in roles if n == name_key(claimant)]
            if not matching:
                errors.append("PARTY_NOT_EXACT")
            elif claimed_role and name_key(claimed_role) not in matching:
                errors.append("ROLE_MISMATCH")
            elif not claimed_role:
                errors.append("CLAIM_ROLE_UNSPECIFIED")
        elif name_key(claimant) != name_key(record["owner"]):
            errors.append("PARTY_NOT_EXACT")
        elif claimed_role:
            errors.append("SOURCE_HAS_NO_ROLE_LABEL")
    for label, validate in (("abn", valid_abn), ("acn", valid_acn)):
        supplied = field(claim, (label,))
        if supplied:
            if not validate(supplied):
                errors.append(label.upper()+"_CHECKSUM_INVALID")
            if not record[label]:
                errors.append(label.upper()+"_NOT_PRESENT_IN_SOURCE")
            elif number(supplied) != number(record[label]):
                errors.append(label.upper()+"_VALUE_MISMATCH")
    if state == "NT" and tid == "EL31896" and name_key(record["status"]) == "GRANT":
        errors.append("KNOWN_CONFLICT_2024_EL31896_CESSATION")
    blocking = [e for e in errors if e != "CLAIM_ROLE_UNSPECIFIED"]
    return {"title_id": tid, "result":
            "SOURCE_CONFLICT" if any(e.startswith(("INCONSISTENT_SOURCE", "KNOWN_CONFLICT")) for e in blocking)
            else "CHECK_FAILED" if blocking else "MATCHES_PROVIDED_DATA",
            "errors": errors, "source_status": record["status"],
            "source_owner": record["owner"], "register_certified": False}


def check(source, claims, state, expected_sha256=None):
    rows, meta = source_records(source)
    if expected_sha256 and meta["sha256"].lower() != expected_sha256.lower():
        raise ValueError("SOURCE_SHA256_MISMATCH")
    index = defaultdict(list)
    for row in rows:
        if row["title_id"]:
            index[row["title_id"]].append(row)
    return {
        "ran_utc": datetime.now(timezone.utc).isoformat(),
        "jurisdiction": state, "source": meta, "register_certified": False,
        "checks": [validate_claim(c, index, state) for c in claims],
        "limitations": "Only checks bytes and source-field equality. Does not authenticate a publisher, determine live legal tenure, verify company registration, or prove private royalties/debts.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--claims", required=True, type=Path, help="JSON array of assertions")
    p.add_argument("--state", required=True, choices=sorted(TITLE_FORMATS))
    p.add_argument("--expected-sha256", help="A separately obtained authoritative checksum")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    claims = json.loads(args.claims.read_text(encoding="utf-8"))
    if not isinstance(claims, list) or not all(isinstance(c, dict) for c in claims):
        raise ValueError("Claims must be an array of objects")
    if args.expected_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256):
        raise ValueError("Expected SHA-256 must be 64 hexadecimal digits")
    result = check(args.source, claims, args.state, args.expected_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"source": result["source"], "checks": result["checks"]}, indent=2))


if __name__ == "__main__":
    main()
