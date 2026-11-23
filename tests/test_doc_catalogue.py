"""Document catalogue: questions about which documents exist, from index metadata (lensrag/doc_catalogue.py)."""
import unittest
from types import SimpleNamespace as NS
from lensrag.doc_catalogue import build_catalogue, describe, run


def doc(doc_id, doc_type, version="", country="GLOBAL", effective="", **meta):
    return NS(doc_id=doc_id, doc_type=doc_type, version=version, country=country, effective_date=effective,
              status="in force", meta={"title": f"{doc_id} title", **meta})


CHUNKS = [doc("POL-v2.0-CH01", "policy_manual_chapter", "2.0"),
          doc("POL-v2.0-CH40", "policy_manual_chapter", "2.0", "IN"),
          doc("POL-v2.0-CH41", "policy_manual_chapter", "2.0", "DE"),
          doc("POL-v3.0-CH40", "policy_manual_chapter", "3.0", "IN"),
          doc("POL-v3.0-CH41", "policy_manual_chapter", "3.0", "DE"),
          doc("POL-v3.0-CH42", "policy_manual_chapter", "3.0", "AU"),
          doc("CIR-1", "hr_circular", effective="2026-11-01", issued="2026-10-01"),
          doc("CIR-2", "hr_circular", effective="2027-01-01", issued="2026-12-01"),
          doc("HB-BLR", "office_handbook", country="IN", office="Bengaluru")]
NAMES = {"IN": "India", "DE": "Germany", "AU": "Australia"}
ROWS = build_catalogue(CHUNKS + CHUNKS[:2], lambda t, v: NAMES.get(v, v))   # repeated chunks: one row per document


class CatalogueTests(unittest.TestCase):
    def test_one_row_per_document_with_names_and_no_global_country(self):
        self.assertEqual(len(ROWS), 9)
        self.assertNotIn("country", ROWS[0])             # company-wide: 'GLOBAL' is not a country
        self.assertEqual(ROWS[1]["country"], "India")
        self.assertEqual(ROWS[1]["document_type"], "policy manual chapter")

    def test_count_and_list_with_exists(self):
        v3 = [{"field": "version", "op": "eq", "value": "3.0"}, {"field": "country", "op": "exists", "value": True}]
        self.assertEqual(run(ROWS, {"operation": "count", "filters": v3})[0], 3)
        self.assertEqual(run(ROWS, {"operation": "list", "target": "country", "filters": v3})[0],
                         ["Australia", "Germany", "India"])

    def test_list_minus_another_version(self):
        q = {"operation": "list", "target": "country",
             "filters": [{"field": "version", "op": "eq", "value": "3.0"}],
             "minus_filters": [{"field": "version", "op": "eq", "value": "2.0"}]}
        self.assertEqual(run(ROWS, q)[0], ["Australia"])

    def test_dates_compare_as_iso_strings(self):
        q = {"operation": "list", "filters": [{"field": "document_type", "op": "eq", "value": "hr circular"},
                                              {"field": "effective_date", "op": "gt", "value": "2026-11-01"}]}
        self.assertEqual(run(ROWS, q)[0], ["CIR-2"])
        self.assertIn("ISO date", describe(ROWS)["effective_date"]["kind"])


if __name__ == "__main__":
    unittest.main()
