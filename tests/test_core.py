import unittest
from pathlib import Path
from lensrag.data import ensure_extracted, load_documents, load_gold, chunk_document
from lensrag.metrics import evidence_recall, evidence_precision, set_f1
from lensrag.retrieval import BM25, route_query
from lensrag.aggregation import aggregate_records, completeness_report, find_conflicts, validate_evidence_records

ROOT=Path(__file__).resolve().parents[1]

class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=ensure_extracted(ROOT/"data"/"bragslabs_corpus.zip",ROOT/"data"/"extracted")

    def test_tier_document_counts(self):
        self.assertEqual(len(load_documents(self.corpus,"S")),46)
        self.assertEqual(len(load_documents(self.corpus,"M")),245)
        self.assertEqual(len(load_documents(self.corpus,"L")),495)

    def test_gold_benchmark(self):
        self.assertEqual(len(load_gold(self.corpus)),89)

    def test_retrieval_excluded_documents_not_loaded(self):
        ids={d.doc_id for d in load_documents(self.corpus,"L")}
        self.assertNotIn("POL-v3.0-CH37",ids)

    def test_context_header_has_policy_metadata(self):
        d=load_documents(self.corpus,"S")[0]
        c=chunk_document(d)[0]
        self.assertIn("Effective date:",c.enriched_text)
        self.assertIn("Version:",c.enriched_text)
        self.assertIn("Scope:",c.enriched_text)

    def test_metrics(self):
        self.assertAlmostEqual(evidence_recall(["a","b"],["a","c"]),.5)
        self.assertAlmostEqual(evidence_precision(["a","b"],["a","c"]),.5)
        self.assertAlmostEqual(set_f1(["a","b"],["a","c"]),.5)

    def test_router(self):
        self.assertEqual(route_query("How many countries offer more than 20 days?"),"count")
        self.assertEqual(route_query("What is the policy for India?"),"local")


    def test_deterministic_aggregation(self):
        records=[
            {"entity":"India","attribute":"leave","value":18,"evidence_span":"18 days","doc_id":"a"},
            {"entity":"Germany","attribute":"leave","value":28,"evidence_span":"28 days","doc_id":"b"},
        ]
        self.assertEqual(aggregate_records(records,"count"),2)
        self.assertEqual(aggregate_records(records,"max")["value"],28)

    def test_completeness_and_conflicts(self):
        records=[
            {"entity":"India","attribute":"sick_days","value":8,"version":"3.0","doc_id":"a","evidence_span":"8 days"},
            {"entity":"India","attribute":"sick_days","value":10,"version":"3.0","doc_id":"b","evidence_span":"10 days"},
            {"entity":"India","attribute":"sick_days","value":6,"version":"2.0","doc_id":"c","evidence_span":"6 days"},
        ]
        self.assertEqual(completeness_report(records,["India","Germany"])["missing_entities"],["Germany"])
        self.assertEqual(len(find_conflicts(records)),1)

    def test_evidence_validation(self):
        valid,rejected=validate_evidence_records([{"entity":"India","attribute":"leave","value":18,"evidence_span":"18 days","doc_id":"a"},{}])
        self.assertEqual(len(valid),1)
        self.assertEqual(len(rejected),1)

    def test_bm25(self):
        b=BM25(["India annual leave policy","Germany pension contribution"])
        scores=b.score("India leave")
        self.assertGreater(scores[0],scores[1])

if __name__=="__main__": unittest.main()
