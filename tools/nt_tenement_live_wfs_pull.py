#!/usr/bin/env python3
"""Read-only query of NT Geological Survey's original mineral-tenement WFS.

Returns SOURCE RECORDS, not certified legal-status determinations.
The endpoint may serve stale data. In particular verify EL31896 against the
2024 NTGS surrender report and the current statutory register.

Example:
    python tools/nt_tenement_live_wfs_pull.py --out evidence/nt-20261024
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICE = "https://geology.data.nt.gov.au/geoserver/wfs"
DEFAULT_TITLES = "ML25978 EL31896 ML23868 ML23686 ML23825 ML30184 EL22349 EL23186 EL30131 EL28026 EL27821"
MAX_BYTES = 16 * 1024 * 1024


def safe_title(s):
    value = s.strip().upper().replace(" ", "")
    if not re.fullmatch(r"[A-Z]{1,5}\d{2,7}", value):
        raise ValueError("Invalid tenement identifier: " + repr(s))
    return value


def fetch(cql, outdir, tag, timeout=30):
    """Pin the HTTPS host and preserve exact original response bytes."""
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "mt:MineralTenement", "outputFormat": "application/json",
        "count": "500", "cql_filter": cql
    }
    url = SERVICE + "?" + urlencode(params)
    query_at = datetime.now(timezone.utc).isoformat()
    request = Request(url, headers={
        "User-Agent": "MineralTitleEvidence/1.0 (read only)",
        "Accept": "application/json"
    })
    with urlopen(request, timeout=timeout) as response:
        if not response.url.startswith(SERVICE + "?"):
            raise RuntimeError("Unexpected redirect away from official NTGS endpoint")
        body = response.read(MAX_BYTES + 1)
        content_type = response.headers.get("Content-Type", "")
        http_status = response.status
    if len(body) > MAX_BYTES:
        raise RuntimeError("Government response exceeds safe size limit")
    data = json.loads(body)
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise RuntimeError("Official WFS did not return a GeoJSON FeatureCollection")
    matched = data.get("numberMatched")
    returned = data.get("numberReturned", len(data["features"]))
    if isinstance(matched, int) and isinstance(returned, int) and matched > returned:
        raise RuntimeError("WFS truncated results; do not claim complete inventory")
    raw_path = outdir / (tag + ".original_response.geojson")
    raw_path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    rows = []
    for feature in data["features"]:
        prop = feature.get("properties") or {}
        title = prop.get("name") or prop.get("fileID") or ""
        rows.append({
            "tenement_id": title, "wfs_status_verbatim": prop.get("status") or "",
            "holder_or_applicant_verbatim": prop.get("owner") or "",
            "area_verbatim": prop.get("area") or "",
            "source_feature_id": feature.get("id") or "",
            "source_data_timestamp_utc": data.get("timeStamp") or "",
            "request_timestamp_utc": query_at,
            "certified_statutory_register_status": "NOT_VERIFIED",
            "caveat": (
                "CONFLICT: WFS Grant versus NTGS July 2024 cessation report; ask registrar"
                if title == "EL31896" else
                "Public WFS is not the statutory mining-title register"
            )
        })
    fieldnames = list(rows[0]) if rows else [
        "tenement_id", "wfs_status_verbatim", "holder_or_applicant_verbatim",
        "area_verbatim", "source_feature_id", "source_data_timestamp_utc",
        "request_timestamp_utc", "certified_statutory_register_status", "caveat"
    ]
    with (outdir / (tag + ".evidence_rows.csv")).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "source_url": url, "queried_at_utc": query_at,
        "response_timestamp_utc": data.get("timeStamp"),
        "numberMatched": matched, "numberReturned": returned,
        "http_status": http_status, "content_type": content_type,
        "raw_response_sha256": digest, "raw_response_bytes": len(body),
        "raw_response_path": raw_path.name,
        "evidence_csv": tag + ".evidence_rows.csv",
        "record_count": len(rows)
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--titles", default=DEFAULT_TITLES, help="Space-separated IDs; accepts only NT title syntax")
    p.add_argument("--out", required=True, help="NEW folder for raw response and audit evidence")
    p.add_argument("--timeout", type=int, default=30)
    a = p.parse_args()
    folder = Path(a.out)
    folder.mkdir(parents=True, exist_ok=False)
    titles = sorted({safe_title(t) for t in a.titles.split()})
    if not titles:
        raise ValueError("At least one title required")
    cql_titles = "name IN (" + ",".join("'" + x + "'" for x in titles) + ")"
    queries = [
        ("titles", cql_titles),
        ("holder_match", "owner ILIKE '%BENGER%' OR owner ILIKE '%IMPERIAL%'")
    ]
    completed = []
    for tag, cql in queries:
        result = fetch(cql, folder, tag, a.timeout)
        completed.append(result)
        print(tag, result["record_count"], "source timestamp:", result["response_timestamp_utc"])
    manifest = {
        "provider": "Northern Territory Geological Survey (NT Government)",
        "source": SERVICE,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "Not a certified statutory register. A WFS response timestamp is not proof of source freshness. This tool cannot prove unpaid royalties, ownership rights or debts.",
        "known_conflict": "EL31896 reportedly ceased 2024-07-02 in NTGS 2024 surrender report despite a WFS Grant response.",
        "queries": completed
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Saved original official responses, SHA-256 fingerprints, CSV and manifest to", folder)


if __name__ == "__main__":
    main()
