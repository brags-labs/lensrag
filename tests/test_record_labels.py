"""Index-time sentiment labels for opinion records (lensrag/record_labels.py)."""
import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from lensrag.records import build_records, run_query
from lensrag.record_labels import label_records, load_labels, apply_labels, record_key

SURVEY = "\n\n".join(f"**PULSE26-AE-{i:04d}** · Dubai · L2 · remote · likelihood to recommend: {s}/10\n"
                     f"*Topic tagged by respondent:* {t}\n{text}"
                     for i, (s, t, text) in enumerate([(2, "Pay and benefits", "Pay has not kept up. Frustrating."),
                                                       (9, "Pay and benefits", "The new bands are fair."),
                                                       (3, "Workload", "Too many late calls.")]))


def records():
    c = NS(text=SURVEY, doc_type="survey_comments", chunk_id="c1", doc_id="D1", period="2026-04", status="current")
    return build_records([c], {"survey_comments"})


class LabelTests(unittest.TestCase):
    def test_records_keep_their_text_for_labelling(self):
        rs = records()
        self.assertIn("Frustrating", rs[0].text)
        self.assertNotIn("_text", rs[0].fields)

    def test_labels_are_cached_and_become_a_countable_field(self):
        calls = []
        def fake(system, user):
            n = len(json.loads(user)["records"]); calls.append(n)
            return {"labels": ["negative", "positive", "negative"][:n] if n == 3 else ["negative"] * n}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "record_labels.json"
            rs = records()
            labels = label_records(rs, fake, "m1", path, workers=1, progress=None)
            self.assertEqual(labels[record_key(rs[1])], "positive")
            label_records(rs, fake, "m1", path, workers=1, progress=None)
            self.assertEqual(calls, [3])                      # second run reuses the cache
            self.assertEqual(load_labels(path, "another-model"), {})   # another model relabels
            apply_labels(rs, load_labels(path))
        out = run_query({"all": rs}, {"operation": "top_k", "target": "topic_tagged_by_respondent", "k": 1,
                                       "filters": [{"field": "sentiment", "op": "eq", "value": "negative"}]})
        top = out["groups"]["all"]["categories"]
        self.assertEqual([(c["category"], c["count"]) for c in top], [("Pay and benefits", 1), ("Workload", 1)])

    def test_a_malformed_batch_is_retried_one_record_at_a_time(self):
        def fake(system, user):
            n = len(json.loads(user)["records"])
            return {"labels": ["neutral"]} if n == 1 else {"labels": ["neutral"]}   # wrong length for a batch
        labels = label_records(records(), fake, "m1", None, workers=1, progress=None)
        self.assertEqual(len(labels), 3)


if __name__ == "__main__":
    unittest.main()
