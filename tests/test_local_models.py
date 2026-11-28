"""Table 3.1 open-source components (full/local_models.py) with stand-in models."""
import os, unittest
from types import SimpleNamespace as NS
from unittest import mock
import numpy as np
from lensrag.domain import load_domain
from lensrag.full.local_models import Reranker, EntityNER, NLIVerifier, SentimentClassifier, claims_of
from lensrag.full.pipeline import PipelineConfig, apply_stack_components, LensRAGPipeline
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.routing import LOCAL_COMPONENTS

HR = load_domain("hr")
INV = {"domain": "hr", "entities": {"country": [{"value": "DE", "name": "Germany"}, {"value": "IN", "name": "India"},
                                                {"value": "UK", "name": "United Kingdom"}], "office": []},
       "versions": [], "periods": []}


class LengthScorer:  # longer passages score higher
    def predict(self, pairs, batch_size=16):
        return [len(text) for _, text in pairs]


class Chunk:
    def __init__(self, text): self.text = self.enriched_text = text


class FakeNLP:
    def __init__(self, ents): self.ents = ents
    def __call__(self, text):
        return NS(ents=[NS(text=t, label_=l) for t, l in self.ents if t.split("'")[0] in text])


class FakeNLI:
    """Entails when the claim's number appears in the premise; contradicts when another number does."""
    config = NS(id2label={0: "contradiction", 1: "entailment", 2: "neutral"})
    def predict(self, pairs, batch_size=8):
        out = []
        for premise, claim in pairs:
            nums = {w for w in claim.split() if w.isdigit()}
            if nums and nums <= set(premise.split()):
                out.append([0, 5, 0])
            elif nums and any(w.isdigit() for w in premise.split()):
                out.append([5, 0, 0])
            else:
                out.append([0, 0, 5])
        return np.array(out, dtype=float)


class FakeSentiment:
    def __call__(self, texts):
        return [[{"label": "negative", "score": 0.9 if "unhappy" in t else 0.1},
                 {"label": "neutral", "score": 0.05}, {"label": "positive", "score": 0.05}] for t in texts]


class ComponentTests(unittest.TestCase):
    def test_reranker_keeps_the_best(self):
        items = [(Chunk("a" * n), 0.0) for n in (3, 9, 5)]
        top = Reranker(model=LengthScorer()).rerank("q", items, 2)
        self.assertEqual([len(c.text) for c, _ in top], [9, 5])

    def test_ner_matches_spelling_variants_and_possessives(self):
        ner = EntityNER(nlp=FakeNLP([("Germny's", "GPE"), ("U.K.", "GPE"), ("Acme", "ORG")]))
        self.assertEqual(ner.match("What is Germny's annual leave?", INV, HR), {"country": ["DE"]})
        ner = EntityNER(nlp=FakeNLP([("Narnia", "GPE")]))
        self.assertEqual(ner.match("Leave in Narnia?", INV, HR), {})

    def test_claims_strip_citations_and_labels(self):
        self.assertEqual(claims_of("[exact] Germany gives 28 days of leave [POL-1]. Ok."), ["Germany gives 28 days of leave ."])

    def test_nli_entailed_contradicted_unsupported(self):
        out = NLIVerifier(model=FakeNLI()).verify(
            "Germany gives 28 days of annual leave. India gives 30 days of annual leave. Staff are generally happy here today.",
            ["Germany employees receive 28 days", "India employees receive 18 days"])
        self.assertEqual([c["status"] for c in out["claims"]], ["entailed", "contradicted", "unsupported"])
        self.assertAlmostEqual(out["supported_share"], 1 / 3)

    def test_sentiment_probabilities(self):
        probs = SentimentClassifier(model=FakeSentiment()).negative_probs(["I was unhappy", "great place"])
        self.assertEqual(probs, [0.9, 0.1])


class StackTests(unittest.TestCase):
    def test_local_stack_switches_components_on_and_env_can_turn_one_off(self):
        cfg = apply_stack_components(PipelineConfig(llm_stack="local-qwen"))
        self.assertEqual(cfg.reranker_model, LOCAL_COMPONENTS["reranker_model"])
        self.assertEqual(cfg.embedding_model, "BAAI/bge-m3")
        self.assertEqual(cfg.nli_model, LOCAL_COMPONENTS["nli_model"])
        with mock.patch.dict(os.environ, {"LENSRAG_NLI_MODEL": "off"}):
            self.assertIsNone(apply_stack_components(PipelineConfig(llm_stack="local-qwen")).nli_model)
        explicit = apply_stack_components(PipelineConfig(llm_stack="local-qwen", reranker_model="my/reranker"))
        self.assertEqual(explicit.reranker_model, "my/reranker")
        self.assertIsNone(apply_stack_components(PipelineConfig()).reranker_model)  # no stack: everything off


# --- pipeline integration --------------------------------------------------------------------
from tests.test_evidence import CHUNKS, INV as EV_INV, StubLLM  # noqa: E402
from tests.test_computation_modes import exit_note, RecordLLM, INV as REC_INV  # noqa: E402


class PipelineComponentTests(unittest.TestCase):
    def test_local_question_is_reranked_before_the_llm_filter(self):
        llm = StubLLM()
        pipe = LensRAGPipeline(PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True), EV_INV, llm,
                               PipelineConfig(page_size=1, rerank_candidates=5))
        pipe.reranker = Reranker(model=NS(predict=lambda pairs, batch_size=16: [("28 days" in t) * 1.0 for _, t in pairs]))
        out = pipe.ask("What is the annual leave in Germany?")
        self.assertEqual(out["adaptive_retrieval"]["reranker"], "BAAI/bge-reranker-v2-m3")
        self.assertEqual([c["doc_id"] for c in out["retrieved_chunks"]], ["POL-DE"])

    def test_ner_adds_entities_the_lookup_missed(self):
        pipe = LensRAGPipeline(PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True), EV_INV, StubLLM(), PipelineConfig())
        pipe.ner = EntityNER(nlp=FakeNLP([("Germny", "GPE")]))
        self.assertEqual(pipe._plan("How much annual leave do staff get in Germny?").named, {"country": ["DE"]})

    def test_sentiment_classifier_gives_soft_labels_for_estimates(self):
        before = [exit_note(i, "2026-Q1", i % 10 < 3) for i in range(60)]
        after = [exit_note(i, "2026-Q2", i % 10 < 6) for i in range(60)]
        llm = RecordLLM()
        pipe = LensRAGPipeline(PersistentHybridIndex(before + after, allow_lexical_fallback=True), REC_INV, llm,
                               PipelineConfig(max_exact_records=500, reduce_runs=2))
        pipe.sentiment = SentimentClassifier(model=FakeSentiment())
        out = pipe.ask("Did exit-interview sentiment in India become more negative after the rule took effect on 1 April 2026?")
        diff = out["estimate"]["difference"]
        self.assertAlmostEqual(diff["estimate"], 0.8 * 0.3, places=2)  # (0.9-0.1) x (0.6-0.3)
        self.assertNotIn("Label each", " ".join(llm.calls))           # no LLM labelling calls

    def test_nli_result_is_reported_in_verification(self):
        llm = StubLLM()
        pipe = LensRAGPipeline(PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True), EV_INV, llm, PipelineConfig())
        pipe.nli = NLIVerifier(model=FakeNLI())
        llm.text = lambda system, user: "Germany employees receive 28 days of annual leave."
        out = pipe.ask("Which country has the highest annual leave?")
        self.assertEqual(out["verification"]["nli"]["claims"][0]["status"], "entailed")


if __name__ == "__main__":
    unittest.main()


from lensrag.full.local_models import linearize_tables, focus_premise  # noqa: E402


class PremiseTests(unittest.TestCase):
    TABLE = "Intro text.\n\n| Entitlement | Value |\n| --- | --- |\n| Paid annual leave (working days) | 28 |\n| Sick days | 30 |"

    def test_tables_become_sentences(self):
        self.assertEqual(linearize_tables(self.TABLE).splitlines()[-2:], ["Paid annual leave (working days): 28.", "Sick days: 30."])
        wide = "| Country | Days | Weeks |\n|---|---|---|\n| India | 18 | 2 |"
        self.assertEqual(linearize_tables(wide), "India: Days 18, Weeks 2.")

    def test_premise_keeps_header_context_and_the_relevant_row(self):
        chunk = ("Document: Chapter 41. Germany addendum [POL-DE] | Type: policy | Section: Leave | Scope: DE | "
                 "Version: 3.0 | Status: current | Entities: Germany | Period: unspecified\n" + "Filler sentence. " * 50 + self.TABLE)
        premise = focus_premise(chunk, "Germany gives 28 days of paid annual leave.", lines=2)
        self.assertIn("Entities: Germany", premise)
        self.assertIn("Version: 3.0", premise)
        self.assertIn("Paid annual leave (working days): 28.", premise)
        self.assertNotIn("Period", premise)  # 'unspecified' fields are dropped
        self.assertLess(len(premise), 400)


class RepeatRetryTests(unittest.TestCase):
    def test_repetition_abort_is_retried_with_sampling_and_a_penalty(self):
        from lensrag.full.llm import LLMClient
        calls = []
        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                raise RuntimeError("Error code: 500 - prediction aborted, token repeat limit reached")
            return NS(choices=[NS(message=NS(content='{"answer": 1}'))], usage=None)
        llm = LLMClient.__new__(LLMClient); llm.model = "m"; llm.reset_usage()
        llm.client = NS(chat=NS(completions=NS(create=create)))
        self.assertEqual(llm.json("s", "u"), {"answer": 1})
        self.assertEqual(calls[1]["frequency_penalty"], 0.5)
        self.assertGreater(calls[1]["temperature"], 0)
        self.assertEqual(llm.usage["repeat_retries"], 1)

    def test_other_errors_are_not_retried(self):
        from lensrag.full.llm import LLMClient
        llm = LLMClient.__new__(LLMClient); llm.model = "m"; llm.reset_usage()
        llm.client = NS(chat=NS(completions=NS(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("context too long")))))
        with self.assertRaises(RuntimeError):
            llm.json("s", "u")


class StackFromEnvTests(unittest.TestCase):
    def test_stack_set_only_in_the_environment_still_switches_components_on(self):
        with mock.patch.dict(os.environ, {"LENSRAG_LLM_STACK": "local-qwen"}):
            cfg = apply_stack_components(PipelineConfig())
        self.assertEqual(cfg.llm_stack, "local-qwen")
        self.assertEqual(cfg.reranker_model, LOCAL_COMPONENTS["reranker_model"])
        self.assertEqual(cfg.nli_model, LOCAL_COMPONENTS["nli_model"])
