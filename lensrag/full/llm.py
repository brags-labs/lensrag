from __future__ import annotations
import json, os, threading


_LOCK=threading.Lock()


def _tls(client):
    if "_tls" not in client.__dict__:
        with _LOCK:
            client.__dict__.setdefault("_tls",threading.local())
    return client.__dict__["_tls"]


def record_call(client, d):
    """Add one call's usage to client.usage (thread-safe) and remember it as this thread's last call."""
    with _LOCK:
        for k,v in d.items():
            client.usage[k]=client.usage.get(k,0)+v
    _tls(client).last=d


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
        d={"calls":1,"prompt_tokens":getattr(u,"prompt_tokens",0) or 0 if u is not None else 0,
           "completion_tokens":getattr(u,"completion_tokens",0) or 0 if u is not None else 0}
        record_call(self,d)

    def last_call_usage(self):
        """This thread's last call's usage: exact when several threads share the client."""
        return getattr(_tls(self),"last",None)

    def _create(self, **kw):
        """chat.completions.create with one retry when a local server aborts a repetition loop
        (Ollama: "token repeat limit reached"). Greedy decoding loops the same way every time,
        so the retry samples a little and penalises repeated tokens."""
        try:
            return self.client.chat.completions.create(model=self.model,**kw)
        except Exception as e:
            if "repeat" not in str(e).lower():
                raise
            self.usage["repeat_retries"]=self.usage.get("repeat_retries",0)+1
            kw.update(temperature=max(kw.get("temperature") or 0,0.4),frequency_penalty=0.5,max_tokens=kw.get("max_tokens") or 2048)
            return self.client.chat.completions.create(model=self.model,**kw)

    def json(self, system, user, temperature=0):
        r=self._create(temperature=temperature,response_format={"type":"json_object"},messages=[{"role":"system","content":system},{"role":"user","content":user}])
        self._track(r)
        return json.loads(r.choices[0].message.content)

    def text(self, system, user, temperature=0.1):
        r=self._create(temperature=temperature,messages=[{"role":"system","content":system},{"role":"user","content":user}])
        self._track(r)
        return r.choices[0].message.content
