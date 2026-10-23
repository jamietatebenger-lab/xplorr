# Official mining-tenement data: live query and auditable import

This is read-only forensic research, not access to a certified mineral-title register.
A spatial status of Grant, LIVE or Renew Retained is the source's own field,
not proof of current legal validity or of any unpaid royalty.

## Run Northern Territory government's live WFS query

    python tools/nt_tenement_live_wfs_pull.py --out evidence/nt-20261024
    python tools/nt_tenement_live_wfs_pull.py --titles "ML25978 EL31896 ML23825 ML23868" --out evidence/nt-second-run

Endpoint: https://geology.data.nt.gov.au/geoserver/wfs

WFS layer: mt:MineralTenement.
Queries used: name IN ('ML25978','EL31896',...) and
owner ILIKE '%BENGER%' OR owner ILIKE '%IMPERIAL%'.

The script preserves the exact URL, original response bytes, SHA-256 hash,
server response timestamp, retrieval timestamp, and verbatim fields. Search
matches may be applicants or agents rather than granted holders.

KNOWN MATERIAL CONFLICT: The NTGS final EL31896 surrender report says
cessation on 2 July 2024, whereas an October 2026 NTGS WFS response returned
Grant and Tivan as holder. Status is DISPUTED; obtain a fresh statutory
register extract before describing EL31896 as active.

The WFS title ML25978 returned Application, with John Benger and Robert
Cleaver each as 50% applicants, and Imperial Granite as agent.
This is not a granted mineral lease.

## Parse state portal exports (CSV / JSON / GeoJSON)

    python tools/tenement_dump_audit.py raw/nt.geojson --jurisdiction NT \
      --source-url https://geology.data.nt.gov.au/geoserver/wfs \
      --term Benger --term Imperial --term ML25978 \
      --output evidence/nt-processed

    python tools/tenement_dump_audit.py raw/wa.csv --jurisdiction WA \
      --term "Imperial Granite" --output evidence/wa-processed

    python tools/tenement_dump_audit.py raw/qld-arcgis.json --jurisdiction QLD \
      --term "John Benger" --output evidence/qld-processed

Writes all_records.csv, matches.csv and manifest.json, preserving full
original properties, input-file SHA-256, captured time, literal holder/status,
geographic bounding box when available, and an explicit NOT_VERIFIED statutory
register classification. Never modifies government records.

### WA: official direct ArcGIS mining-tenement layer

Source catalogue: https://catalogue.data.wa.gov.au/en/dataset/mining-tenements-dmirs-003

Layer: https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer/3

Verified layer fields: tenid, fmt_tenid, tenstatus, holder1, holder2,
grantdate, enddate, legal_area. Status values include LIVE and PENDING.

Sample REST query for spatial LIVE records containing an Imperial holder:

    https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer/3/query?where=tenstatus%3D%27LIVE%27%20AND%20holder1%20LIKE%20%27%25IMPERIAL%25%27&outFields=tenid%2Cfmt_tenid%2Ctenstatus%2Cholder1%2Clegal_area%2Cgrantdate%2Cenddate&returnGeometry=false&f=json

Verify record availability and query permissions. Check all holder slots.
Paginate if the number of matching records exceeds the service page limit;
never assume one API page is a complete inventory.

TENGRAPH spatial data is not identical to Mineral Titles Online (MTO).
Some exports require SLIP credentials or payment: do not bypass access.

### NSW and Queensland

NSW dataset: https://www.planningportal.nsw.gov.au/opendata/dataset/nsw-mining-titles
Use a government-supplied CSV/WFS export with the actual schema and timestamp.

Queensland Resource Authorities FeatureServer:
https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Economy/CurrentQldResourceAuthorities/FeatureServer

Query the actual layer metadata before supplying a numeric layer ID, field
names, or WHERE filter. Layer IDs and fields are not universal.

## Authentication and regulatory guardrails

1. Preserve originals downloaded from official government endpoints.
2. Record authoritative URL, retrieval timestamp, byte length, SHA-256,
   source publication/dataset version and update date when available.
3. Check completeness via record counts, pagination, and omitted holder slots.
4. Preserve raw status values; applicant or agent does not equal owner.
5. Resolve conflicts with later dealings and CURRENT STATUTORY REGISTER.
6. Never infer unpaid personal royalties, consideration, debt or claim validity
   from a cadastral polygon or technical report alone.
7. For ASX and issuer PDFs, match publisher announcement entry, ACN and
   independently retrieved original. A checksum against an internal manifest
   is not publisher authentication.

Offline tests:

    python -m unittest discover -s tools -p 'test_tenement_dump_audit.py' -v

No official registers are modified. Testing does not require network access.
