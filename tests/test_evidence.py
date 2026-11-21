import re, unittest
from lensrag.aggregation import aggregate_records, resolve_versions, find_conflicts, reduce_labels
from lensrag.data import Chunk
from lensrag.planning import plan_query, build_scopes
from lensrag.retrieval import coverage_retrieve
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig


def rec(entity, value, version="3.0", status="current", date="2026-04-01", doc="d"):
    return {"entity": entity, "attribute": "leave", "value": value, "evidence_span": f"{value}", "doc_id": doc,
            "version": version, "status": status, "effective_date": date}


class AggregationTests(unittest.TestCase):
    def test_resolution_prefers_current_and_flags_alternatives(self):
        records = [rec("India", 18), rec("India", 20, "2.0", "superseded", "2024-04-01"),
                   rec("India", 21, "", "announced", "2027-01-01")]
        resolved, flags = resolve_versions(records)
        self.assertEqual([r["value"] for r in resolved], [18])
        self.assertEqual(sorted(f["kind"] for f in flags), ["pending_change", "superseded_value"])

    def test_active_disagreement_is_a_conflict_resolved_to_latest(self):
        records = [rec("India", 8, date="2026-04-01", doc="manual"), rec("India", 10, "", "in force", "2026-06-01", "circular")]
        resolved, flags = resolve_versions(records)
        self.assertEqual(resolved[0]["value"], 10)
        self.assertEqual([(f["kind"], f["unresolved"]) for f in flags], [("conflict", False)])

    def test_rank_uses_k_keeps_ties_and_one_value_per_entity(self):
        records = [rec("UK", 25), rec("UK", 22, "2.0", "superseded"), rec("AU", 20), rec("IN", 18), rec("DE", 18), rec("SG", 14)]
        top3 = aggregate_records(records, "rank", top_k=3)
        self.assertEqual([r["entity"] for r in top3], ["UK", "AU", "IN", "DE"])  # IN and DE tie for third
        self.assertEqual(len(aggregate_records(records, "rank")), 5)
        self.assertEqual([r["entity"] for r in aggregate_records(records, "rank", top_k=2, direction="asc")], ["SG", "IN", "DE"])

    def test_count_filter_mean_share(self):
        records = [rec("UK", 25), rec("UK", 22, "2.0", "superseded"), rec("AU", 20), rec("IN", 10)]
        self.assertEqual(aggregate_records(records, "count"), 3)
        self.assertEqual([r["entity"] for r in aggregate_records(records, "filter", threshold=20, comparator="gte")], ["UK", "AU"])
        self.assertEqual([r["entity"] for r in aggregate_records(records, "filter", threshold=10, comparator="eq")], ["IN"])
        yes = [dict(rec("Bengaluru", True), attribute="gym and creche"), dict(rec("Pune", False), attribute="gym and creche")]
        self.assertEqual([r["entity"] for r in aggregate_records(yes, "filter")], ["Bengaluru"])
        self.assertEqual(aggregate_records([rec("t1", 3), rec("t2", 4)], "mean")["mean"], 3.5)
        self.assertEqual(aggregate_records(yes, "share")["share"], 0.5)

    def test_label_reduction_merges_variants(self):
        out = reduce_labels([{"labels": ["Hybrid policy", "hybrid-policy"], "period": "p"}, {"labels": ["Hybrid policies"], "period": "p"}])
        self.assertEqual(out, {"p": {"hybrid policy": 3}})


def chunk(cid, country, text, version="3.0", status="current", doc_type="policy_manual_chapter"):
    return Chunk(cid, cid.split("::")[0], cid, doc_type, country, version, "2026-04-01", status, "",
                 (), "Leave", text, f"Document: {cid} | Scope: {country} | Version: {version}\n{text}")


CHUNKS = [chunk("POL-UK::C0", "UK", "United Kingdom employees receive 25 days annual leave."),
          chunk("POL-AU::C0", "AU", "Australia employees receive 20 days annual leave."),
          chunk("POL-IN::C0", "IN", "India employees receive 18 days annual leave."),
          chunk("POL-DE::C0", "DE", "Germany employees receive 28 days annual leave."),
          chunk("POL-SG::C0", "SG", "Singapore employees receive 14 days annual leave."),
          chunk("OLD-DE::C0", "DE", "Germany employees receive 26 days annual leave.", "2.0", "superseded"),
          chunk("POL-DE::C1", "DE", "Germany office canteen opening hours are listed here.")]
# A company-wide table: one chunk that holds evidence for two countries.
SHARED = chunk("POL-ALL::C0", "GLOBAL", "Annual leave table: Canada employees receive 22 days annual leave; "
               "Ireland employees receive 24 days annual leave.")
INV2 = {"domain": "hr",
        "entities": {"country": [{"value": "CA", "name": "Canada"}, {"value": "IE", "name": "Ireland"}], "office": []},
        "versions": [], "periods": []}
INV = {"domain": "hr",
       "entities": {"country": [{"value": c, "name": n} for c, n in [("AU", "Australia"), ("DE", "Germany"), ("IN", "India"),
                                                                     ("SG", "Singapore"), ("UK", "United Kingdom")]],
                    "office": []},
       "versions": ["2.0", "3.0"], "periods": []}


class CoverageLoopTests(unittest.TestCase):
    def test_loop_pages_until_no_new_relevant_evidence(self):
        index = PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True)
        plan = plan_query("Which country has the highest annual leave?", INV)
        calls = []

        def judge(scope, items):
            calls.append((scope.label, [c.chunk_id for c, _ in items]))
            return [(c, s, None) for c, s in items if "annual leave" in c.text]
        hits, telemetry = coverage_retrieve(index, plan, build_scopes(plan, INV), judge=judge, page=1, max_rounds=5)
        self.assertTrue(telemetry["converged"])
        self.assertEqual({c.doc_id for c, *_ in hits}, {"POL-UK", "POL-AU", "POL-IN", "POL-DE", "POL-SG"})
        # Germany kept going while it found evidence and stopped at the first irrelevant page.
        de_pages = [ids for label, ids in calls if label == "Germany"]
        self.assertGreaterEqual(len(de_pages), 2)


class SharedChunkTests(unittest.TestCase):
    def test_shared_chunk_is_judged_and_credited_for_every_scope(self):
        index = PersistentHybridIndex([SHARED] + CHUNKS, allow_lexical_fallback=True)
        plan = plan_query("Which country has the highest annual leave?", INV2)
        judged = []

        def judge(scope, items):
            judged.append((scope.label, [c.chunk_id for c, _ in items]))
            return [(c, s, scope.label) for c, s in items if scope.label in c.text]
        hits, telemetry = coverage_retrieve(index, plan, build_scopes(plan, INV2), judge=judge, page=2)
        self.assertEqual(sorted(lab for c, _, lab, _ in hits if c.chunk_id == "POL-ALL::C0"), ["Canada", "Ireland"])
        self.assertEqual(telemetry["shared_chunks"], 1)
        self.assertEqual(telemetry["scopes_without_evidence"], [])
        self.assertTrue(all("POL-ALL::C0" in ids for _, ids in judged))

    def test_pipeline_extracts_each_entity_from_a_shared_table(self):
        class TableLLM(StubLLM):
            def json(self, system, user):
                if system.startswith("Decide for each passage"):
                    import json as _json
                    data = _json.loads(user)
                    out = []
                    for p in data["passages"]:
                        m = re.search(data["scope"] + r" employees receive (\d+) days", p["passage"])
                        out.append({"index": p["index"], "relevant": bool(m),
                                    "records": [{"entity": data["scope"], "attribute": "annual leave days",
                                                 "value": int(m[1]), "evidence_span": m[0]}] if m else []})
                    return {"passages": out}
                return super().json(system, user)
        index = PersistentHybridIndex([SHARED], allow_lexical_fallback=True)
        pipe = LensRAGPipeline(index, INV2, TableLLM(), PipelineConfig(page_size=2))
        out = pipe.ask("Rank the countries by annual leave days.")
        self.assertEqual([(r["entity"], r["value"]) for r in out["deterministic_result"]], [("Ireland", 24), ("Canada", 22)])
        self.assertTrue(out["verification"]["coverage"]["complete"])


class StubLLM:
    """Deterministic stand-in for the LLM: rules-only plan, regex extraction, fixed text."""
    def __init__(self): self.calls = []

    def json(self, system, user):
        import json as _json
        self.calls.append(system[:30])
        if system.startswith("Classify"):
            return {}
        if system.startswith("Decide for each passage"):
            data = _json.loads(user)
            out = []
            for p in data["passages"]:
                m = re.search(r"(\d+) days", p["passage"])
                if m and "leave" in p["passage"]:
                    out.append({"index": p["index"], "relevant": True,
                                "records": [{"entity": data["scope"].split(" / ")[0], "attribute": "annual leave days",
                                             "value": int(m[1]), "evidence_span": m[0]}]})
                else:
                    out.append({"index": p["index"], "relevant": False, "records": []})
            return {"passages": out}
        if system.startswith("Check whether"):
            return {"supported": True, "unsupported_claims": [], "notes": ""}
        return {}

    def text(self, system, user):
        return "answer"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        index = PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True)
        self.pipe = LensRAGPipeline(index, INV, StubLLM(), PipelineConfig(page_size=2))

    def test_filter_question_runs_and_filters_in_code(self):
        out = self.pipe.ask("Which countries offer more than 20 days of annual leave?")
        self.assertEqual(out["query_type"], "filter")
        self.assertEqual(sorted(r["entity"] for r in out["deterministic_result"]), ["Germany", "United Kingdom"])

    def test_top_three_returns_three_one_per_country(self):
        out = self.pipe.ask("Show the top three countries by annual leave days.")
        self.assertEqual([r["entity"] for r in out["deterministic_result"]], ["Germany", "United Kingdom", "Australia"])
        self.assertTrue(out["verification"]["coverage"]["complete"])

    def test_superseded_versions_excluded_unless_asked(self):
        out = self.pipe.ask("Which country has the highest annual leave?")
        self.assertNotIn("OLD-DE", {c["doc_id"] for c in out["retrieved_chunks"]})
        out = self.pipe.ask("For which countries did annual leave change between version 2.0 and version 3.0?")
        self.assertEqual(out["query_type"], "version_diff")
        kinds = {f["kind"] for f in out["verification"]["conflicts"]}
        self.assertIn("version_difference", kinds)

    def test_no_per_passage_entity_discovery_calls(self):
        self.pipe.ask("Which country has the highest annual leave?")
        self.assertFalse(any(c.startswith("From this passage") for c in self.pipe.llm.calls))


if __name__ == "__main__":
    unittest.main()
