"""Official catalogue URL templates used by the map (keep in sync with app.js).

Prefer actual harvested links. Generate a catalogue URL from an identifier
only when that identifier matches the expected state-specific format.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

WAMEX_DETAILS = "https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber="
DIGS_REPORT = "https://search.geoscience.nsw.gov.au/report/"
DIGS_SEARCH = "https://search.geoscience.nsw.gov.au/search?query="
GSQ_DATASET = "https://geoscience.data.qld.gov.au/data/dataset/"
GSQ_REPORT = "https://geoscience.data.qld.gov.au/data/report/"

PORTAL_HOMES = {
    "nsw": {"https://search.geoscience.nsw.gov.au", "https://search.geoscience.nsw.gov.au/"},
    "qld": {"https://geoscience.data.qld.gov.au", "https://geoscience.data.qld.gov.au/"},
    "wa": {"https://wamex.dmp.wa.gov.au/Wamex", "https://wamex.dmp.wa.gov.au/Wamex/"},
}


def _norm(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def is_portal_home(url: str, state: str) -> bool:
    homes = {_norm(h) for h in PORTAL_HOMES.get(state, ())}
    return _norm(url) in homes


def _is_http_url(value: str) -> bool:
    """Reject malformed URLs and pseudo-schemes such as httpx: or javascript:."""
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def report_href(rec: dict) -> str:
    st = str(rec.get("st") or rec.get("jurisdiction") or rec.get("state") or "").strip().lower()
    raw = str(rec.get("u") or rec.get("url") or rec.get("href") or "").strip()

    if st == "wa":
        a = str(rec.get("a") or "").strip()
        # WA catalogue A-numbers must be decimal, never arbitrary source text.
        # Avoid ValueError for malformed or huge int(...) inputs.
        if re.fullmatch(r"[0-9]{1,12}", a):
            return WAMEX_DETAILS + quote(a.lstrip("0") or "0", safe="")
        if _is_http_url(raw) and not is_portal_home(raw, "wa"):
            return raw
        return ""

    if st == "nsw":
        m = re.search(r"search\\.geoscience\\.nsw\\.gov\\.au/report/([^/?#]+)", raw, re.I)
        if m:
            return DIGS_REPORT + quote(m.group(1), safe="")
        if _is_http_url(raw) and not is_portal_home(raw, "nsw"):
            return raw
        title = str(rec.get("t") or "").strip()
        if title:
            return DIGS_SEARCH + quote(title[:180], safe="")
        return ""

    if st == "qld":
        m = re.search(r"geoscience\\.data\\.qld\\.gov\\.au/(?:data/)?(?:dataset|report)/([^/?#]+)", raw, re.I)
        if m:
            rid = m.group(1)
            if re.fullmatch(r"cr[0-9]+", rid, re.I):
                return GSQ_REPORT + quote(rid, safe="")
            return GSQ_DATASET + quote(rid, safe="")
        # Preserve specific harvested links rather than overwriting them
        # with a fabricated catalogue address based on an internal row ID.
        if _is_http_url(raw) and not is_portal_home(raw, "qld"):
            return raw
        rid = str(rec.get("id") or "").strip()
        if re.fullmatch(r"cr[0-9]+", rid, re.I):
            return GSQ_REPORT + quote(rid, safe="")
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", rid, re.I):
            return GSQ_DATASET + quote(rid, safe="")
        return ""

    if _is_http_url(raw) and not is_portal_home(raw, st):
        return raw
    return ""
