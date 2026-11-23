"""Index-time labels for record logs whose free text states an opinion.

Exit conversations and survey comments carry their sentiment in prose ("The employee was warm
and positive throughout", "People are quietly looking at other options"). Questions such as
"the share of negative exit conversations after 1 April" or "the topics with the most negative
comments" need that sentiment for every record in scope. Labelling a sample at question time is
slow (minutes) and only estimates; labelling every record once, when the index is built, makes
the sentiment an ordinary record field that the exact field-query path counts in milliseconds.

The labels are cached next to the index (record_labels.json) with the model and prompt that
made them, so a later run reuses them and a changed prompt or model relabels.
"""
from __future__ import annotations
import hashlib, json, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LABELS = ("positive", "neutral", "negative", "mixed")
PROMPT = ("Label the overall sentiment each record expresses about the employer: positive, neutral, negative or "
          "mixed. Judge the person's own words and the interviewer's or respondent's described tone, not the "
          "topic alone (a comment about pay can be positive). mixed = clearly both. Return JSON "
          "{labels:[...]} with one label per record, in order.")
PROMPT_VERSION = hashlib.sha1(PROMPT.encode()).hexdigest()[:10]
MAX_CHARS = 1400


def record_key(r):
    return f"{r.doc_id}::{r.rid}"


def _batches(records, budget_chars=6000, max_items=25):
    batch, size = [], 0
    for r in records:
        n = min(len(r.text), MAX_CHARS)
        if batch and (size + n > budget_chars or len(batch) >= max_items):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += n
    if batch:
        yield batch


def label_batch(json_call, batch):
    """{key: label} for one batch; records the model leaves out or labels oddly are omitted."""
    texts = [{"index": i, "record": r.text[:MAX_CHARS]} for i, r in enumerate(batch)]
    out = json_call(PROMPT, json.dumps({"records": texts}, ensure_ascii=False)) or {}
    labels = out.get("labels") if isinstance(out, dict) else None
    if not isinstance(labels, list) or len(labels) != len(batch):
        return {}
    return {record_key(r): str(l).strip().lower() for r, l in zip(batch, labels) if str(l).strip().lower() in LABELS}


def label_records(records, json_call, model_name, path=None, workers=2, progress=print):
    """Label every record's sentiment, reusing a cache at path made by the same model and prompt.
    Batches that come back malformed are retried one record at a time. Returns {key: label}."""
    cache = load_labels(path, model_name) if path else {}
    todo = [r for r in records if record_key(r) not in cache and r.text]
    batches = list(_batches(todo))
    done, t0 = 0, time.time()

    def run(batch):
        got = label_batch(json_call, batch)
        for r in batch:   # a malformed batch: label its records one at a time
            if record_key(r) not in got:
                got.update(label_batch(json_call, [r]))
        return got

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(run, batches):
            cache.update(got)
            done += 1
            if path and (done % 10 == 0 or done == len(batches)):
                save_labels(path, cache, model_name)
            if progress and (done % 10 == 0 or done == len(batches)):
                progress(f"labelled {len(cache)} records; batch {done}/{len(batches)}; {time.time() - t0:.0f}s")
    if path:
        save_labels(path, cache, model_name)
    return cache


def load_labels(path, model_name=None):
    """Cached labels, or {} when missing or made by another model or prompt."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    if data.get("prompt_version") != PROMPT_VERSION or (model_name and data.get("model") != model_name):
        return {}
    return data.get("labels", {})


def save_labels(path, labels, model_name):
    Path(path).write_text(json.dumps({"model": model_name, "prompt_version": PROMPT_VERSION, "labels": labels}))


def apply_labels(records, labels, field="sentiment"):
    """Add each labelled record's sentiment as a field. Returns how many were labelled."""
    n = 0
    for r in records:
        lab = labels.get(record_key(r))
        if lab:
            r.fields[field] = lab
            n += 1
    return n
