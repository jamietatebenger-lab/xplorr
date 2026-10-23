"""Offline verification tests for read-only government mining-title imports."""
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tenement_dump_audit import export, normalize
from nt_tenement_live_wfs_pull import safe_title, fetch


def first_csv(path):
    with path.open("r", encoding="utf-8", newline="") as stream:
        return next(csv.DictReader(stream))


class ImportTests(unittest.TestCase):
    def test_nt_geojson_and_raw_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); path = base / "nt.geojson"
            path.write_text(json.dumps({"type":"FeatureCollection","features":[{
                "type":"Feature",
                "properties":{"name":"ML25978","status":"Application",
                    "owner":"Applicant - John BENGER (50%), Agent - IMPERIAL GRANITE",
                    "area":"270 Hectares"},
                "geometry":{"type":"Polygon","coordinates":[[
                    [133.9,-23.9],[133.91,-23.9],[133.91,-23.88],[133.9,-23.9]]]}}]}))
            m = export([path],base / "out","NT","https://geology.data.nt.gov.au/geoserver/wfs",["benger"])
            self.assertEqual(m["records_total"],1)
            self.assertEqual(m["records_matched"],1)
            row = first_csv(base / "out" / "matches.csv")
            self.assertEqual(row["tenement_id"],"ML25978")
            self.assertEqual(row["status_verbatim"],"Application")
            self.assertEqual(row["current_certified_register_status"],"NOT_VERIFIED")
            self.assertEqual(len(row["source_sha256"]),64)
            self.assertIn("133.9",row["geojson_bbox_lon_lat"])

    def test_wa_csv_field_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp); p=b/"wa.csv"
            p.write_text("FMT_TENID,HOLDER1,TENSTATUS,Extra Note\nE 70/25,IMPERIAL GRANITE,Pending,RETAIN\n")
            export([p],b/"out","WA","",["imperial"])
            row=first_csv(b/"out"/"matches.csv")
            self.assertEqual(row["tenement_id"],"E 70/25")
            self.assertEqual(row["status_verbatim"],"Pending")
            self.assertIn("RETAIN",row["raw_properties_json"])

    def test_arcgis_attributes(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);p=b/"qld.json"
            p.write_text(json.dumps({"features":[{"attributes":{
                "permit_number":"EPM12345","holder":"Example Company",
                "status":"Granted"}}]}))
            export([p],b/"out","QLD","",["EPM12345"])
            row=first_csv(b/"out"/"matches.csv")
            self.assertEqual(row["tenement_id"],"EPM12345")
            self.assertEqual(row["input_format"],"arcgis_json")
            self.assertEqual(row["current_certified_register_status"],"NOT_VERIFIED")

    def test_el31896_conflict(self):
        row=normalize({"name":"EL31896","status":"Grant","owner":"TIVAN"},None,
                      "NT","hash","name","","2026-10-24","geojson",1)
        self.assertIn("CONFLICT:",row["caveats"])

    def test_analyst_snapshot_not_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);p=b/"analyst.json"
            p.write_text(json.dumps({"items":[{
                "title_id":"ML25978","wfs_status":"Application",
                "parties":"Applicant - John BENGER"}]}))
            export([p],b/"out","NT","",["BENGER"])
            row=first_csv(b/"out"/"matches.csv")
            self.assertIn("ANALYST_TRANSCRIPTION",row["caveats"])

    def test_nt_live_title_guard(self):
        self.assertEqual(safe_title(" ML25978 "),"ML25978")
        with self.assertRaises(ValueError): safe_title("ML25978' OR 1=1")

    def test_nt_live_preserves_response_bytes(self):
        class FakeResponse:
            status=200
            url="https://geology.data.nt.gov.au/geoserver/wfs?service=WFS"
            headers={"Content-Type":"application/json"}
            def __init__(self,data): self.data=data
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return self.data
        payload=json.dumps({
            "type":"FeatureCollection","numberMatched":1,"numberReturned":1,
            "timeStamp":"2026-10-23T16:56:18Z",
            "features":[{"id":"mt.feature.1","properties":{
                "name":"ML25978","status":"Application","owner":"Applicant - Benger"}}]
        }).encode()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch("nt_tenement_live_wfs_pull.urlopen",return_value=FakeResponse(payload)):
                result=fetch("name IN ('ML25978')",base,"sample")
            self.assertEqual((base/"sample.original_response.geojson").read_bytes(),payload)
            self.assertEqual(result["numberMatched"],1)
            self.assertEqual(len(result["raw_response_sha256"]),64)
            self.assertEqual(first_csv(base/"sample.evidence_rows.csv")["certified_statutory_register_status"],"NOT_VERIFIED")

    def test_nt_live_rejects_truncated_results(self):
        class FakeResponse:
            status=200
            url="https://geology.data.nt.gov.au/geoserver/wfs?test=1"
            headers={}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return json.dumps({"type":"FeatureCollection","numberMatched":5,"numberReturned":0,"features":[]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("nt_tenement_live_wfs_pull.urlopen",return_value=FakeResponse()):
                with self.assertRaisesRegex(RuntimeError,"truncated"):
                    fetch("owner ILIKE '%BENGER%'",Path(tmp),"partial")


if __name__=="__main__":
    unittest.main()
