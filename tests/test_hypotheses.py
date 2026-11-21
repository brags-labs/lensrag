import json, tempfile, unittest
from pathlib import Path
import numpy as np
import pandas as pd
from lensrag.answers import score_answer, run_answers
from lensrag.hypotheses import analyse, holm

ROOT = Path(__file__).resolve().parents[1]


class ScoringTests(unittest.TestCase):
    def test_value_and_ratio(self):
        self.assertEqual(score_answer(28, 28, "value"), (1.0, 1.0))
        self.assertEqual(score_answer("28 days", 28, "value"), (1.0, 1.0))
        self.assertEqual(score_answer(3.43, 3.43, "value")[0], 1.0)
        self.assertEqual(score_answer(3.6, 3.43, "value")[0], 0.0)
        self.assertEqual(score_answer("44.3%", 0.443, "ratio")[0], 1.0)

    def test_set_and_ranked_list(self):
        em, f1 = score_answer(["Germany", "Ireland", "India"], ["Germany", "Ireland", "Netherlands"], "set")
        self.assertEqual(em, 0.0); self.assertAlmostEqual(f1, 2 / 3)
        gold = [["Germany", 20], ["Singapore", 17], ["India", 12]]
        self.assertEqual(score_answer(gold, gold, "ranked_list"), (1.0, 1.0))
        em, f1 = score_answer([["Singapore", 17], ["Germany", 20], ["India", 12]], gold, "ranked_list")
        self.assertEqual((em, f1), (0.0, 1.0))  # right names, wrong order

    def test_answers_as_name_number_objects(self):
        gold = [["Germany", 20], ["Singapore", 17], ["India", 12]]
        pred = [{"name": "Germany", "number": 20}, {"name": "Singapore", "number": 12}, {"name": "India", "number": 12}]
        self.assertEqual(score_answer(pred, gold, "ranked_list"), (0.0, 1.0))  # right names, one wrong value
        self.assertEqual(score_answer({"country": "United States", "weeks": 8}, ["United States", 8], "tuple"), (1.0, 1.0))

    def test_tuple_and_text(self):
        self.assertEqual(score_answer(["United States", 8], ["United States", 8], "tuple"), (1.0, 1.0))
        self.assertEqual(score_answer(["United States", 6], ["United States", 8], "tuple"), (0.0, 0.5))
        self.assertEqual(score_answer("No, it is a policy update.", "No: it is a legitimate policy update.", "text"), (1.0, 1.0))
        self.assertEqual(score_answer("anything", "HB-PNQ (Pune): 500 instead of 600", "text"), (None, None))


class HolmTests(unittest.TestCase):
    def test_holm(self):
        np.testing.assert_allclose(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


def synthetic_metrics():
    rows = []
    rng = np.random.default_rng(0)
    for i in range(30):
        scope = "local" if i < 10 else "global"
        for method, loc, glo in [("bm25_topk", .9, .3), ("hybrid_topk", .85, .3), ("lensrag", .9, .8),
                                 ("lensrag_rerank", .85, .85), ("long_context_128k", 1, .2), ("long_context_1m", 1, .6),
                                 ("long_context_full", 1, 1)]:
            r = float(np.clip((loc if scope == "local" else glo) + rng.normal(0, .05), 0, 1))
            rows.append({"tier": "L", "qid": f"Q{i}", "query_type": "local" if scope == "local" else ("conflict" if i < 13 else "count"),
                         "scope": scope, "method": method, "evidence_recall": r, "evidence_precision": r / 2, "evidence_f1": r / 1.5,
                         "evidence_complete": r > .95, "latency_ms": 1.0, "retrieved_docs": 5, "context_tokens": 1000,
                         "n_docs": 100, "completeness_flag": (r < .9) if method == "lensrag_rerank" else None})
    return pd.DataFrame(rows)


class AnalysisTests(unittest.TestCase):
    def test_analysis_detects_planted_effects_and_marks_answer_level_unmeasured(self):
        with tempfile.TemporaryDirectory() as td:
            synthetic_metrics().to_csv(Path(td) / "metrics.csv", index=False)
            r = analyse(td)
            h1 = [x for x in r["h1"] if x["metric"] == "evidence_recall"]
            self.assertTrue(all(x["significant"] for x in h1))
            h2 = {(x["ours"], x["baseline"], x["metric"]): x for x in r["h2"]}
            self.assertTrue(h2[("lensrag", "bm25_topk", "evidence_recall")]["significant"])
            self.assertIsNone(r["answer_level"])
            text = (Path(td) / "hypotheses.md").read_text()
            self.assertIn("Answer level: not measured", text)
            self.assertIn("## H3", text)


class StubLLM:
    """Answers with the gold-format placeholder; counts tokens like the real client."""
    model = "stub"
    def __init__(self): self.reset_usage()
    def reset_usage(self): self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    def json(self, system, user):
        self.usage["calls"] += 1; self.usage["prompt_tokens"] += len(user) // 4; self.usage["completion_tokens"] += 5
        if system.startswith("Answer the HR question") or system.startswith("Convert this answer"):
            return {"answer": 28}
        if system.startswith("Decide for each passage"):
            return {"passages": []}
        if system.startswith("Check whether"):
            return {"supported": True}
        return {}
    def text(self, system, user):
        self.usage["calls"] += 1
        return "28"


class AnswerRunnerTests(unittest.TestCase):
    def test_runner_scores_every_method_and_records_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            df = run_answers(ROOT / "data" / "bragslabs_corpus.zip", ROOT / "data" / "extracted", td, tier="S",
                             methods=("rag_topk", "long_context_128k", "lensrag"), llm=StubLLM(), limit=2,
                             lexical_fallback=True)
            self.assertEqual(sorted(df.method.unique()), ["lensrag", "long_context_128k", "rag_topk"])
            self.assertEqual(len(df), 6)
            self.assertTrue((df.error.fillna("") == "").all())
            q1 = df[(df.qid == "Q001")]  # gold answer is 28 (Germany annual leave)
            self.assertTrue((q1.exact_match == 1.0).all())
            self.assertTrue((df.total_tokens > 0).all())
            self.assertTrue((Path(td) / "answers.csv").exists())
            self.assertIn("interval_covered", df.columns)  # tier S questions are exact: nothing to cover
            self.assertTrue(df.interval_covered.isna().all())


if __name__ == "__main__":
    unittest.main()


from lensrag.answers import interval_coverage


class IntervalCoverageTests(unittest.TestCase):
    one = {"groups": {"all": {"estimate": 3.4, "ci_low": 3.2, "ci_high": 3.6, "n": 150, "population": 2208}}}

    def test_single_value_and_ratio(self):
        self.assertEqual(interval_coverage(self.one, 3.43, "value")["covered"], 1.0)
        self.assertEqual(interval_coverage(self.one, 3.9, "value")["covered"], 0.0)
        share = {"groups": {"all": {"estimate": 0.42, "ci_low": 0.36, "ci_high": 0.49}}}
        self.assertEqual(interval_coverage(share, 0.443, "ratio")["covered"], 1.0)

    def test_before_after_pair_uses_period_order(self):
        est = {"groups": {"(24315, 24435)": {"ci_low": 0.48, "ci_high": 0.62},   # after (listed first on purpose)
                          "(24195, 24314)": {"ci_low": 0.30, "ci_high": 0.42}}}  # before
        out = interval_coverage(est, [0.356, 0.563], "tuple")
        self.assertEqual((out["covered"], out["targets"]), (1.0, 2))
        self.assertEqual(interval_coverage(est, [0.563, 0.356], "tuple")["covered"], 0.0)

    def test_category_and_ranked_list(self):
        est = {"groups": {"all": {"n": 150, "population": 200, "categories": [
            {"category": "hybrid attendance and work mode", "estimate": 0.2, "ci_low": 0.15, "ci_high": 0.26},
            {"category": "Payroll", "estimate": 0.1, "ci_low": 0.06, "ci_high": 0.15}]}}}
        self.assertEqual(interval_coverage(est, ["Hybrid attendance and work mode", 38], "tuple")["covered"], 1.0)
        self.assertEqual(interval_coverage(est, ["Hybrid attendance and work mode", 80], "tuple")["covered"], 0.0)
        out = interval_coverage(est, [["Hybrid attendance and work mode", 40], ["Expense reimbursement", 24]], "ranked_list")
        self.assertEqual((out["covered"], out["targets"]), (0.5, 2))  # the second category was never estimated

    def test_no_estimate_means_not_applicable(self):
        self.assertIsNone(interval_coverage(None, 28, "value")["covered"])
        self.assertIsNone(interval_coverage(self.one, ["a", "b"], "set")["covered"])


class CoverageReportTests(unittest.TestCase):
    def test_report_shows_interval_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            synthetic_metrics().to_csv(Path(td) / "metrics.csv", index=False)
            pd.DataFrame([{"tier": "L", "qid": f"Q{i}", "method": "lensrag", "scope": "global", "exact_match": 0.0,
                           "set_f1": 0.0, "interval_covered": cov, "total_tokens": 100, "latency_s": 1.0, "error": ""}
                          for i, cov in enumerate([1.0, 1.0, 0.0, None])]).to_csv(Path(td) / "answers.csv", index=False)
            r = analyse(td)
            row = r["answer_level"][0]
            self.assertAlmostEqual(row["interval_coverage"], 2 / 3)
            self.assertEqual(row["n_interval"], 3)
            self.assertIn("Interval coverage", (Path(td) / "hypotheses.md").read_text())
