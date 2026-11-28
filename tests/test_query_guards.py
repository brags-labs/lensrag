"""Guards on the structured answer paths: stated conditions are kept or the path gives up,
negated criteria keep their polarity, resumed runs match their experiment, and templated
answers disclose what verification found."""
import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from lensrag.answers import check_resume, run_fingerprint
from lensrag.data import Chunk
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig, disclosures

INV = {"domain": "hr", "entities": {"country": [{"value": "IN", "name": "India"}], "office": []},
       "versions": [], "periods": []}
QUESTION = "How many HR helpdesk tickets in India in April 2026 had a CSAT of 3?"


def tickets(csats=(3, 3, 1, 4, 5)):
    text = "\n".join(f"### Ticket HD-IN-202604-{i:04d} — Payroll\n**Opened:** 0{1 + i} April 2026 · **Country:** India\n"
                     f"**Status:** Closed · **CSAT:** {c}/5\n" for i, c in enumerate(csats))
    return [Chunk("TKT-IN-202604::C0001", "TKT-IN-202604", "t.md", "helpdesk_ticket_log", "IN", "", "", "", "2026-04",
                  (), "Tickets", text, "Document: tickets\n" + text)]


class QueryLLM:
    """Maps every question to one fixed record query."""
    def __init__(self, query): self.query = query
    def json(self, system, user):
        if system.startswith("Map the question"): return self.query
        if system.startswith("Check whether"): return {"supported": True}
        return {}
    def text(self, system, user): return "Answer from passages."


def ask(query, question=QUESTION):
    pipe = LensRAGPipeline(PersistentHybridIndex(tickets(), allow_lexical_fallback=True), INV, QueryLLM(query),
                           PipelineConfig(record_fields=True, template_answers=True, fact_table=False, doc_catalogue=False))
    return pipe.ask(question)


def count_query(value):
    return {"answerable": True, "operation": "count", "filters": [{"field": "csat", "op": "eq", "value": value}],
            "group_by": "none"}


class RecordFilterTests(unittest.TestCase):
    def test_numeric_equality_filter_is_kept_and_matches_scored_values(self):
        out = ask(count_query(3))
        self.assertEqual(out["adaptive_retrieval"]["mode"], "record fields")
        self.assertEqual(out["estimate"]["groups"]["all"]["estimate"], 2)    # '3/5' matches 3

    def test_misread_condition_falls_back_instead_of_broadening(self):
        out = ask(count_query(4))                                            # the question says 3
        self.assertNotEqual(out["adaptive_retrieval"].get("mode"), "record fields")

    def test_invented_filter_on_an_unnamed_condition_is_still_dropped(self):
        out = ask(count_query(4), "How many HR helpdesk tickets were raised in India in April 2026?")
        self.assertEqual(out["adaptive_retrieval"]["mode"], "record fields")
        self.assertEqual(out["estimate"]["groups"]["all"]["estimate"], 5)

    def test_field_answer_reports_no_missing_coverage(self):
        self.assertNotIn("Incomplete coverage", ask(count_query(3))["answer"])


def fact(entity, attribute, value):
    return {"entity": entity, "attribute": attribute, "value": value, "specific": True, "evidence_span": f"| {attribute} | {value} |",
            "doc_id": f"HB-{entity}", "version": "", "status": "", "effective_date": "", "period": None, "scope": entity,
            "chunk": NS(chunk_id=f"HB-{entity}::1")}


class CriteriaTests(unittest.TestCase):
    OFFICES = {"BLR": ("Yes", "Yes"), "PNQ": ("Yes", "No"), "HYD": ("No", "No")}

    def run_criteria(self, question, required=(True, True)):
        by_attr = {"gym": [fact(e, "Gym", g) for e, (g, _) in self.OFFICES.items()],
                   "creche": [fact(e, "Crèche", c) for e, (_, c) in self.OFFICES.items()]}
        top = [("gym", 1.0), ("creche", 1.0)]
        cands = [{"id": 0, "attribute": "Gym"}, {"id": 1, "attribute": "Crèche"}]
        pick = {"answerable": True, "criteria": [{"criterion": "gym", "attribute_ids": [0], "required": required[0]},
                                                 {"criterion": "crèche", "attribute_ids": [1], "required": required[1]}]}
        out = LensRAGPipeline._fact_criteria(LensRAGPipeline.__new__(LensRAGPipeline), NS(operation="all_of"), pick, top,
                                             by_attr, cands, [NS(entity_value=e) for e in self.OFFICES], question)
        return [a["entity"] for a in out[1] or []]

    def test_both_present(self):
        self.assertEqual(self.run_criteria("Which offices have both a gym and a crèche?"), ["BLR"])

    def test_negated_criterion_from_the_question_wording(self):
        # the model marked both criteria required; the question's 'no crèche' decides
        self.assertEqual(self.run_criteria("Which offices have both a gym but no crèche?"), ["PNQ"])
        self.assertEqual(self.run_criteria("Which offices have a gym but do not have a creche?"), ["PNQ"])

    def test_model_polarity_used_when_the_wording_is_silent(self):
        self.assertEqual(self.run_criteria("Which offices have both facilities listed?", required=(True, False)), ["PNQ"])


class ResumeTests(unittest.TestCase):
    def test_resume_requires_the_same_fingerprint(self):
        cfg = PipelineConfig()
        a = run_fingerprint({"model": "m", "cfg": cfg})
        self.assertEqual(a, run_fingerprint({"model": "m", "cfg": PipelineConfig()}))
        self.assertNotEqual(a, run_fingerprint({"model": "other", "cfg": cfg}))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "answers_config.json"
            self.assertRaises(ValueError, check_resume, path, a)                     # no config: unknown run
            path.write_text(json.dumps({"fingerprint": a}))
            check_resume(path, a)
            self.assertRaises(ValueError, check_resume, path, run_fingerprint({"model": "other", "cfg": cfg}))


class DisclosureTests(unittest.TestCase):
    def test_verification_findings_are_written_out(self):
        note = disclosures({
            "coverage": {"expected_count": 3, "present_count": 2, "missing_entities": ["Germany"], "complete": False},
            "conflicts": [{"kind": "conflict", "key": {"entity": "IN", "attribute": "Paternity leave"},
                           "values": ["10", "7"], "sources": [{"doc_id": "POL-IN"}, {"doc_id": "FAQ-IN"}]}],
            "version_resolution": [{"kind": "pending_change", "key": "IN", "chosen": {"value": 400, "doc_id": "POL"},
                                    "other": {"value": 450, "doc_id": "CIR-1"}}],
            "claim_support": {"supported": False, "unsupported_claims": ["Germany offers 30 days"]},
            "uncertainty": {"ok": True, "problems": []}})
        for text in ("Incomplete coverage", "Germany", "Conflict: IN, Paternity leave is stated as 10 / 7",
                     "Pending change", "450 [CIR-1]", "Germany offers 30 days"):
            self.assertIn(text, note)

    def test_nothing_to_disclose(self):
        self.assertEqual(disclosures({"coverage": {"expected_count": 2, "complete": True}, "conflicts": [],
                                      "claim_support": {"supported": True}}), "")


if __name__ == "__main__":
    unittest.main()
