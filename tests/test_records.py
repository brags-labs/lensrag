"""Record-aware ingestion (lensrag/records.py) and rules-first question typing."""
import json, unittest
from types import SimpleNamespace as NS
from lensrag.records import records_of_chunk, build_records, catalogue, run_query, parse_value

TICKETS = """### Ticket HD-AE-202511-0001 — Travel and relocation
**Opened:** 03 November 2025 · **Country:** United Arab Emirates · **Office:** Dubai
**Status:** Closed · **Resolved in:** 7 working hours · **CSAT:** 3/5

### Ticket HD-AE-202511-0002 — Policy clarification
**Opened:** 08 November 2025 · **Country:** United Arab Emirates · **Office:** Dubai
**Status:** Resolved · **Resolved in:** 8 working hours · **CSAT:** 1/5
"""
SURVEY = """**PULSE26-AE-0001** · Dubai · L2 · off-site · likelihood to recommend: 2/10
*Topic tagged by respondent:* Recognition
Recognition goes to the same few people.

**PULSE26-AE-0002** · Dubai · L3 · remote · likelihood to recommend: 9/10
*Topic tagged by respondent:* Hybrid and office days
Anchor days have improved collaboration.
"""
EXIT = """### Exit interview EXIT-AE-2025Q4-001
**Last working day:** 21 October 2025 · **Country:** United Arab Emirates
**Primary reason:** Fully remote offer elsewhere · **Would rejoin:** Yes
**Outcome.** Resolved informally. Action: none.
"""


def chunk(text, doc_type, cid="c1", doc_id="D1", period="2025-11"):
    return NS(text=text, doc_type=doc_type, chunk_id=cid, doc_id=doc_id, period=period, status="current")


class ParseTests(unittest.TestCase):
    def test_ticket_blocks_and_fields(self):
        recs = records_of_chunk(chunk(TICKETS, "helpdesk_ticket_log"))
        self.assertEqual([r["id"] for r in recs], ["HD-AE-202511-0001", "HD-AE-202511-0002"])
        self.assertEqual(recs[0]["title"], "Travel and relocation")
        self.assertEqual(recs[0]["csat"], "3/5")
        self.assertEqual(recs[1]["resolved_in"], "8 working hours")

    def test_survey_comments_several_per_chunk_with_inline_and_italic_fields(self):
        recs = records_of_chunk(chunk(SURVEY, "survey_comments"))
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[1]["topic_tagged_by_respondent"], "Hybrid and office days")
        self.assertEqual(recs[0]["likelihood_to_recommend"], "2/10")

    def test_heading_that_ends_in_an_id_and_sentence_fields(self):
        rec = records_of_chunk(chunk(EXIT, "exit_interview_notes"))[0]
        self.assertEqual(rec["id"], "EXIT-AE-2025Q4-001")
        self.assertEqual(rec["primary_reason"], "Fully remote offer elsewhere")
        self.assertEqual(rec["outcome"], "Resolved informally")

    def test_values(self):
        self.assertEqual(parse_value("3/5")[1], 3.0)
        self.assertEqual(parse_value("7 working hours")[1], 7.0)
        self.assertEqual(str(parse_value("03 November 2025")[2]), "2025-11-03")

    def test_duplicates_across_overlapping_chunks_are_dropped(self):
        recs = build_records([chunk(TICKETS, "helpdesk_ticket_log", "c1"), chunk(TICKETS, "helpdesk_ticket_log", "c2"),
                              chunk("Policy text.", "policy_manual_chapter", "c3")], {"helpdesk_ticket_log"})
        self.assertEqual(len(recs), 2)


def recs(n_hybrid, n_leave, csat=4, period="2026-04"):
    rows = []
    for i in range(n_hybrid + n_leave):
        title = "Hybrid attendance" if i < n_hybrid else "Leave balance"
        text = f"### Ticket HD-X-{period.replace('-', '')}-{i:04d} — {title}\n**Status:** Closed · **CSAT:** {csat}/5\n"
        rows.append(chunk(text, "helpdesk_ticket_log", f"{period}-{i}", period=period))
    return build_records(rows, {"helpdesk_ticket_log"})


class QueryTests(unittest.TestCase):
    def test_count_mode_share_mean(self):
        g = {"all": recs(3, 2)}
        self.assertEqual(run_query(g, {"operation": "count", "filters": [{"field": "title", "op": "eq", "value": "hybrid attendance"}]})["groups"]["all"]["estimate"], 3)
        mode = run_query(g, {"operation": "mode", "target": "title"})["groups"]["all"]["categories"][0]
        self.assertEqual((mode["category"], mode["count"]), ("Hybrid attendance", 3))
        share = run_query(g, {"operation": "share", "condition": [{"field": "title", "op": "eq", "value": "Leave balance"}]})
        self.assertEqual(share["groups"]["all"]["estimate"], 0.4)
        self.assertEqual(run_query(g, {"operation": "mean", "target": "csat"})["groups"]["all"]["estimate"], 4.0)

    def test_rank_groups_by_record_count(self):
        out = run_query({"India": recs(5, 0), "Germany": recs(2, 0), "Canada": recs(3, 0)}, {"operation": "rank_groups", "k": 2})
        self.assertEqual([(c["category"], c["count"]) for c in out["groups"]["all"]["categories"]], [("India", 5), ("Canada", 3)])

    def test_catalogue_lists_categories_and_hides_identifiers(self):
        cat = catalogue(recs(3, 2))["helpdesk_ticket_log"]["fields"]
        self.assertEqual(sorted(cat["title"]["values"]), ["Hybrid attendance", "Leave balance"])
        self.assertEqual(cat["csat"]["type"], "number")

    def test_a_tie_at_the_k_cut_keeps_every_tied_item(self):
        out = run_query({"A": recs(5, 0), "B": recs(3, 0), "C": recs(3, 0), "D": recs(1, 0)}, {"operation": "rank_groups", "k": 2})
        self.assertEqual([c["category"] for c in out["groups"]["all"]["categories"]], ["A", "B", "C"])

    def test_net_share_ranks_groups_by_promoters_minus_detractors(self):
        recs_of = lambda scores: build_records([chunk("\n\n".join(
            f"**PULSE26-AE-{i:04d}** · Dubai · L2 · remote · likelihood to recommend: {s}/10\n*Topic tagged by respondent:* Workload"
            for i, s in enumerate(scores)), "survey_comments")], {"survey_comments"})
        promoters = [{"field": "likelihood_to_recommend", "op": "gte", "value": 9}]
        detractors = [{"field": "likelihood_to_recommend", "op": "lte", "value": 6}]
        g = {"A": recs_of([10, 9, 2, 7]), "B": recs_of([1, 2, 9, 8])}
        out = run_query(g, {"operation": "max_group", "condition": promoters, "minus_condition": detractors})
        top = out["groups"]["all"]["categories"][0]
        self.assertEqual((top["category"], top["count"]), ("A", 25.0))   # 50% promoters - 25% detractors
        one = run_query({"all": g["B"]}, {"operation": "net_share", "condition": promoters, "minus_condition": detractors})
        self.assertEqual(one["groups"]["all"]["estimate"], -25.0)

    def test_count_conditioned_on_a_year_of_a_date_valued_attribute(self):
        from lensrag.full.pipeline import LensRAGPipeline
        rs = [{"value_as_written": y} for y in ("2016", "2025", "2019", "2025")]
        self.assertEqual(LensRAGPipeline._asked_year("How many offices opened in 2025?", rs), "2025")
        self.assertIsNone(LensRAGPipeline._asked_year("How many countries give 20 days?", [{"value_as_written": "20"}]))

    def test_missing_target_means_not_answerable(self):
        self.assertIsNone(run_query({"all": recs(1, 1)}, {"operation": "mean", "target": "nonexistent"}))


class TypeSourceTests(unittest.TestCase):
    def test_rules_decide_the_type_and_the_llm_type_is_only_recorded(self):
        from tests.test_evidence import CHUNKS, INV, StubLLM
        from lensrag.full.index import PersistentHybridIndex
        from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig

        class WrongClassifier(StubLLM):
            def json(self, system, user, **kw):
                if system.startswith("Classify"):
                    return {"qtype": "aggregate"}
                return super().json(system, user, **kw)
        idx = PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True)
        pipe = LensRAGPipeline(idx, INV, WrongClassifier(), PipelineConfig())
        plan = pipe._plan("What is the annual leave in Germany?")
        self.assertEqual(plan.qtype, "local")
        self.assertEqual(pipe._llm_qtype, "aggregate")
        pipe = LensRAGPipeline(idx, INV, WrongClassifier(), PipelineConfig(type_source="llm"))
        self.assertEqual(pipe._plan("What is the annual leave in Germany?").qtype, "aggregate")

    def test_stated_parameters_beat_the_llm_parameters(self):
        from tests.test_evidence import CHUNKS, INV, StubLLM
        from lensrag.full.index import PersistentHybridIndex
        from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig

        class WrongParams(StubLLM):
            def json(self, system, user, **kw):
                if system.startswith("Classify"):
                    return {"qtype": "filter", "direction": "asc", "threshold": 16, "comparator": "gte", "k": 5}
                return super().json(system, user, **kw)
        idx = PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True)
        pipe = LensRAGPipeline(idx, INV, WrongParams(), PipelineConfig())
        plan = pipe._plan("Which three countries have the highest annual leave?")
        self.assertEqual((plan.direction, plan.k), ("desc", 3))
        plan = pipe._plan("Which countries give more than 16 weeks of leave?")
        self.assertEqual((plan.threshold, plan.comparator), (16.0, "gt"))
        # unstated parameters still come from the LLM
        plan = pipe._plan("Which countries give annual leave?")
        self.assertEqual(plan.direction, "asc")

    def test_entity_named_as_written_takes_the_scope_name(self):
        from tests.test_evidence import CHUNKS, INV, StubLLM
        from lensrag.full.index import PersistentHybridIndex
        from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig
        pipe = LensRAGPipeline(PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True), INV, StubLLM(), PipelineConfig())
        name = next(e["name"] for items in INV["entities"].values() for e in items)
        recs = pipe._canonical_entities([{"entity": "Some Legal Entity Ltd", "scope": name},
                                         {"entity": "Elsewhere", "scope": "all"}])
        self.assertEqual([r["entity"] for r in recs], [name, "Elsewhere"])

    def test_facts_outside_the_asked_version_are_dropped(self):
        from types import SimpleNamespace as NS
        from lensrag.full.pipeline import LensRAGPipeline
        pipe = LensRAGPipeline.__new__(LensRAGPipeline)
        pipe.index = NS(chunks=[NS(version="2.0", effective_date="2024-01-01"),
                                NS(version="3.0", effective_date="2026-11-01")])
        recs = [{"doc_id": "POL-v2", "version": "2.0", "effective_date": "2024-01-01", "value": 2},
                {"doc_id": "CIR-2023", "version": "", "effective_date": "2024-01-01", "value": 2},
                {"doc_id": "CIR-2026", "version": "", "effective_date": "2026-11-01", "value": 3},
                {"doc_id": "POL-v3", "version": "3.0", "effective_date": "2026-11-01", "value": 3},
                {"doc_id": "FAQ", "version": "", "effective_date": "", "value": 2}]
        keep, drop = pipe._in_version(recs, NS(versions=["2.0"]))
        self.assertEqual([r["doc_id"] for r in keep], ["POL-v2", "CIR-2023", "FAQ"])
        self.assertEqual(len(drop), 2)
        self.assertEqual(len(pipe._in_version(recs, NS(versions=["2.0", "3.0"]))[0]), 5)

    def test_explicit_direction_edge_cases(self):
        from lensrag.planning import explicit_direction as d
        self.assertEqual(d("Which three countries have the highest employer retirement contribution?"), "desc")
        self.assertEqual(d("Rank the three oldest offices by opening year."), "asc")
        self.assertIsNone(d("Which countries give at least 20 days of annual leave?"))   # a threshold
        self.assertIsNone(d("Who is the oldest employee?"))                               # age, not a date
        self.assertEqual(d("Which country pays the least?"), "asc")
        self.assertIsNone(d("Which countries give leave?"))


class UnitTests(unittest.TestCase):
    def test_working_days_under_a_weeks_attribute_become_weeks(self):
        from lensrag.aggregation import validate_evidence_records
        recs, _ = validate_evidence_records([
            {"entity": "India", "attribute": "partner leave at full pay (weeks)", "value": 10, "doc_id": "d",
             "evidence_span": "Partner / non-birth-parent leave at full pay (weeks) | 10 working days"},
            {"entity": "Canada", "attribute": "partner leave at full pay (weeks)", "value": 6, "doc_id": "d",
             "evidence_span": "partners 6 weeks at full pay"},
            {"entity": "India", "attribute": "annual leave (days)", "value": 10, "doc_id": "d",
             "evidence_span": "10 working days"}])
        self.assertEqual([r["value"] for r in recs], [2, 6, 10])


if __name__ == "__main__":
    unittest.main()
