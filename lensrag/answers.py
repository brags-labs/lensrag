"""Answer-level evaluation for H2: exact match and set-level F1 against the gold answers.

`score_answer` compares a predicted answer with the gold answer in the gold's own format
(value, ratio, set, list, tuple, ranked_list, text). `run_answers` answers the gold
questions with each method and an LLM, and writes `answers.csv`. It needs a configured
LLM: Claude (ANTHROPIC_API_KEY) or an OpenAI-compatible endpoint (OPENAI_API_KEY /
OPENAI_BASE_URL); see lensrag/full/providers.py.

Methods:
  rag_topk            standard RAG: hybrid top-k chunks, then one LLM answer
  long_context_128k   whole documents packed in corpus order into a 128k window
  long_context_1m     the same with a 1M window
  lensrag             the full LensRAG pipeline (lensrag.full), answer converted to the gold format
"""
from __future__ import annotations
import ast, json, os, re, time
from pathlib import Path
import pandas as pd
from .aggregation import normalize_label
from .full.routing import role

FORMAT_INSTRUCTIONS = {
    "value": "a single number (no units) or, if not numeric, a short string",
    "ratio": "a number between 0 and 1",
    "set": "a JSON list of names, in any order",
    "list": "a JSON list of names",
    "tuple": "a JSON list [name, number]",
    "ranked_list": "a JSON list of [name, number] pairs in ranked order",
    "text": "one sentence that starts with 'Yes' or 'No' when the question is a yes/no question",
}


# --- scoring ----------------------------------------------------------------------------
def _norm(x) -> str:
    s = str(x).casefold().replace("&", " and ")
    s = re.sub(r"^the\s+", "", s.strip())
    return re.sub(r"[^a-z0-9.%₹$ ]+", " ", s).strip().replace("  ", " ")


def _num(x, ratio=False):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(x))
        if not m:
            return None
        v = float(m.group(0).replace(",", ""))
        if ratio and "%" in str(x):
            v /= 100
    if ratio and v > 1:
        v /= 100
    return v


def _num_eq(a, b):
    return a is not None and b is not None and abs(a - b) <= max(0.01 * abs(b), 0.005)


_CURRENCY = "₹$€£"
_AMOUNT = re.compile(rf"^\s*[{_CURRENCY}]?\s*-?\d[\d,]*(?:\.\d+)?\s*$")


def _item_eq(pred, gold, ratio=False):
    g, p = _num(gold, ratio), _num(pred, ratio)
    if isinstance(gold, (int, float)) and not isinstance(gold, bool):
        return _num_eq(p, g)
    if isinstance(gold, str) and _AMOUNT.match(gold) and _AMOUNT.match(str(pred)):
        # "₹600" vs "600": the same amount; a different currency symbol is still wrong.
        gs, ps = [c for c in gold if c in _CURRENCY], [c for c in str(pred) if c in _CURRENCY]
        return _num_eq(p, g) and (not ps or ps == gs)
    return _norm(pred) == _norm(gold) and _norm(gold) != ""


def _from_dict(d):
    """{"name": "Germany", "number": 20} (or similar keys) -> ["Germany", 20]; other dicts unchanged."""
    if not isinstance(d, dict):
        return d
    text = next((v for v in d.values() if isinstance(v, str)), None)
    num = next((v for v in d.values() if isinstance(v, (int, float)) and not isinstance(v, bool)), None)
    if text is not None and num is not None:
        return [text, num]
    return text if text is not None else num if num is not None else d


def _as_list(x):
    if isinstance(x, dict):  # one object is the answer itself: {"name": "US", "weeks": 8} -> ["US", 8]
        v = _from_dict(x)
        return v if isinstance(v, list) else [v]
    if isinstance(x, list):
        return [_from_dict(i) for i in x]
    if isinstance(x, str):
        try:
            v = json.loads(x)
            return v if isinstance(v, list) else [v]
        except Exception:
            return [s for s in re.split(r",|;|\band\b", x) if s.strip()]
    return [x]


def _set_scores(pred_items, gold_items):
    p = {_norm(x) for x in pred_items if _norm(x)}
    g = {_norm(x) for x in gold_items if _norm(x)}
    if not g:
        return float(not p), float(not p)
    tp = len(p & g)
    prec = tp / len(p) if p else 0.0
    rec = tp / len(g)
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return float(p == g), f1


def score_answer(pred, gold, fmt):
    """Return (exact_match, set_f1); (None, None) when the format can't be scored automatically."""
    if pred is None:
        return 0.0, 0.0
    if fmt in ("value", "ratio"):
        if isinstance(pred, list) and len(pred) == 1:
            pred = pred[0]
        em = float(_item_eq(pred, gold, ratio=fmt == "ratio"))
        return em, em
    if fmt in ("set", "list"):
        return _set_scores(_as_list(pred), _as_list(gold))
    if fmt == "tuple":
        p, g = _as_list(pred), _as_list(gold)
        matches = [i < len(p) and _item_eq(p[i], g[i]) for i in range(len(g))]
        return float(all(matches) and len(p) == len(g)), sum(matches) / len(g)
    if fmt == "ranked_list":
        p = [x if isinstance(x, list) else [x] for x in _as_list(pred)]
        g = _as_list(gold)
        names_p, names_g = [_norm(x[0]) for x in p], [_norm(x[0]) for x in g]
        values_ok = all(len(pi) > 1 and _item_eq(pi[1], gi[1]) for pi, gi in zip(p, g)) and len(p) == len(g)
        _, f1 = _set_scores(names_p, names_g)
        return float(names_p == names_g and values_ok), f1
    if fmt == "text":
        m = re.match(r"\s*(yes|no)\b", str(gold), re.I)
        if not m:
            return None, None  # free text: needs a human or LLM judge
        ok = bool(re.match(rf"\s*{m.group(1)}\b", str(pred), re.I))
        return float(ok), float(ok)
    return None, None


# --- interval coverage (Mode B estimates) -------------------------------------------------
def _groups_in_order(estimate):
    groups = (estimate or {}).get("groups") or {}
    order = (estimate or {}).get("order")
    if order and set(groups) <= set(order):  # field queries keep the question's own order
        return [groups[k] for k in order if k in groups]
    def key(k):
        try:
            return tuple(ast.literal_eval(k))
        except Exception:
            return (k,)
    return [groups[k] for k in sorted(groups, key=key)]


def _within(x, lo, hi):
    if x is None or lo is None or hi is None:
        return None
    eps = 0.005 * abs(x) + 1e-9
    return lo - eps <= x <= hi + eps


def _category_interval(group, name):
    """(found, count_low, count_high) for a category in a category-share estimate."""
    pop = group.get("population") or group.get("n") or 0
    for c in group.get("categories", []):
        if _norm(c["category"]) == _norm(name) or normalize_label(c["category"]) == normalize_label(name):
            return True, c["ci_low"] * pop, c["ci_high"] * pop
    return False, None, None


def interval_coverage(estimate, gold, fmt):
    """Does the gold answer fall inside the pipeline's 95% intervals?

    Returns {"covered": fraction of gold targets inside their interval (None when the answer
    has no estimate to check), "targets": n, "details": [...]}. Targets by gold format:
      value / ratio            the main estimate (one group) or the single group's interval
      tuple [a, b] of numbers  two period groups in time order (before, after)
      tuple [category, count]  the category must be found and the count inside its share interval x population
      ranked_list              each [category, count] item as above
    """
    groups = _groups_in_order(estimate)
    if not groups:
        return {"covered": None, "targets": 0, "details": []}
    details = []
    if fmt in ("value", "ratio") and _num(gold, fmt == "ratio") is not None:
        g = groups[0]
        x = _num(gold, fmt == "ratio")
        details.append({"target": x, "ci": [g.get("ci_low"), g.get("ci_high")], "covered": _within(x, g.get("ci_low"), g.get("ci_high"))})
    elif fmt == "tuple" and isinstance(gold, list) and len(gold) == 2 and all(_num(v) is not None and not isinstance(v, str) for v in gold):
        for x, g in zip(gold, groups[:2]):
            details.append({"target": x, "ci": [g.get("ci_low"), g.get("ci_high")], "covered": _within(float(x), g.get("ci_low"), g.get("ci_high"))})
    elif fmt in ("tuple", "ranked_list"):
        items = [gold] if fmt == "tuple" else gold
        for item in items:
            if not isinstance(item, list) or len(item) < 2 or "categories" not in groups[0]:
                continue
            found, lo, hi = _category_interval(groups[0], item[0])
            details.append({"target": item, "category_found": found, "ci": [lo, hi],
                            "covered": bool(found and _within(float(item[1]), lo, hi))})
    checked = [d["covered"] for d in details if d["covered"] is not None]
    return {"covered": (sum(checked) / len(checked)) if checked else None, "targets": len(checked), "details": details}


# --- runner ------------------------------------------------------------------------------
def _ask(llm, question, fmt, context):
    # The context goes in the system prompt and the question last, so a context shared by many
    # questions (the long-context corpus) is a stable prefix that the provider can cache.
    system = ("Answer the HR question using only the context below. If the context is insufficient, give your best "
              "answer from it anyway.\n\nCONTEXT:\n" + json.dumps(context, ensure_ascii=False))
    out = role(llm, "answer").json(system, json.dumps({"question": question, "answer_format": "Return JSON {\"answer\": ...} where answer is "
                                       + FORMAT_INSTRUCTIONS.get(fmt, "a short answer")}, ensure_ascii=False))
    return out.get("answer")


_ASKS_COUNT = re.compile(r"\bhow many\b|\bnumber of\b|\bcount\b", re.I)
_ASKS_SHARE = re.compile(r"\bshare\b|\bproportion\b|\bpercent|\bfraction\b|\brate\b|\bratio\b", re.I)


def _point(group, question, fmt):
    """A group's point estimate as a count or a share, whichever the question asks for."""
    est, pop = group.get("estimate"), group.get("population")
    if est is None:
        return None
    is_share = "share" in str(group.get("what", "")) or "proportion" in str(group.get("what", ""))
    if is_share and pop and fmt != "ratio" and _ASKS_COUNT.search(question):
        return round(est * pop)
    if not is_share and "number of" in str(group.get("what", "")) and pop and (fmt == "ratio" or _ASKS_SHARE.search(question)):
        return est / pop
    return round(est, 3) if isinstance(est, float) else est


def answer_from_estimate(estimate, question, fmt):
    """The answer in the gold format, read straight from a Mode B estimate (None when the
    estimate's shape doesn't fit the format). Asking the LLM to restate an estimate loses it:
    small models answer "unsupported" even when the estimate is there."""
    groups = _groups_in_order(estimate)
    if not groups:
        return None
    if "categories" in groups[0]:
        g = groups[0]
        cats = sorted(g["categories"], key=lambda c: -c["estimate"])
        pop = g.get("population") or g.get("n") or 0
        values = g.get("values_are") not in (None, "counts")   # means or shares: the value itself
        def item(c):
            if values:
                return [c["category"], round(c["count"], 3)]
            return [c["category"], round(c["estimate"], 3) if _ASKS_SHARE.search(question) else round(c["estimate"] * pop)]
        if fmt == "tuple" and cats:
            return item(cats[0])
        if fmt == "ranked_list":
            return [item(c) for c in cats]
        if fmt in ("set", "list"):
            return [c["category"] for c in cats]
        return None
    if fmt in ("value", "ratio") and len(groups) == 1:
        return _point(groups[0], question, fmt)
    if fmt == "tuple" and len(groups) == 2:  # before / after periods, in time order
        pts = [_point(g, question, fmt) for g in groups]
        return pts if None not in pts else None
    return None


def answer_from_aggregate(result, fmt):
    """The requested format, in code, from a computed fact-table result; None if it doesn't fit."""
    a = result.get("deterministic_result")
    if a is None:
        return None
    def val(r):
        v = r.get("value")
        return int(v) if isinstance(v, float) and v.is_integer() else v
    if isinstance(a, dict) and "changed" in a:
        if fmt in ("set", "list") and len(a["versions"]) == 2:
            return a["changed"]
        if fmt == "value" and len(a["by_version"]) == 1 and len(a["versions"]) == 2:
            vals = next(iter(a["by_version"].values()))
            x, y = (vals.get(v) for v in a["versions"])
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                d = y - x
                return int(d) if float(d).is_integer() else round(d, 3)
            return None
        if fmt == "list" and len(a["by_version"]) == 1:
            vals = next(iter(a["by_version"].values()))
            return [int(x) if isinstance(x, float) and x.is_integer() else x for x in (vals.get(v) for v in a["versions"])]
        return None
    if isinstance(a, dict) and "count" in a:
        return a["count"] if fmt == "value" else None
    rows = [a] if isinstance(a, dict) and "entity" in a else a if isinstance(a, list) else None
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return a if fmt == "value" else None
    if not rows or not all(isinstance(r, dict) and "entity" in r for r in rows):
        return None
    if fmt == "value":
        if len(rows) != 1:
            return None
        v = val(rows[0])
        return v if isinstance(v, (int, float)) else rows[0].get("value_as_written", v)
    if fmt == "set":
        return list(dict.fromkeys(r["entity"] for r in rows))
    if fmt == "tuple":
        return [rows[0]["entity"], val(rows[0])] if len(rows) == 1 else None
    if fmt == "ranked_list":
        return [[r["entity"], val(r)] for r in rows]
    return None


def _to_format(llm, question, fmt, result):
    if result.get("answer_source") == "fact table":
        pred = answer_from_aggregate(result, fmt)
        if pred is not None:
            return pred
    est = result.get("estimate") or {}
    if result.get("computation_mode") == "estimated" or est.get("field_query"):
        pred = answer_from_estimate(result.get("estimate"), question, fmt)
        if pred is not None:
            return pred
    out = role(llm, "extract").json("Convert this answer to the requested format without changing its content. Return JSON "
                   "{\"answer\": ...} where answer is " + FORMAT_INSTRUCTIONS.get(fmt, "a short answer") + ".",
                   json.dumps({"question": question, "answer": result.get("answer"),
                               "deterministic_result": result.get("deterministic_result"),
                               "estimate": result.get("estimate")}, ensure_ascii=False, default=str))
    return out.get("answer")


def reformat_estimates(path, questions):
    """Re-derive and re-score LensRAG answers that have a stored Mode B estimate, without
    rerunning the pipeline (the estimate is saved in answers.csv). Returns the rows changed."""
    df = pd.read_csv(path)
    by_qid = {q["qid"]: q for q in questions}
    changed = []
    for i, r in df.iterrows():
        if r.method != "lensrag" or r.get("computation_mode") != "estimated" or not isinstance(r.estimate, str) or not r.estimate:
            continue
        q = by_qid.get(r.qid)
        pred = answer_from_estimate(json.loads(r.estimate), q["question"], r.answer_format) if q else None
        if pred is None:
            continue
        em, f1 = score_answer(pred, q["answer"], r.answer_format)
        new = json.dumps(pred, ensure_ascii=False, default=str)
        if new != r.prediction:
            changed.append({"qid": r.qid, "before": r.prediction, "after": new, "gold": r.gold,
                            "exact_match": (r.exact_match, em)})
        df.loc[i, ["prediction", "exact_match", "set_f1"]] = [new, em, f1]
    df.to_csv(path, index=False)
    return changed


def run_answers(zip_path, extract_dir, output, tier="L", methods=("rag_topk", "long_context_128k", "lensrag"),
                top_k=10, llm=None, llm_model=None, llm_provider=None, llm_stack=None, domain="hr", index_dir=None, limit=None, store_dir=None,
                lexical_fallback=False, qids=None, resume=True):
    """Answer every eligible gold question with each method and score it; writes answers.csv.

    Each answer is appended to answers.csv as soon as it is scored. With `resume`, answers
    already in the file without an error are skipped, so an interrupted run continues where it
    stopped. Standard RAG uses the same embedding model as LensRAG when the stack sets one.
    """
    from .data import ensure_extracted, load_documents, load_gold, chunk_document
    from .domain import load_domain
    from .experiment import tier_index, LONG_CONTEXT_WINDOWS, TokenCounter, long_context_docs
    from .full.providers import create_llm
    dom = load_domain(domain)
    llm = llm or create_llm(llm_provider, llm_model, llm_stack)
    corpus = ensure_extracted(Path(zip_path), Path(extract_dir))
    docs = load_documents(corpus, tier, dom)
    by_id = {d.doc_id: d for d in docs}
    gold = [q for q in load_gold(corpus) if "SML".index(q.get("min_tier", "S")) <= "SML".index(tier)
            and (not qids or q["qid"] in qids)][:limit]
    count = TokenCounter()
    doc_tokens = {d.doc_id: count(("doc", d.doc_id), d.text) for d in docs}
    index = None
    pipe = None
    from .full.pipeline import LensRAGPipeline, PipelineConfig, apply_stack_components
    llm_stack = llm_stack or os.getenv("LENSRAG_LLM_STACK") or None  # same source as create_llm
    cfg = apply_stack_components(PipelineConfig(tier=tier, domain=dom.source, llm_stack=llm_stack))
    if os.getenv("LENSRAG_FAST", "").lower() in ("1", "true", "yes"):  # low-latency profile
        from .full.pipeline import fast_config
        cfg = fast_config(cfg)
    stack_embedding = cfg.embedding_model if llm_stack and not lexical_fallback else None
    if "rag_topk" in methods:
        if stack_embedding:  # same dense model as LensRAG, for a like-for-like baseline
            from .embeddings import DenseEncoder
            index, _, _ = tier_index(docs, tier, store_dir, "dense", DenseEncoder(stack_embedding), dom)
        else:
            index, _, _ = tier_index(docs, tier, store_dir, "tfidf", None, dom)
    if "lensrag" in methods:
        from .full.index import PersistentHybridIndex
        from .planning import build_inventory
        if index_dir and (Path(index_dir) / "metadata.json").exists():
            pipe = LensRAGPipeline.load(index_dir, cfg, use_llm=False)
        else:
            chunks = [c for d in docs for c in chunk_document(d, domain=dom)]
            if lexical_fallback:
                idx = PersistentHybridIndex(chunks, allow_lexical_fallback=True)
            else:
                from .embeddings import DenseEncoder
                idx = PersistentHybridIndex(chunks, encoder=DenseEncoder(cfg.embedding_model))
            pipe = LensRAGPipeline(idx, build_inventory(docs, dom), None, cfg)
        pipe.llm = llm
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    path = out / "answers.csv"
    done = set()
    if resume and path.exists():
        prev = pd.read_csv(path)
        ok = prev[prev.error.isna() | (prev.error.astype(str) == "")] if "error" in prev else prev
        prev = ok  # failed answers are retried
        prev.to_csv(path, index=False)
        done = set(zip(prev.tier, prev.qid, prev.method))
    elif path.exists():
        path.unlink()
    meta = {"tier": tier, "methods": list(methods), "llm_provider": type(llm).__name__,
            "llm_model": getattr(llm, "model", None), "llm_effort": getattr(llm, "effort", None), "top_k": top_k,
            "questions": len(gold), "domain": dom.name,
            "rag_topk_retrieval": f"hybrid BM25 + {stack_embedding}" if stack_embedding else "hybrid BM25 + TF-IDF",
            "lensrag_components": {k: getattr(cfg, k) for k in ("embedding_model", "reranker_model", "spacy_model",
                                                                "nli_model", "sentiment_model")},
            "lensrag_index": str(index_dir) if index_dir else "built in memory"}
    (out / "answers_config.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    rows = []
    # Method by method, so consecutive calls share a prompt prefix (the long-context corpus)
    # and stay within the provider's prompt-cache lifetime.
    for method in methods:
        for q in gold:
            if (tier, q["qid"], method) in done:
                continue
            fmt = q.get("answer_format", "value")
            scope = "local" if q["type"] == "local" else "global"
            llm.reset_usage() if hasattr(llm, "reset_usage") else None
            t0 = time.perf_counter(); pred, err = None, ""; result = {}
            try:
                if method == "rag_topk":
                    hits = index.search(q["question"], top_k)
                    pred = _ask(llm, q["question"], fmt, [{"doc_id": c.doc_id, "text": c.enriched_text} for c, _ in hits])
                elif method in LONG_CONTEXT_WINDOWS:
                    ids, _ = long_context_docs(docs, doc_tokens, LONG_CONTEXT_WINDOWS[method])
                    pred = _ask(llm, q["question"], fmt, [{"doc_id": i, "text": by_id[i].text} for i in ids])
                elif method == "lensrag":
                    result = pipe.ask(q["question"])
                    pred = _to_format(llm, q["question"], fmt, result)
                else:
                    raise ValueError(method)
            except Exception as e:  # record failures (e.g. context too long) instead of aborting the run
                err = f"{type(e).__name__}: {e}"[:300]
            em, f1 = score_answer(pred, q["answer"], fmt) if not err else (0.0, 0.0)
            cov = interval_coverage(result.get("estimate"), q["answer"], fmt) if result else {"covered": None, "targets": 0}
            usage = getattr(llm, "usage", {}) or {}
            rows.append({"tier": tier, "qid": q["qid"], "method": method, "query_type": q["type"], "scope": scope,
                         "answer_format": fmt, "prediction": json.dumps(pred, ensure_ascii=False, default=str),
                         "computation_mode": result.get("computation_mode", "") if result else "",
                         "planned_type": result.get("query_type", "") if result else "",
                         "answer_source": (result.get("answer_source") or "record fields" if (result.get("estimate") or {}).get("field_query") or result.get("answer_source") else
                                           "estimate" if result.get("estimate") else "llm") if result else "",
                         "interval_covered": cov["covered"], "interval_targets": cov["targets"],
                         "estimate": json.dumps(result.get("estimate"), default=str) if result and result.get("estimate") else "",
                         "gold": json.dumps(q["answer"], ensure_ascii=False), "exact_match": em, "set_f1": f1,
                         "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
                         "total_tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
                         "cache_read_tokens": usage.get("cache_read_tokens", 0),
                         "cache_write_tokens": usage.get("cache_write_tokens", 0),
                         "llm_calls": usage.get("calls", 0), "latency_s": time.perf_counter() - t0, "error": err,
                         "usage_by_role": json.dumps(usage.get("by_role", {})) if usage.get("by_role") else ""})
            # Checkpoint: append this answer now, so an interrupted run loses at most one question.
            pd.DataFrame(rows[-1:]).to_csv(path, mode="a", header=not path.exists(), index=False)
    return pd.read_csv(path)
