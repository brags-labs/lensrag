"""Open-source, self-hosted components from the report's Table 3.1 that aren't LLMs.

  Reranker             Search + rerank: a cross-encoder (default BAAI/bge-reranker-v2-m3)
                       reorders candidate passages for local questions.
  EntityNER            Select relevant entities: spaCy NER (default en_core_web_sm) finds names
                       the entity-list lookup missed (spelling variants, possessives) and
                       fuzzy-matches them to the inventory.
  NLIVerifier          Verify evidence: an NLI cross-encoder (default
                       cross-encoder/nli-deberta-v3-large) checks each answer sentence against
                       the evidence: entailed, contradicted or unsupported.
  SentimentClassifier  Map-reduce per-record labels: a RoBERTa sentiment classifier (default
                       cardiffnlp/twitter-roberta-base-sentiment-latest) gives P(negative) per
                       record, used as soft labels in Mode B estimates.

Every component loads its model on first use and accepts an injected `model` (or `nlp`),
so tests can use stand-ins. Model names are recorded on each instance for the report.
"""
from __future__ import annotations
import difflib
import re

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"
DEFAULT_SPACY = "en_core_web_sm"
DEFAULT_NLI = "cross-encoder/nli-deberta-v3-large"
DEFAULT_SENTIMENT = "cardiffnlp/twitter-roberta-base-sentiment-latest"


# --- Search + rerank -------------------------------------------------------------------------
class Reranker:
    def __init__(self, model_name=DEFAULT_RERANKER, model=None, max_chars=2000):
        self.model_name, self._model, self.max_chars = model_name, model, max_chars

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def rerank(self, question, items, top):
        """items: [(chunk, score)] -> the `top` best by cross-encoder score, as [(chunk, score)]."""
        if not items:
            return []
        scores = self.model.predict([(question, c.enriched_text[:self.max_chars]) for c, _ in items], batch_size=16)
        order = sorted(range(len(items)), key=lambda i: (-float(scores[i]), i))
        return [(items[i][0], float(scores[i])) for i in order[:top]]


# --- Select relevant entities --------------------------------------------------------------------
NER_LABELS = {"GPE", "LOC", "ORG", "NORP", "FAC", "PERSON"}


class EntityNER:
    """spaCy NER fallback for entity selection: names the lookup missed, matched fuzzily."""
    def __init__(self, model_name=DEFAULT_SPACY, nlp=None, min_ratio=0.85):
        self.model_name, self._nlp, self.min_ratio = model_name, nlp, min_ratio

    @property
    def nlp(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def mentions(self, text):
        return [(e.text, e.label_) for e in self.nlp(text).ents if e.label_ in NER_LABELS]

    def match(self, question, inventory, domain):
        """{entity type: [values]} for NER mentions that fuzzy-match an inventory name or alias."""
        out = {}
        mentions = [re.sub(r"(?:'s|’s)$", "", m).strip() for m, _ in self.mentions(question)]
        for t in domain.entity_types:
            items = inventory.get("entities", {}).get(t.name, [])
            names = {e["name"]: e["value"] for e in items}
            names.update({alias: names[full] for alias, full in t.aliases.items() if full in names})
            for m in mentions:
                best = difflib.get_close_matches(m, list(names), n=1, cutoff=self.min_ratio) or \
                       difflib.get_close_matches(m.lower(), [n.lower() for n in names], n=1, cutoff=self.min_ratio)
                if best:
                    hit = next(n for n in names if n.lower() == best[0].lower())
                    if names[hit] not in out.setdefault(t.name, []):
                        out[t.name].append(names[hit])
        return {k: v for k, v in out.items() if v}


# --- Verify evidence -----------------------------------------------------------------------------
_CITATION = re.compile(r"\[[^\]]*\]")
_SENT = re.compile(r"(?<=[.!?])\s+")


def claims_of(answer, min_words=5):
    """Answer sentences worth checking, without citations and [exact]/[estimated] labels."""
    out = []
    for s in _SENT.split(str(answer)):
        s = _CITATION.sub("", s).strip(" -*•\n")
        if len(s.split()) >= min_words:
            out.append(s)
    return out


def linearize_tables(text):
    """Rewrite Markdown table rows as sentences, which NLI models read far better than pipes.

    "| Paid annual leave (working days) | 28 |" under a header "| Entitlement | Value |"
    becomes "Paid annual leave (working days): Value 28." Other lines are kept as they are.
    """
    out, header = [], None
    for line in str(text).splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            out.append(line); header = None; continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        if header is None:
            header = cells; continue
        first, rest = cells[0], cells[1:]
        names = header[1:] if len(header) == len(cells) else [""] * len(rest)
        parts = [f"{n} {v}".strip() if n and len(rest) > 1 else v for n, v in zip(names, rest)]
        out.append(f"{first}: {', '.join(p for p in parts if p)}.")
    return "\n".join(out)


def focus_premise(evidence, claim, lines=4):
    """A short premise for NLI: the chunk's context header (scope, version, entities) plus the
    `lines` lines most similar to the claim, with tables written as sentences. Long chunks
    would otherwise be truncated before the relevant row, and the header is often the only
    place the entity (e.g. the country) is named."""
    text = linearize_tables(evidence)
    first, _, body = text.partition("\n")
    header = ""
    if first.startswith("Document:"):
        fields = dict(f.split(":", 1) for f in first.split(" | ") if ":" in f)
        keep = [f"{k.strip()}: {v.strip()}" for k, v in fields.items()
                if k.strip() in ("Document", "Section", "Version", "Effective date", "Status", "Entities") and v.strip() != "unspecified"]
        header = "; ".join(keep) + ". "
    else:
        body = text
    rows = [r.strip() for r in re.split(r"\n|(?<=[.!?])\s+", body) if r.strip()]
    best = sorted(range(len(rows)), key=lambda i: (-_overlap(claim, rows[i]), i))[:lines]
    return header + " ".join(rows[i] for i in sorted(best))


def _overlap(a, b):
    wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(wa & wb) / (len(wa) or 1)


class NLIVerifier:
    """Checks each answer claim against the best-matching evidence passages with an NLI model."""
    def __init__(self, model_name=DEFAULT_NLI, model=None, entail_threshold=0.5, contradict_threshold=0.5,
                 candidates=4, max_chars=1500, focus_lines=4):
        self.model_name, self._model = model_name, model
        self.entail_threshold, self.contradict_threshold = entail_threshold, contradict_threshold
        self.candidates, self.max_chars, self.focus_lines = candidates, max_chars, focus_lines

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def _labels(self):
        cfg = getattr(self.model, "config", None) or getattr(getattr(self.model, "model", None), "config", None)
        id2label = getattr(cfg, "id2label", None) or {0: "contradiction", 1: "entailment", 2: "neutral"}
        return {int(i): str(l).lower() for i, l in id2label.items()}

    def verify(self, answer, evidence):
        """evidence: list of passage texts. Returns per-claim verdicts and a summary."""
        import numpy as np
        claims = claims_of(answer)
        evidence = [e for e in evidence if e]
        if not claims or not evidence:
            return {"model": self.model_name, "claims": [], "supported_share": None, "contradicted": [], "unsupported": []}
        labels = self._labels()
        ent = next(i for i, l in labels.items() if l.startswith("entail"))
        con = next(i for i, l in labels.items() if l.startswith("contra"))
        pairs, owners = [], []
        for ci, claim in enumerate(claims):
            best = sorted(evidence, key=lambda e: -_overlap(claim, e))[:self.candidates]
            best = [focus_premise(e, claim, self.focus_lines) for e in best]
            for e in best:
                pairs.append((e[:self.max_chars], claim)); owners.append(ci)
        logits = np.asarray(self.model.predict(pairs, batch_size=8), dtype=float)
        probs = np.exp(logits - logits.max(axis=1, keepdims=True)); probs /= probs.sum(axis=1, keepdims=True)
        verdicts = []
        for ci, claim in enumerate(claims):
            rows = [probs[i] for i, o in enumerate(owners) if o == ci]
            p_ent = max(r[ent] for r in rows); p_con = max(r[con] for r in rows)
            status = ("entailed" if p_ent >= self.entail_threshold else
                      "contradicted" if p_con >= self.contradict_threshold else "unsupported")
            verdicts.append({"claim": claim, "entailment": round(float(p_ent), 3), "contradiction": round(float(p_con), 3),
                             "status": status})
        return {"model": self.model_name, "claims": verdicts,
                "supported_share": sum(v["status"] == "entailed" for v in verdicts) / len(verdicts),
                "contradicted": [v["claim"] for v in verdicts if v["status"] == "contradicted"],
                "unsupported": [v["claim"] for v in verdicts if v["status"] == "unsupported"]}


# --- Per-record sentiment labels -----------------------------------------------------------------
class SentimentClassifier:
    """P(negative) per text, from a RoBERTa sentiment classifier; used as Mode B soft labels."""
    def __init__(self, model_name=DEFAULT_SENTIMENT, model=None, batch_size=16):
        self.model_name, self._model, self.batch_size = model_name, model, batch_size

    @property
    def model(self):
        if self._model is None:
            from transformers import pipeline
            self._model = pipeline("text-classification", model=self.model_name, top_k=None,
                                   truncation=True, max_length=512)
        return self._model

    def negative_probs(self, texts):
        out = []
        for i in range(0, len(texts), self.batch_size):
            for scores in self.model(list(texts[i:i + self.batch_size])):
                by_label = {str(s["label"]).lower(): float(s["score"]) for s in scores}
                out.append(next((v for k, v in by_label.items() if k.startswith("neg") or k in ("label_0",)), 0.0))
        return out
