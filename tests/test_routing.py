import os, unittest
from unittest import mock
from lensrag.full.routing import RoutedLLM, STACKS, ollama_variants, role, ROLES
from lensrag.full.providers import create_llm


class FakeClient:
    def __init__(self, provider, model):
        self.provider, self.model = provider, model
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    def json(self, system, user, **kw):
        self.usage["calls"] += 1; self.usage["prompt_tokens"] += 10; self.usage["completion_tokens"] += 2
        return {"model": self.model}
    def text(self, system, user):  # no **kw: the router must cope with clients that take no options
        self.usage["calls"] += 1; self.usage["prompt_tokens"] += 5
        return self.model


class RoutingTests(unittest.TestCase):
    def routed(self, **env):
        with mock.patch.dict(os.environ, env, clear=False):
            return RoutedLLM("ollama", STACKS["local-qwen"]["roles"], FakeClient)

    def test_each_role_reaches_its_model_and_usage_adds_up(self):
        llm = self.routed()
        self.assertEqual(role(llm, "classify").json("s", "u")["model"], "lensrag-qwen2.5-3b")
        self.assertEqual(role(llm, "extract").json("s", "u")["model"], "lensrag-qwen2.5-14b")
        self.assertEqual(role(llm, "answer").text("s", "u", temperature=1.0), "lensrag-qwen2.5-32b")
        self.assertEqual(llm.usage["calls"], 3)
        self.assertEqual(llm.usage["prompt_tokens"], 25)
        self.assertEqual(llm.usage["by_role"]["extract"], {"calls": 1, "prompt_tokens": 10, "completion_tokens": 2})
        self.assertEqual(len(llm._clients), 3)  # one client per distinct model, reused across roles
        llm.reset_usage(); self.assertEqual(llm.usage["calls"], 0)

    def test_environment_overrides_a_role(self):
        llm = self.routed(LENSRAG_MODEL_ANSWER="qwen2.5:7b")
        self.assertEqual(role(llm, "answer").text("s", "u"), "qwen2.5:7b")
        self.assertEqual(role(llm, "reduce").json("s", "u")["model"], "lensrag-qwen2.5-32b")

    def test_single_client_passes_through(self):
        c = FakeClient("x", "m")
        self.assertIs(role(c, "classify"), c)

    def test_ollama_variants_set_context_window(self):
        v = ollama_variants("local-qwen")
        self.assertEqual(set(v), {"lensrag-qwen2.5-3b", "lensrag-qwen2.5-14b", "lensrag-qwen2.5-32b"})
        self.assertEqual(v["lensrag-qwen2.5-14b"], "FROM qwen2.5:14b\nPARAMETER num_ctx 32768\n")

    def test_create_llm_with_stack(self):
        llm = create_llm(stack="local-qwen")
        self.assertIsInstance(llm, RoutedLLM)
        self.assertEqual(llm.provider, "ollama")
        self.assertEqual(set(llm.roles), set(ROLES))


class PipelineRoleTests(unittest.TestCase):
    def test_pipeline_sends_each_stage_to_its_role(self):
        from tests.test_evidence import CHUNKS, INV, StubLLM
        from lensrag.full.index import PersistentHybridIndex
        from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig
        seen = []
        class Tracking(StubLLM):
            pass
        stub = Tracking()
        llm = RoutedLLM("ollama", STACKS["local-qwen"]["roles"], lambda p, m: stub)
        orig = llm._call
        def spy(r, kind, system, user, **kw):
            seen.append(r); return orig(r, kind, system, user, **kw)
        llm._call = spy
        pipe = LensRAGPipeline(PersistentHybridIndex(CHUNKS, allow_lexical_fallback=True), INV, llm, PipelineConfig(page_size=2))
        pipe.ask("Which countries offer more than 20 days of annual leave?")
        self.assertEqual(seen[0], "classify")
        self.assertIn("extract", seen); self.assertIn("verify", seen)
        self.assertEqual(seen[-1], "answer")


if __name__ == "__main__":
    unittest.main()
