"""Per-stage model routing (report Table 3.1): a different model for each pipeline role.

Roles and the pipeline stages that use them:
  classify  query classification and parameters (Step 3)            - small model
  extract   relevance filter, evidence extraction, record labelling (Steps 5-6, Mode B labels)
  map       map step of map-reduce (Mode C)
  reduce    reduce step of map-reduce, repeated for agreement (Mode C) - strong model
  verify    claim-support judge (Step 8)
  answer    writing and finalising the answer (Step 9), and baseline answers - strong model

`RoutedLLM` looks like one client (json / text / usage / reset_usage) but sends each call to
the client for its role; `with_role(role)` returns a view used by the pipeline. Token usage
from every role is added to one `usage` total, so cost per question still works.

Stacks (named presets) are in STACKS; individual roles can be overridden with environment
variables LENSRAG_MODEL_<ROLE> (e.g. LENSRAG_MODEL_ANSWER=qwen2.5:14b).
"""
from __future__ import annotations
import os

ROLES = ("classify", "extract", "map", "reduce", "verify", "answer")

# Ollama model tags; the "lensrag-" variants are the same weights with a 32k context window
# (see `ollama_variants` and docs/LOCAL_MODELS.md). 72B models don't fit in 36 GB, so the strong
# roles use Qwen2.5-32B.
# The non-LLM open-source components of Table 3.1 (see full/local_models.py), switched on by
# the local stacks. Each can be turned off per run with LENSRAG_<NAME>=off.
LOCAL_COMPONENTS = {
    "embedding_model": "BAAI/bge-m3",                                       # Search: dense embeddings
    "reranker_model": "BAAI/bge-reranker-v2-m3",                            # Search + rerank
    "spacy_model": "en_core_web_sm",                                        # Select entities: NER
    "nli_model": "cross-encoder/nli-deberta-v3-large",                      # Verify evidence: NLI
    "sentiment_model": "cardiffnlp/twitter-roberta-base-sentiment-latest",  # Per-record sentiment labels
}

STACKS = {
    "local-qwen": {
        "provider": "ollama",
        "roles": {"classify": "lensrag-qwen2.5-3b", "extract": "lensrag-qwen2.5-14b", "map": "lensrag-qwen2.5-14b",
                  "reduce": "lensrag-qwen2.5-32b", "verify": "lensrag-qwen2.5-14b", "answer": "lensrag-qwen2.5-32b"},
        "components": LOCAL_COMPONENTS,
    },
    "local-qwen-14b": {  # one mid-size model everywhere: faster, less memory
        "provider": "ollama",
        "roles": {r: "lensrag-qwen2.5-14b" for r in ROLES},
        "components": LOCAL_COMPONENTS,
    },
}


def stack_components(stack):
    """The stack's non-LLM components, with LENSRAG_<NAME>=off (or another model name) applied."""
    comps = dict((STACKS.get(stack) or {}).get("components") or {})
    for name in list(comps):
        override = os.getenv(f"LENSRAG_{name.upper()}")
        if override:
            comps[name] = None if override.lower() in ("off", "none", "0") else override
    return comps


def ollama_variants(stack="local-qwen", num_ctx=32768):
    """Modelfiles for the stack's "lensrag-" models: {variant name: Modelfile text}."""
    out = {}
    for name in set(STACKS[stack]["roles"].values()):
        if name.startswith("lensrag-"):
            base = name[len("lensrag-"):].replace("qwen2.5-", "qwen2.5:")
            out[name] = f"FROM {base}\nPARAMETER num_ctx {num_ctx}\n"
    return out


class _RoleView:
    def __init__(self, parent, role):
        self.parent, self.role = parent, role
        self.model = parent.model_for(role)

    @property
    def usage(self):
        return self.parent.usage

    def json(self, system, user, **kw):
        return self.parent._call(self.role, "json", system, user, **kw)

    def text(self, system, user, **kw):
        return self.parent._call(self.role, "text", system, user, **kw)


import threading
_USAGE_LOCK = threading.Lock()


class RoutedLLM:
    def __init__(self, provider, roles, factory, default_role="answer"):
        """factory(provider, model) -> client with json/text/usage/reset_usage."""
        self.provider, self.default_role = provider, default_role
        self.roles = {r: os.getenv(f"LENSRAG_MODEL_{r.upper()}") or roles.get(r) or roles.get(default_role) for r in ROLES}
        self._factory = factory
        self._clients = {}
        self.model = " / ".join(f"{r}={self.roles[r]}" for r in ROLES)
        self.reset_usage()

    def model_for(self, role):
        return self.roles.get(role) or self.roles[self.default_role]

    def client(self, role):
        model = self.model_for(role)
        if model not in self._clients:
            self._clients[model] = self._factory(self.provider, model)
        return self._clients[model]

    def reset_usage(self):
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
                      "calls": 0, "by_role": {}}

    def _call(self, role, kind, system, user, **kw):
        c = self.client(role)
        before = dict(getattr(c, "usage", {}) or {})
        try:
            out = getattr(c, kind)(system, user, **kw)
        except TypeError:
            out = getattr(c, kind)(system, user)
        # A client that reports its own last call (per thread) is exact under concurrency;
        # otherwise the difference of its running totals (exact when calls don't overlap).
        last = c.last_call_usage() if hasattr(c, "last_call_usage") else None
        after = getattr(c, "usage", {}) or {}
        with _USAGE_LOCK:
            role_u = self.usage["by_role"].setdefault(role, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            for k in ("prompt_tokens", "completion_tokens", "cache_read_tokens", "cache_write_tokens", "calls"):
                d = (last or {}).get(k, 0) if last is not None else (after.get(k, 0) or 0) - (before.get(k, 0) or 0)
                self.usage[k] = self.usage.get(k, 0) + d
                if k in role_u:
                    role_u[k] += d
        return out

    def with_role(self, role):
        return _RoleView(self, role)

    def json(self, system, user, **kw):
        return self._call(self.default_role, "json", system, user, **kw)

    def text(self, system, user, **kw):
        return self._call(self.default_role, "text", system, user, **kw)


def role(llm, name):
    """The client to use for a pipeline role: a routed view, or the single client itself."""
    return llm.with_role(name) if hasattr(llm, "with_role") else llm
