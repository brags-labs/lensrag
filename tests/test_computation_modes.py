"""Step 7 computation modes: exact (A), estimated (B) and generated (C)."""
import json, re, unittest
from lensrag.aggregation import aggregate_records, number_provenance
from lensrag.data import Chunk
from lensrag.estimation import (wilson_interval, stratified_sample, share_estimate, soft_labels, stratified_estimate,
                                stratified_difference, category_shares, majority_category)
from lensrag.synthesis import consistent_insights
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig


def rec(entity, attribute, value, doc="d"):
    return {"entity": entity, "attribute": attribute, "value": value, "evidence_span": "x", "doc_id": doc}


class ModeATests(unittest.TestCase):
    def test_categorical_frequency_mode_and_crosstab(self):
        recs = [dict(rec("IN", "category", v), scope="India") for v in ["Expense reimbursement", "expense reimbursements", "Payroll"]]
        recs += [dict(rec("UK", "category", v), scope="United Kingdom") for v in ["Leave", "Payroll"]]
        self.assertEqual(aggregate_records(recs, "mode")["India"], ["Expense reimbursement"])
        self.assertEqual(sorted(aggregate_records(recs, "mode")["United Kingdom"]), ["Leave", "Payroll"])  # a tie
        self.assertEqual(aggregate_records(recs, "frequency", top_k=1)["India"], [("Expense reimbursement", 2)])
        self.assertEqual(aggregate_records(recs, "crosstab")["United Kingdom"], {"Leave": 1, "Payroll": 1})

    def test_all_of_any_of_and_sum(self):
        offices = [rec("Bengaluru", "on-site gym", True), rec("Bengaluru", "creche", True),
                   rec("Pune", "on-site gym", True), rec("Pune", "creche", False)]
        self.assertEqual(aggregate_records(offices, "all_of", resolve=False)["entities"], ["Bengaluru"])
        self.assertEqual(aggregate_records(offices, "any_of", resolve=False)["entities"], ["Bengaluru", "Pune"])
        self.assertEqual(aggregate_records([rec("a", "x", 2), rec("b", "x", 3.5)], "sum")["sum"], 5.5)

    def test_number_provenance(self):
        self.assertEqual(number_provenance("UK gives 25 days; 31% of cases; 99 more", [25, 0.31]), [99.0])
        self.assertEqual(number_provenance("Three countries, 2 steps", []), [])  # small integers ignored


class ModeBTests(unittest.TestCase):
    def test_wilson_matches_reference_values(self):
        lo, hi = wilson_interval(31, 100)
        self.assertAlmostEqual(lo, 0.2278, places=3); self.assertAlmostEqual(hi, 0.4063, places=3)

    def test_stratified_sample_is_proportional_and_reproducible(self):
        strata = {"IN": list(range(800)), "UK": list(range(200)), "SG": list(range(3))}
        s1, sizes = stratified_sample(strata, 100, seed=1)
        s2, _ = stratified_sample(strata, 100, seed=1)
        self.assertEqual({k: len(v) for k, v in s1.items()}, {"IN": 80, "UK": 20, "SG": 1})
        self.assertEqual(s1, s2)
        self.assertEqual(sizes["IN"], 800)

    def test_shares_soft_labels_and_finite_population(self):
        self.assertTrue(share_estimate([1, 0, 1, 1], population=4)["exact"])
        whole = share_estimate([1, 0, 1, 1], population=4)
        self.assertEqual((whole["ci_low"], whole["ci_high"]), (0.75, 0.75))
        self.assertEqual(soft_labels([[True, False], [True, True], [False, True]]), [2 / 3, 2 / 3])
        self.assertEqual(majority_category([["a", "b"], ["a", "b"], ["c", "b"]]), [("a", 2 / 3), ("b", 1.0)])

    def test_stratified_estimate_weights_by_population(self):
        # 10 sampled records each, but IN has 9x the population: the pooled share leans to IN.
        est = stratified_estimate({"IN": ([1] * 10, 900), "UK": ([0] * 10, 100)})
        self.assertAlmostEqual(est["estimate"], 0.9)
        diff = stratified_difference({"x": ([0] * 65 + [1] * 35, 1000)}, {"x": ([0] * 46 + [1] * 54, 1000)})
        self.assertAlmostEqual(diff["estimate"], 0.19)
        self.assertGreater(diff["ci_low"], 0)

    def test_category_shares(self):
        out = category_shares(["a", "a", "b", None])
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["categories"][0]["category"], "a")


class FakeReduceLLM:
    """Five reduce runs: one insight in every run, one in 3 of 5, one only once."""
    def __init__(self): self.run = 0
    def json(self, system, user):
        self.run += 1
        ins = [{"key": "Sentiment worsened", "text": "Negative share rose from 35% to 54%.", "citations": ["EXIT-1", "BOGUS"]}]
        if self.run <= 3:
            ins.append({"key": "commute concerns", "text": "Commute concerns grew.", "citations": []})
        if self.run == 5:
            ins.append({"key": "one-off idea", "text": "A one-off idea mentioning 77 people.", "citations": ["EXIT-1"]})
        return {"insights": ins}


class ModeCTests(unittest.TestCase):
    def test_majority_support_citations_and_numbers(self):
        out = consistent_insights(FakeReduceLLM(), "q", notes=[], stats={"before": 0.35, "after": 0.54},
                                  evidence_doc_ids=["EXIT-1"], k=5)
        by_key = {i["key"]: i for i in out["insights"]}
        self.assertEqual(set(by_key), {"sentiment worsened", "commute concern"})
        self.assertEqual(by_key["sentiment worsened"]["support"], 1.0)
        self.assertEqual(by_key["sentiment worsened"]["citations"], ["EXIT-1"])  # unknown ids dropped
        self.assertEqual(by_key["sentiment worsened"]["unverified_numbers"], [])
        self.assertEqual(by_key["commute concern"]["status"], "hypothesis")    # 3/5 but no citations
        self.assertEqual([d["key"] for d in out["dropped"]], ["one off idea"])


# --- end-to-end on synthetic record logs ------------------------------------------------
def ticket(i, country, csat, category):
    text = f"Ticket HD-{country}-{i:04d} — {category}. Resolved. CSAT: {csat}/5"
    return Chunk(f"TKT-{country}-202604::C{i:04d}", f"TKT-{country}-202604", "t.md", "helpdesk_ticket_log", country, "", "",
                 "", "2026-04", (), "Tickets", text, "Document: tickets\n" + text)


def exit_note(i, period, negative):
    tone = "I was unhappy with the office attendance rule." if negative else "I enjoyed my time here."
    text = f"Exit interview {period}-{i:03d}. {tone}"
    return Chunk(f"EXIT-IN-{period}::C{i:04d}", f"EXIT-IN-{period}", "e.md", "exit_interview_notes", "IN", "", "", "",
                 period, (), "Exits", text, "Document: exits\n" + text)


INV = {"domain": "hr", "entities": {"country": [{"value": "IN", "name": "India"}, {"value": "UK", "name": "United Kingdom"}],
                                    "office": []}, "versions": [], "periods": []}


class RecordLLM:
    """Labels records by reading them; writes fixed insights; never invents numbers."""
    def __init__(self): self.calls = []
    def json(self, system, user):
        self.calls.append(system[:20])
        if system.startswith("Label each record"):
            data = json.loads(user); out = []
            for r in data["records"]:
                t = r["text"]
                if "number the question asks" in system:
                    m = re.search(r"CSAT: (\d)/5", t); out.append({"index": r["index"], "applies": True,
                                                                    "value": int(m[1]), "evidence_span": m[0]})
                elif "sentiment" in system:
                    neg = "unhappy" in t
                    out.append({"index": r["index"], "applies": True, "value": "negative" if neg else "positive",
                                "evidence_span": t.split(". ")[1]})
                else:
                    m = re.search(r"— ([^.]+)\.", t); out.append({"index": r["index"], "applies": True, "value": m[1],
                                                                 "evidence_span": m[1]})
            return {"records": out}
        if system.startswith("You write insights"):
            return {"insights": [{"key": "exit sentiment worsened", "text": "Exit sentiment became more negative after the rule.",
                                  "citations": ["EXIT-IN-2026-Q2"]}]}
        if system.startswith("Check whether"):
            return {"supported": True}
        return {}
    def text(self, system, user):
        return "The answer, using only computed results."


class PipelineModeTests(unittest.TestCase):
    def setUp(self):
        self.tickets = [ticket(i, "IN", 1 + (i % 5), "Payroll" if i % 3 else "Expense reimbursement") for i in range(400)]
        self.tickets += [ticket(i, "UK", 4, "Leave") for i in range(50)]
        self.true_mean = sum(1 + (i % 5) for i in range(400)) / 400

    def pipe(self, chunks, **cfg):
        return LensRAGPipeline(PersistentHybridIndex(chunks, allow_lexical_fallback=True), INV, RecordLLM(),
                               PipelineConfig(seed=7, **cfg))

    def test_mean_over_many_records_is_estimated_with_interval(self):
        out = self.pipe(self.tickets, max_exact_records=100, sample_size=120, label_passes=2).ask(
            "What was the average CSAT score of HR helpdesk tickets in India in April 2026?")
        self.assertEqual(out["computation_mode"], "estimated")
        g = out["estimate"]["groups"]["all"]
        self.assertEqual(out["estimate"]["records_in_scope"], 400)
        self.assertLess(out["estimate"]["sampled_records"], 400)
        self.assertLessEqual(g["ci_low"], self.true_mean); self.assertGreaterEqual(g["ci_high"], self.true_mean)
        self.assertTrue(out["verification"]["uncertainty"]["ok"])
        self.assertTrue(out["verification"]["number_provenance"]["ok"])

    def test_small_population_is_computed_exactly(self):
        out = self.pipe(self.tickets, max_exact_records=1000).ask(
            "What was the average CSAT score of HR helpdesk tickets in India in April 2026?")
        self.assertEqual(out["computation_mode"], "exact")
        self.assertAlmostEqual(out["estimate"]["groups"]["all"]["estimate"], self.true_mean)

    def test_most_common_category_is_estimated_with_shares(self):
        out = self.pipe(self.tickets, max_exact_records=100, sample_size=120, label_passes=1).ask(
            "What was the most common helpdesk ticket category in India in April 2026?")
        cats = out["estimate"]["groups"]["all"]["categories"]
        self.assertEqual(cats[0]["category"], "payroll")  # 2/3 of tickets
        self.assertLess(cats[0]["ci_low"], 2 / 3); self.assertGreater(cats[0]["ci_high"], 2 / 3)

    def test_sentiment_shift_estimates_difference_and_keeps_agreed_insights(self):
        before = [exit_note(i, "2026-Q1", i % 10 < 3) for i in range(120)]   # 30% negative
        after = [exit_note(i, "2026-Q2", i % 10 < 6) for i in range(120)]    # 60% negative
        pipe = self.pipe(before + after, max_exact_records=50, sample_size=100, label_passes=2, reduce_runs=3)
        out = pipe.ask("Did exit-interview sentiment in India become more negative after the rule took effect on 1 April 2026?")
        self.assertEqual(out["computation_mode"], "generated")
        diff = out["estimate"]["difference"]
        self.assertAlmostEqual(diff["estimate"], 0.3, delta=0.12)
        self.assertGreater(diff["ci_low"], 0)
        self.assertEqual([i["key"] for i in out["insights"]["insights"]], ["exit sentiment worsened"])
        self.assertEqual(out["insights"]["insights"][0]["support"], 1.0)


if __name__ == "__main__":
    unittest.main()
