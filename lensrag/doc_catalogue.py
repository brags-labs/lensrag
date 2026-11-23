"""Document catalogue: questions about which documents exist, answered from index metadata.

"How many country addenda are there in version 3.0?", "How many circulars were issued in 2025?",
"Which countries were covered by version 1.0?", "Which countries were added in version 3.0?" ask
about the corpus's documents, not about what they say. Every document's type, title, version,
country, office and dates are already in the index; reading passages to rediscover them costs
minutes and miscounts. Here an LLM maps the question to a small query over one row per document
(filters, then a count, a list of distinct values, or a list minus another list) and code runs it.

The fields are generic chunk metadata, so no document type or field list is configured.
"""
from __future__ import annotations
import re
from collections import Counter

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def build_catalogue(chunks, display=None, global_values=("ALL", "GLOBAL", "")):
    """One row per document: {field: value}. display(type, code) -> name turns entity codes into
    names ('IN' -> 'India'), the way questions write them. A company-wide document has no country
    (its 'GLOBAL' marker is not a country to count or list)."""
    show = display or (lambda t, v: v)
    glob = {str(g).upper() for g in global_values}
    rows = {}
    for c in chunks:
        if c.doc_id in rows:
            continue
        meta = c.meta if isinstance(c.meta, dict) else {}
        row = {"document": c.doc_id, "document_type": str(c.doc_type or "").replace("_", " "),
               "title": meta.get("title") or "", "version": str(c.version or ""),
               "country": show("country", c.country) if c.country and str(c.country).upper() not in glob else "", "office": meta.get("office") or "",
               "effective_date": str(c.effective_date or ""), "issued": str(meta.get("issued") or ""),
               "status": str(c.status or "")}
        rows[c.doc_id] = {k: v for k, v in row.items() if v not in ("", None)}
    return list(rows.values())


def describe(rows, max_values=40, examples=8):
    """Field -> {values (all, when few) or examples, n} for the mapping prompt."""
    out = {}
    fields = Counter(k for r in rows for k in r)
    for k, n in fields.items():
        vals = Counter(r[k] for r in rows if k in r)
        info = {"documents_with_field": n}
        if len(vals) <= max_values:
            info["values"] = sorted(vals)
        else:
            info["examples"] = [v for v, _ in vals.most_common(examples)]
        if all(DATE.match(v) for v in vals):
            info["kind"] = "ISO date (compare with gte/gt/lte/lt, or contains a year)"
        out[k] = info
    return out


def _match(row, f):
    k, op, want = f.get("field"), f.get("op", "eq"), f.get("value")
    have = row.get(k)
    if op == "exists":            # the document has (or, with value false, lacks) the field
        return (have not in (None, "")) == (str(want).lower() not in ("false", "0", "no"))
    if have is None:
        return op == "ne"
    h = str(have).lower()
    if op in ("in", "not_in"):
        hit = h in [str(x).lower() for x in (want if isinstance(want, list) else [want])]
        return hit if op == "in" else not hit
    w = str(want).lower()
    if op in ("gte", "gt", "lte", "lt"):
        if DATE.match(h) and DATE.match(w):                    # ISO dates compare as strings
            return {"gte": h >= w, "gt": h > w, "lte": h <= w, "lt": h < w}[op]
        try:
            x, y = float(h), float(w)
        except ValueError:
            return False
        return {"gte": x >= y, "gt": x > y, "lte": x <= y, "lt": x < y}[op]
    if op == "contains":
        return w in h
    if op == "ne":
        return h != w
    return h == w


def select(rows, filters):
    return [r for r in rows if all(_match(r, f) for f in filters or [])]


def run(rows, q):
    """{operation: count|count_distinct|list, filters, target, minus_filters} -> (answer, matched rows).
    list = the distinct target values of the matching documents, minus those of the documents
    matching minus_filters ('countries in version 3.0 but not in version 2.0')."""
    op, target = q.get("operation"), q.get("target") or "document"
    hit = select(rows, q.get("filters"))
    if op == "count":
        return len(hit), hit
    vals = sorted({r[target] for r in hit if r.get(target)})
    if q.get("minus_filters"):
        drop = {r[target] for r in select(rows, q["minus_filters"]) if r.get(target)}
        vals = [v for v in vals if v not in drop]
        hit = [r for r in hit if r.get(target) in vals]
    if op == "count_distinct":
        return len(vals), hit
    if op == "list":
        return vals, hit
    return None, []
