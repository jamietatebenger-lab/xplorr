"""Offline regression tests for official catalogue URL construction."""

import unittest

from report_urls import report_href


class ReportHrefTests(unittest.TestCase):
    def test_wa_numeric_a_number(self):
        self.assertEqual(
            report_href({"st": "wa", "a": "00120783", "u": "https://wamex.dmp.wa.gov.au/Wamex"}),
            "https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=120783",
        )

    def test_wa_malformed_id_is_never_fabricated(self):
        self.assertEqual(report_href({"st": "wa", "a": "A120783"}), "")
        self.assertEqual(report_href({"st": "wa", "a": "9" * 5000}), "")
        source = "https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=1234"
        self.assertEqual(report_href({"st": "wa", "a": "bad", "u": source}), source)

    def test_wa_home_without_identifier(self):
        self.assertEqual(report_href({"st": "wa", "u": "https://wamex.dmp.wa.gov.au/Wamex"}), "")

    def test_nsw_report(self):
        source = "https://search.geoscience.nsw.gov.au/report/R00035415"
        self.assertEqual(report_href({"st": "nsw", "u": source}), source)

    def test_nsw_fallback_is_search_not_document(self):
        self.assertEqual(
            report_href({"st": "nsw", "t": "EL 23186"}),
            "https://search.geoscience.nsw.gov.au/search?query=EL%2023186",
        )

    def test_qld_cr(self):
        self.assertEqual(
            report_href({"st": "qld", "id": "cr119257"}),
            "https://geoscience.data.qld.gov.au/data/report/cr119257",
        )

    def test_qld_uuid(self):
        value = "000acf17-3bcd-4262-9e49-3b8f6f00346e"
        self.assertEqual(
            report_href({"st": "qld", "id": value}),
            "https://geoscience.data.qld.gov.au/data/dataset/" + value,
        )

    def test_qld_unrelated_id_rejected(self):
        self.assertEqual(report_href({"st": "qld", "id": "EL23186"}), "")
        self.assertEqual(report_href({"st": "qld", "id": "cr119257garbage"}), "")

    def test_qld_actual_link_beats_internal_id(self):
        source = "https://example.com/original-contract.pdf"
        self.assertEqual(report_href({"st": "qld", "id": "123", "u": source}), source)

    def test_invalid_url_schemes(self):
        self.assertEqual(report_href({"st": "nt", "u": "httpx://example.com/doc"}), "")
        self.assertEqual(report_href({"st": "nt", "u": "javascript:alert(1)"}), "")

    def test_nt_original_link_preserved(self):
        source = "https://geoscience.nt.gov.au/gemis/ntgsjspui/bitstream/1/83875/1/EL23186_2004_A.pdf"
        self.assertEqual(report_href({"st": "nt", "u": source}), source)


if __name__ == "__main__":
    unittest.main()
