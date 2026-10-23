"""Reproducible offline checks; government-shaped fixture is synthetic."""
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from deterministic_tenement_validation import (
    valid_abn, valid_acn, title_id, title_format, name_key,
    role_records, source_records, check
)


class IdentifierChecks(unittest.TestCase):
    def test_abr_modulus_89(self):
        self.assertTrue(valid_abn("51 824 753 556"))
        self.assertFalse(valid_abn("51 824 753 557"))
        self.assertFalse(valid_abn("51 824 753 55x"))
        self.assertFalse(valid_abn("00000000000"))

    def test_asic_modulus_10(self):
        self.assertTrue(valid_acn("004 085 616"))
        self.assertTrue(valid_acn("080 314 012"))
        self.assertFalse(valid_acn("004 085 617"))
        self.assertFalse(valid_acn("080 314 0120"))

    def test_title_identifiers(self):
        self.assertEqual(title_id(" EL 31896 "), "EL31896")
        self.assertTrue(title_format("ML25978", "NT"))
        self.assertTrue(title_format("E70/0025", "WA"))
        self.assertFalse(title_format("ML25978x", "NT"))
        self.assertFalse(title_format("E70/25", "NT"))

    def test_corporate_names_not_conflated(self):
        self.assertEqual(name_key("Imperial Granite & Minerals Pty Ltd"),
                         name_key("Imperial Granite AND Minerals Pty Ltd"))
        self.assertNotEqual(name_key("Imperial Granite Pty Ltd"),
                            name_key("Imperial Granite & Minerals Pty Ltd"))

    def test_explicit_role_extraction(self):
        s = ("Applicant - John BENGER (50%),\n"
             "Applicant - Robert CLEAVER (50%),\n"
             "Agent - IMPERIAL GRANITE & MINERALS PTY LTD")
        self.assertEqual(
            role_records(s),
            [("APPLICANT", "JOHN BENGER"), ("APPLICANT", "ROBERT CLEAVER"),
             ("AGENT", "IMPERIAL GRANITE AND MINERALS PTY LTD")]
        )


class CrossReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {
                    "name": "ML25978", "status": "Application",
                    "owner": ("Applicant - John BENGER (50%),\n"
                              "Applicant - Robert CLEAVER (50%),\n"
                              "Agent - IMPERIAL GRANITE & MINERALS PTY LTD")}},
                {"type": "Feature", "properties": {
                    "name": "ML23825", "status": "Grant",
                    "owner": "Holder - MOLYHIL MINING PTY LTD (100%)"}},
                {"type": "Feature", "properties": {
                    "name": "EL31896", "status": "Grant",
                    "owner": "Holder - TIVAN LIMITED (100%)"}},
            ],
        }

    def make_file(self, root):
        path = Path(root) / "synthetic_nt_wfs.geojson"
        path.write_text(json.dumps(self.fixture), encoding="utf-8")
        return path

    def test_correct_applicant_role(self):
        with TemporaryDirectory() as root:
            path = self.make_file(root)
            claims = [{"title_id": "ML25978", "holder": "John Benger",
                       "role": "Applicant", "status": "Application"}]
            result = check(path, claims, "NT")
            self.assertEqual(result["checks"][0]["result"], "MATCHES_PROVIDED_DATA")
            self.assertFalse(result["register_certified"])

    def test_reject_false_holder_and_grant(self):
        with TemporaryDirectory() as root:
            path = self.make_file(root)
            claims = [{"title_id": "ML25978", "holder": "John Benger",
                       "role": "Holder", "status": "Grant"}]
            checked = check(path, claims, "NT")["checks"][0]
            self.assertEqual(checked["result"], "CHECK_FAILED")
            self.assertIn("ROLE_MISMATCH", checked["errors"])
            self.assertIn("STATUS_MISMATCH", checked["errors"])

    def test_el31896_dispute(self):
        with TemporaryDirectory() as root:
            path = self.make_file(root)
            checked = check(path, [
                {"title_id": "EL31896", "holder": "TIVAN LIMITED",
                 "role": "Holder", "status": "Grant"}
            ], "NT")["checks"][0]
            self.assertEqual(checked["result"], "SOURCE_CONFLICT")
            self.assertIn("KNOWN_CONFLICT_2024_EL31896_CESSATION", checked["errors"])

    def test_missing_record_is_scoped_to_input(self):
        with TemporaryDirectory() as root:
            path = self.make_file(root)
            checked = check(path, [{"title_id": "ML99999"}], "NT")["checks"][0]
            self.assertEqual(checked["result"], "NOT_IN_PROVIDED_DATA")

    def test_conflicting_duplicate_rows(self):
        with TemporaryDirectory() as root:
            self.fixture["features"].append({
                "type": "Feature", "properties": {
                    "name": "ML25978", "status": "Grant",
                    "owner": "Holder - Different Company (100%)"}})
            path = self.make_file(root)
            checked = check(path, [{"title_id": "ML25978"}], "NT")["checks"][0]
            self.assertEqual(checked["result"], "SOURCE_CONFLICT")
            self.assertIn("INCONSISTENT_SOURCE_DUPLICATES", checked["errors"])

    def test_sha256_compare_does_not_authenticate_source(self):
        with TemporaryDirectory() as root:
            path = self.make_file(root)
            good = hashlib.sha256(path.read_bytes()).hexdigest()
            report = check(path, [{"title_id": "ML23825"}], "NT", good)
            self.assertEqual(report["source"]["sha256"], good)
            self.assertEqual(report["source"]["type"],
                             "PROVIDED_BYTES_ORIGIN_NOT_INDEPENDENTLY_VERIFIED")
            with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
                check(path, [], "NT", "0" * 64)

    def test_analyst_snapshot_never_original(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "analyst.json"
            path.write_text(json.dumps({"items": [{
                "title_id": "ML25978", "wfs_status": "Application",
                "parties": "Applicant - John Benger"}]}), encoding="utf-8")
            rows, meta = source_records(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(meta["type"], "ANALYST_TRANSCRIPTION_NOT_ORIGINAL")


if __name__ == "__main__":
    unittest.main()
