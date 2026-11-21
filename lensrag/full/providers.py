"""Choose the LLM provider (and optionally a per-stage model stack).

provider: "anthropic" (Claude), "openai" (any OpenAI-compatible endpoint), "ollama" (a local
Ollama server through its OpenAI-compatible API), or "auto".
Auto picks Claude when ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is set, else OpenAI when
OPENAI_API_KEY or OPENAI_BASE_URL is set. LENSRAG_LLM_PROVIDER sets the default.
To use an `ant auth login` profile (no environment variable), choose "anthropic" explicitly.

stack: a named per-stage model preset from full/routing.py (e.g. "local-qwen"), or
LENSRAG_LLM_STACK. With a stack, each pipeline role gets its own model.
"""
from __future__ import annotations
import os

PROVIDERS = ("auto", "anthropic", "openai", "ollama")
OLLAMA_URL = "http://localhost:11434/v1"


def resolve_provider(provider=None):
    provider = (provider or os.getenv("LENSRAG_LLM_PROVIDER") or "auto").lower()
    if provider == "claude":
        provider = "anthropic"
    if provider == "auto":
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_BASE_URL"):
            return "openai"
        raise RuntimeError("No LLM credentials found: set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY / OPENAI_BASE_URL, "
                           "pass --llm-provider anthropic to use an `ant auth login` profile, or --llm-stack local-qwen "
                           "for local models.")
    if provider not in ("anthropic", "openai", "ollama"):
        raise ValueError(f"Unknown LLM provider: {provider}")
    return provider


def _client(provider, model):
    if provider == "anthropic":
        from .claude_llm import ClaudeClient
        return ClaudeClient(model=model)
    from .llm import LLMClient
    if provider == "ollama":
        return LLMClient(model=model, api_key="ollama", base_url=os.getenv("OLLAMA_OPENAI_URL", OLLAMA_URL))
    return LLMClient(model=model)


def create_llm(provider=None, model=None, stack=None):
    stack = stack or os.getenv("LENSRAG_LLM_STACK")
    if stack:
        from .routing import STACKS, RoutedLLM
        if stack not in STACKS:
            raise ValueError(f"Unknown model stack: {stack} (known: {', '.join(STACKS)})")
        spec = STACKS[stack]
        return RoutedLLM(provider or spec["provider"], spec["roles"], _client)
    return _client(resolve_provider(provider), model)
