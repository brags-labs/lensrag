from __future__ import annotations
import json, os

class LLMClient:
    """OpenAI-compatible chat-completions adapter; configure endpoint/model via env."""
    def __init__(self, model=None, api_key=None, base_url=None):
        try: from openai import OpenAI
        except ImportError as e: raise RuntimeError("LLM stages require: pip install openai") from e
        self.model=model or os.getenv("LENSRAG_LLM_MODEL","gpt-4o-mini")
        key=api_key or os.getenv("OPENAI_API_KEY")
        if not key: raise RuntimeError("Set OPENAI_API_KEY (or configure a compatible provider key).")
        self.client=OpenAI(api_key=key,base_url=base_url or os.getenv("OPENAI_BASE_URL"))
    def json(self, system, user, temperature=0):
        r=self.client.chat.completions.create(model=self.model,temperature=temperature,response_format={"type":"json_object"},messages=[{"role":"system","content":system},{"role":"user","content":user}])
        return json.loads(r.choices[0].message.content)
    def text(self, system, user, temperature=0.1):
        r=self.client.chat.completions.create(model=self.model,temperature=temperature,messages=[{"role":"system","content":system},{"role":"user","content":user}])
        return r.choices[0].message.content
