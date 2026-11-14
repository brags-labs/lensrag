"""Choose the LLM provider for the full runtime and the answer runner.

provider: "anthropic" (Claude), "openai" (any OpenAI-compatible endpoint), or "auto".
Auto picks Claude when ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is set, else OpenAI when
OPENAI_API_KEY or OPENAI_BASE_URL is set. LENSRAG_LLM_PROVIDER sets the default.
To use an `ant auth login` profile (no environment variable), choose "anthropic" explicitly.
"""
from __future__ import annotations
import os

PROVIDERS = ("auto", "anthropic", "openai")


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
                           "or pass --llm-provider anthropic to use an `ant auth login` profile.")
    if provider not in ("anthropic", "openai"):
        raise ValueError(f"Unknown LLM provider: {provider}")
    return provider


def create_llm(provider=None, model=None):
    if resolve_provider(provider) == "anthropic":
        from .claude_llm import ClaudeClient
        return ClaudeClient(model=model)
    from .llm import LLMClient
    return LLMClient(model=model)
