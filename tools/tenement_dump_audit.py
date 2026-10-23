#!/usr/bin/env python3
"""Read-only evidence importer for official mineral-title CSV, GeoJSON and ArcGIS JSON.

Never infers legal title validity, ownership, or payment rights from spatial data.
Keep downloaded originals separately. This program does not access registries or edit them.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

TITLE_KEYS = ('tenement_id', 'title_id', 'title_number', 'title_no', 'tenement_number',
              'tenement_no', 'tenement', 'fileID', 'file_id', 'permit_number',
              'permit_no', 'authority_number', 'name', 'fmt_tenid', 'tenid')
HOLDER_KEYS = ('owner', 'holder', 'holder_name', 'registered_holder', 'title_holder',
               'tenement_holder', 'applicant', 'applicant_name', 'holders', 'holder1')
STATUS_KEYS = ('status', 'title_status', 'tenement_status', 'tenure_status', 'ten_status', 'tenstatus')
AREA_KEYS = ('area', 'area_ha', 'area_km2', 'blocks', 'hectares')
TITLE_RE = re.compile(r'^[A-Z]{1,8}[\s/.-]*\d{1,9}(?:[/-]\d+)?$', re.I)


def field(props: dict, keys) -> str:
    normalized = {re.sub(r'[^a-z0-9]', '', str(k).lower()): v for k, v in props.items()}
    for key in keys:
        value = normalized.get(re.sub(r'[^a-z0-9]', '', key.lower()))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def validate_title(value: str) -> str:
    value = value.strip().upper()
    return value if TITLE_RE.fullmatch(value) else ''


def positions(geometry):
    """Extract coordinate pairs only for explicitly geographic GeoJSON features."""
    if not isinstance(geometry, dict) or 'coordinates' not in geometry:
        return []
    coords = []
    def visit(n):
        if isinstance(n, (list, tuple)) and len(n) >= 2 and all(isinstance(z, (float, int)) for z in n[:2]):
            coords.append((n[0], n[1]))
        elif isinstance(n, (list, tuple)):
            for c in n:
                visit(c)
    visit(geometry['coordinates'])
    return coords


def read_rows(path: Path):
    if path.suffix.lower() == '.csv':
        with path.open('r', newline='', encoding='utf-8-sig') as f:
            yield from ((dict(r), None, 'csv') for r in csv.DictReader(f))
    elif path.suffix.lower() in ('.json', '.geojson'):
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(obj, dict) and obj.get('type') == 'FeatureCollection':
            for f in obj.get('features', []):
                yield (f.get('properties') or {}, f.get('geometry'), 'geojson')
        elif isinstance(obj, dict) and isinstance(obj.get('features'), list):
            for f in obj['features']:
                # ArcGIS REST feature properties are attributes, not properties.
                yield (f.get('attributes') or f.get('properties') or {}, None, 'arcgis_json')
        elif isinstance(obj, list):
            for item in obj:
                yield (item, None, 'json_array')
        elif isinstance(obj, dict) and isinstance(obj.get('items'), list):
            # Historic analyst-transcribed snapshots are NOT original government dumps.
            for item in obj['items']:
                yield (item, None, 'analyst_snapshot')
        else:
            raise ValueError('Unsupported JSON schema; expected GeoJSON, ArcGIS features, array or analyst snapshot')
    else:
        raise ValueError('Supported inputs: .csv, .json, .geojson (export zipped GIS data first)')


def normalize(props: dict, geometry, jurisdiction: str, source_sha: str, source_name: str, source_url: str, captured: str, fmt: str, row_number: int):
    title = validate_title(field(props, TITLE_KEYS))
    # Analyst snapshots require explicit separate column names.
    if fmt == 'analyst_snapshot':
        title = validate_title(str(props.get('title_id', '')))
        holder = str(props.get('parties', ''))
        status = str(props.get('wfs_status', ''))
        area = str(props.get('reported_area', ''))
    else:
        holder = field(props, HOLDER_KEYS)
        status = field(props, STATUS_KEYS)
        area = field(props, AREA_KEYS)
    pts = positions(geometry) if fmt == 'geojson' else []
    bbox = [min(z[0] for z in pts), min(z[1] for z in pts), max(z[0] for z in pts), max(z[1] for z in pts)] if pts else None
    warnings = []
    if not title:
        warnings.append('title_id_not_identified; inspect original fields')
    if not holder:
        warnings.append('holder_not_identified; inspect original fields')
    if jurisdiction == 'NT' and title == 'EL31896' and status.strip().lower() == 'grant':
        warnings.append('CONFLICT: NTGS 2024 final surrender report records cessation 2024-07-02; verify current registrar')
    if fmt == 'analyst_snapshot':
        warnings.append('ANALYST_TRANSCRIPTION_NOT_RAW_GOVERNMENT_DATA')
    return {
        'jurisdiction': jurisdiction,
        'tenement_id': title,
        'holder_or_applicant_verbatim': holder,
        'status_verbatim': status,
        'area_verbatim': area,
        'geojson_bbox_lon_lat': json.dumps(bbox, separators=(',', ':')) if bbox else '',
        'current_certified_register_status': 'NOT_VERIFIED',
        'source_file': source_name,
        'source_row': row_number,
        'source_sha256': source_sha,
        'source_url_provided': source_url,
        'import_timestamp_utc': captured,
        'input_format': fmt,
        'caveats': '; '.join(warnings),
        'raw_properties_json': json.dumps(props, ensure_ascii=False, sort_keys=True, default=str),
    }


def export(inputs, output: Path, jurisdiction: str, source_url: str, terms: list[str]):
    output.mkdir(parents=True, exist_ok=True)
    captured = datetime.now(timezone.utc).isoformat()
    data = []
    source_manifest = []
    for infile in inputs:
        path = Path(infile)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        num = 0
        for num, (props, geom, fmt) in enumerate(read_rows(path), 1):
            data.append(normalize(props, geom, jurisdiction, digest, path.name, source_url, captured, fmt, num))
        source_manifest.append({'file': path.name, 'sha256': digest, 'bytes': path.stat().st_size,
                                'records_read': num, 'source_url_supplied_not_independently_verified': source_url})
    termlist = [t.casefold().strip() for t in terms if t.strip()]
    matched = [r for r in data if any(t in (r['tenement_id']+' '+r['holder_or_applicant_verbatim']).casefold() for t in termlist)] if termlist else data
    fields = list(normalize({}, None, jurisdiction, '', '', '', '', '', 0))
    for filename, rows in [('all_records.csv', data), ('matches.csv', matched)]:
        with (output/filename).open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    manifest = {
        'import_timestamp_utc': captured,
        'jurisdiction': jurisdiction,
        'source_files': source_manifest,
        'records_total': len(data),
        'records_matched': len(matched),
        'matching_terms': terms,
        'warning': 'This import is not registry authentication. Original publisher, dataset age and statutory status require separate verification. Government spatial data cannot establish unpaid royalties or personal debts.',
        'output': ['all_records.csv', 'matches.csv'],
    }
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('files', nargs='+', help='Original government CSV/GeoJSON/ArcGIS JSON export files')
    p.add_argument('--jurisdiction', required=True, choices=('NT','WA','NSW','QLD','SA','VIC','TAS'))
    p.add_argument('--source-url', default='', help='Exact government download URL, if known')
    p.add_argument('--term', action='append', default=[], help='Case-insensitive title/holder filter; repeatable')
    p.add_argument('--output', default='tenement_evidence')
    args = p.parse_args()
    manifest = export(args.files, Path(args.output), args.jurisdiction, args.source_url, args.term)
    print(json.dumps({k: manifest[k] for k in ('records_total', 'records_matched', 'output')}, indent=2))


if __name__ == '__main__':
    main()
