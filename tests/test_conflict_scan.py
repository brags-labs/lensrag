"""Index-time conflict scan over table facts (lensrag/conflict_scan.py)."""
import re
import unittest
import numpy as np
from lensrag.conflict_scan import scan, unit_kind
from lensrag.facts import number

ROLES = {"primary": ["policy_manual_chapter"], "update": ["hr_circular"], "secondary": ["faq", "office_handbook"]}


def encode(texts):
    """Hashed bag-of-words vectors: rows with the same label words match exactly."""
    m = np.full((len(texts), 256), 1e-9)
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z]+", t.lower()):
            m[i, sum(map(ord, w)) * 31 % 256] += 1
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def fact(doc_id, doc_type, attribute, value, country="IN", version="", status="current", previous=None):
    f = {"doc_id": doc_id, "doc_type": doc_type, "attribute": attribute, "value": value, "number": number(value),
         "country": country, "version": version, "status": status, "effective_date": "", "reference": False,
         "evidence_span": f"| {attribute} | {value} |", "subject": None, "section": ""}
    if previous:
        f["previous_value"] = previous
    return f


class ConflictScanTests(unittest.TestCase):
    def kinds(self, facts):
        return sorted((f["kind"], tuple(f["documents"])) for f in scan(facts, encode, ROLES))

    def test_version_change_within_one_chapter(self):
        fs = [fact("POL-v1.0-CH09", "policy_manual_chapter", "Paid sick leave (days)", "7", version="1.0", status="superseded"),
              fact("POL-v3.0-CH09", "policy_manual_chapter", "Paid sick leave (days)", "8", version="3.0")]
        self.assertEqual(self.kinds(fs), [("version_change", ("POL-v1.0-CH09", "POL-v3.0-CH09"))])

    def test_stale_faq_and_agreeing_faq(self):
        fs = [fact("POL-v3.0-CH16", "policy_manual_chapter", "Paternity leave", "10 working days", version="3.0"),
              fact("FAQ-IN", "faq", "Paternity leave", "7 working days", status=""),
              fact("FAQ-IN2", "faq", "Paternity leave", "10 working days", status="")]
        flags = scan(fs, encode, ROLES)
        self.assertEqual([(f["kind"], f["documents"]) for f in flags], [("stale_secondary", ["FAQ-IN", "POL-v3.0-CH16"])])
        self.assertEqual(flags[0]["applies"]["doc_id"], "POL-v3.0-CH16")

    def test_announced_update_is_pending_and_in_force_update_wins_over_stale_handbook(self):
        fs = [fact("POL-v3.0-CH12", "policy_manual_chapter", "Night shift allowance", "₹400 per night", version="3.0"),
              fact("CIR-1", "hr_circular", "Night shift allowance", "₹450 per night", status="announced", previous="₹400 per night"),
              fact("POL-v3.0-CH20", "policy_manual_chapter", "Wellbeing allowance", "₹8,000", version="3.0"),
              fact("CIR-2", "hr_circular", "Wellbeing allowance", "₹10,000", status="in force", previous="₹8,000"),
              fact("HB-PNQ", "office_handbook", "Wellbeing allowance", "₹8,000", status="")]
        flags = {f["kind"]: f for f in scan(fs, encode, ROLES)}
        self.assertEqual(flags["update_pending"]["applies"]["value"], "₹400 per night")
        self.assertEqual(flags["update_unapplied"]["applies"]["doc_id"], "CIR-2")
        self.assertEqual(flags["stale_secondary"]["applies"]["doc_id"], "CIR-2")    # the handbook matches the old manual value

    def test_other_country_and_other_unit_do_not_match(self):
        fs = [fact("POL-v3.0-CH40", "policy_manual_chapter", "Annual leave", "18 days", version="3.0"),
              fact("FAQ-DE", "faq", "Annual leave", "28 days", country="DE", status=""),
              fact("HB-BLR", "office_handbook", "Annual leave", "20%", status="")]
        self.assertEqual(self.kinds(fs), [])
        self.assertEqual(unit_kind("₹1,000"), "money")


class JudgeTests(unittest.TestCase):
    def test_judge_matches_rows_with_different_labels(self):
        fs = [fact("POL-v3.0-CH40", "policy_manual_chapter", "Paid annual leave (days)", "18 days", version="3.0"),
              fact("POL-v3.0-CH41", "policy_manual_chapter", "Paid sick leave (days)", "8 days", version="3.0"),
              fact("CIR-9", "hr_circular", "Earned leave increase", "20 days", status="in force", previous="18 days")]
        seen = []
        def judge(items):
            seen.extend(items)
            return [next(c for c in cands if "annual" in c["attribute"]) for _, cands in items]
        flags = scan(fs, encode, ROLES, judge=judge, floor=-1)
        self.assertEqual(len(seen[0][1]), 2)                       # both same-country candidates offered
        self.assertEqual([(f["kind"], f["documents"]) for f in flags], [("update_unapplied", ["CIR-9", "POL-v3.0-CH40"])])


if __name__ == "__main__":
    unittest.main()
