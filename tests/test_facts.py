import unittest
from types import SimpleNamespace as NS
from lensrag.facts import facts_of_chunk, number, tables
from lensrag.answers import answer_from_aggregate


def chunk(text, **kw):
    base = dict(chunk_id="c1", doc_id="D1", doc_type="policy_manual_chapter", version="3.0", status="current",
                effective_date="2026-11-01", period="", country="IN", meta={})
    base.update(kw)
    return NS(text=text, **base)


class TableTests(unittest.TestCase):
    def test_key_value_rows(self):
        fs = facts_of_chunk(chunk("| Entitlement | Value |\n|---|---|\n| Employer retirement contribution (% of pay) | 12 |\n"
                                  "| Partner leave (weeks) | 10 working days |"))
        self.assertEqual([(f["attribute"], f["number"]) for f in fs],
                         [("Employer retirement contribution (% of pay)", 12.0), ("Partner leave (weeks)", 10.0)])
        self.assertEqual(fs[0]["evidence_span"], "| Employer retirement contribution (% of pay) | 12 |")

    def test_before_after_rows_keep_the_new_value_and_subject(self):
        fs = facts_of_chunk(chunk("| Item | Before | From 1 October 2022 |\n|---|---|---|\n"
                                  "| India — Revised night shift allowance | ₹400 per night | ₹450 per night |"))
        self.assertEqual(len(fs), 1)
        self.assertEqual((fs[0]["subject"], fs[0]["attribute"], fs[0]["number"], fs[0]["previous_value"]),
                         ("India", "Revised night shift allowance", 450.0, "₹400 per night"))

    def test_matrix_rows_name_the_column(self):
        fs = facts_of_chunk(chunk("| Floor | Teams | Desks |\n|---|---|---|\n| 1 | Design | 73 |"))
        self.assertEqual([f["attribute"] for f in fs], ["1 — Teams", "1 — Desks"])

    def test_dates_are_not_numbers_and_text_without_a_header_is_not_a_table(self):
        self.assertIsNone(number("22 August 2022"))
        self.assertEqual(number("₹40,000"), 40000.0)
        self.assertEqual(tables("| a | b |\n| c | d |"), [])


class FormatTests(unittest.TestCase):
    def test_formats_from_a_computed_result(self):
        rows = [{"entity": "Germany", "value": 20.0}, {"entity": "Singapore", "value": 17.0}]
        r = {"answer_source": "fact table", "deterministic_result": rows}
        self.assertEqual(answer_from_aggregate(r, "ranked_list"), [["Germany", 20], ["Singapore", 17]])
        self.assertEqual(answer_from_aggregate(r, "set"), ["Germany", "Singapore"])
        self.assertIsNone(answer_from_aggregate(r, "tuple"))
        one = {"answer_source": "fact table", "deterministic_result": {"entity": "India", "value": "₹600", "value_as_written": "₹600"}}
        self.assertEqual(answer_from_aggregate(one, "value"), "₹600")
        diff = {"answer_source": "fact table", "deterministic_result": {"changed": ["Ireland"], "versions": ["2.0", "3.0"],
                                                                         "by_version": {}}}
        self.assertEqual(answer_from_aggregate(diff, "set"), ["Ireland"])
        cnt = {"answer_source": "fact table", "deterministic_result": {"count": 5, "entities": []}}
        self.assertEqual(answer_from_aggregate(cnt, "value"), 5)


if __name__ == "__main__":
    unittest.main()
