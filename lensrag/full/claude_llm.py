"""Claude (Anthropic Messages API) adapter with the same interface as `LLMClient`.

`json(system, user)` returns a dict, `text(system, user)` a string, and `usage` accumulates
token counts per question, so the pipeline and the answer runner work unchanged.

Credentials come from the environment the usual way for the Anthropic SDK:
ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile.

Settings (environment variables, or constructor arguments):
  LENSRAG_LLM_MODEL         model id (default claude-opus-5-5)
  LENSRAG_LLM_EFFORT        low | medium | high | xhigh | max (default medium, the model's own default)
  LENSRAG_CLAUDE_FALLBACKS  "default" (re-run a declined request on a fallback model, server-side) or "off"
"""
from __future__ import annotations
import json
import os
import re

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept the server-side `fallbacks` parameter.
FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
JSON_INSTRUCTION = "\n\nRespond with one JSON object only: no prose before or after it and no code fences."


class ClaudeRefusal(RuntimeError):
    """Claude declined the request (stop_reason == "refusal")."""


def _parse_json(text: str):
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            return json.loads(s[start:end + 1])
        raise


class ClaudeClient:
    def __init__(self, model=None, effort=None, fallbacks=None, max_tokens=16000, client=None):
        self.model = model or os.getenv("LENSRAG_LLM_MODEL") or DEFAULT_CLAUDE_MODEL
        self.effort = effort or os.getenv("LENSRAG_LLM_EFFORT") or "medium"
        if fallbacks is None:
            fallbacks = os.getenv("LENSRAG_CLAUDE_FALLBACKS", "default")
        self.fallbacks = fallbacks if fallbacks not in ("off", "none", "") and self.model in FALLBACK_MODELS else None
        self.max_tokens = max_tokens
        if client is None:
            import anthropic
            client = anthropic.Anthropic(max_retries=4)
        self.client = client
        self.reset_usage()

    def reset_usage(self):
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "cache_read_tokens": 0,
                      "cache_write_tokens": 0, "calls": 0}

    def _track(self, r):
        u = getattr(r, "usage", None)
        self.usage["calls"] += 1
        if u is None:
            return
        read = getattr(u, "cache_read_input_tokens", 0) or 0
        write = getattr(u, "cache_creation_input_tokens", 0) or 0
        self.usage["prompt_tokens"] += (getattr(u, "input_tokens", 0) or 0) + read + write
        self.usage["completion_tokens"] += getattr(u, "output_tokens", 0) or 0
        self.usage["cache_read_tokens"] += read
        self.usage["cache_write_tokens"] += write

    def _create(self, system, user):
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            # Cached so repeated long prompts (e.g. a long-context corpus) are billed at the cache-read rate;
            # prefixes below the model's minimum cacheable size are simply not cached.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort},
        )
        if self.fallbacks:
            r = self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks=self.fallbacks, **kwargs)
        else:
            r = self.client.messages.create(**kwargs)
        self._track(r)
        if r.stop_reason == "refusal":
            details = getattr(r, "stop_details", None)
            raise ClaudeRefusal(f"Claude declined the request (category: {getattr(details, 'category', None)})")
        if r.stop_reason == "max_tokens":
            raise RuntimeError(f"Claude's reply hit max_tokens={self.max_tokens} and was cut off")
        return "".join(b.text for b in r.content if b.type == "text")

    def json(self, system, user, temperature=None):
        # `temperature` is accepted for interface compatibility and ignored: the API no longer takes it.
        text = self._create(system + JSON_INSTRUCTION, user)
        try:
            return _parse_json(text)
        except json.JSONDecodeError:
            text = self._create(system + JSON_INSTRUCTION,
                                user + "\n\nYour previous reply was not valid JSON. Reply with only the JSON object.")
            return _parse_json(text)

    def text(self, system, user, temperature=None):
        return self._create(system, user)
