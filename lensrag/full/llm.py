from __future__ import annotations
import json, os


class LLMClient:
    """OpenAI-compatible chat-completions adapter; configure endpoint/model via env.

    `usage` accumulates prompt/completion tokens and call counts so experiments can
    report token cost per question (reset it between questions with `reset_usage`).
    """
    def __init__(self, model=None, api_key=None, base_url=None):
        try: from openai import OpenAI
        except ImportError as e: raise RuntimeError("LLM stages require: pip install openai") from e
        self.model=model or os.getenv("LENSRAG_LLM_MODEL","gpt-4o-mini")
        base_url=base_url or os.getenv("OPENAI_BASE_URL")
        key=api_key or os.getenv("OPENAI_API_KEY") or ("local" if base_url else None)
        if not key: raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_BASE_URL for a compatible local server).")
        self.client=OpenAI(api_key=key,base_url=base_url)
        self.reset_usage()

    def reset_usage(self):
        self.usage={"prompt_tokens":0,"completion_tokens":0,"calls":0}

    def _track(self, r):
        u=getattr(r,"usage",None)
        self.usage["calls"]+=1
        if u is not None:
            self.usage["prompt_tokens"]+=getattr(u,"prompt_tokens",0) or 0
            self.usage["completion_tokens"]+=getattr(u,"completion_tokens",0) or 0

    def json(self, system, user, temperature=0):
        r=self.client.chat.completions.create(model=self.model,temperature=temperature,response_format={"type":"json_object"},messages=[{"role":"system","content":system},{"role":"user","content":user}])
        self._track(r)
        return json.loads(r.choices[0].message.content)

    def text(self, system, user, temperature=0.1):
        r=self.client.chat.completions.create(model=self.model,temperature=temperature,messages=[{"role":"system","content":system},{"role":"user","content":user}])
        self._track(r)
        return r.choices[0].message.content
