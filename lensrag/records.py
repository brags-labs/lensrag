"""Record-aware ingestion: semi-structured record logs parsed into field tables, schema-free.

Record logs (helpdesk tickets, grievance cases, exit interviews, survey comments) state most
facts as labelled fields, for example

    ### Ticket HD-AE-202511-0001 — Travel and relocation
    **Opened:** 03 November 2025 · **Country:** United Arab Emirates · **CSAT:** 3/5
    **Outcome.** Resolved informally. Action: ...
    **PULSE26-AE-0001** · Dubai · L2 · likelihood to recommend: 2/10
    *Topic tagged by respondent:* Recognition

Counting, averaging or ranking such fields with an LLM over a sample is slow and error-prone;
reading them is exact. This module finds record blocks and their fields with generic patterns
(no field list is configured), builds a field catalogue per record type for the planner, and
runs a small structured query (filters, operation, grouping) over the records in code.

A record block starts at a `### ` heading or at a line that opens with a bold identifier
(`**ID-123**`). Its fields are:
  title        the heading text after the id (` — ` separated), e.g. a ticket category
  **Key:** v   bold key, colon inside or outside the bold
  **Key.** v   bold key ending in a full stop: the first sentence of the value
  *Key:* v     italic key
  key: v       inside a ` · ` separated line
"""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

_HEAD = re.compile(r"^#{2,4}\s+(?P<head>.+?)\s*$")
_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}$")
_BOLD_ID = re.compile(r"^\*\*(?P<id>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\*\*")
_BOLD_FIELD = re.compile(r"\*\*(?P<k>[^*]{1,40}?)(?::\*\*|\*\*:)\s*(?P<v>.*?)(?=\s+·\s+\*\*|\s*$)")
_BOLD_SENT = re.compile(r"^\*\*(?P<k>[^*]{1,40}?)\.\*\*\s*(?P<v>[^.]{1,80})")
_ITAL_FIELD = re.compile(r"^\*(?P<k>[^*]{1,60}?):\*\s*(?P<v>.+?)\s*$")
_PLAIN_FIELD = re.compile(r"^(?P<k>[A-Za-z][A-Za-z /-]{1,40}):\s*(?P<v>.+)$")
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"], 1)}


def norm_key(k):
    return re.sub(r"[^a-z0-9]+", "_", k.strip().lower()).strip("_")


def parse_value(v):
    """(raw, number or None, date or None). '3/5' -> 3, '7 working hours' -> 7, '03 November 2025' -> date."""
    raw = v.strip().strip("*").strip()
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", raw)
    if m and m.group(2).lower() in _MONTHS:
        return raw, None, date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.match(r"^(-?\d+(?:\.\d+)?)(?:\s*/\s*\d+|\s+[a-z ]+|\s*%)?$", raw)
    return raw, (float(m.group(1)) if m else None), None


@dataclass
class Record:
    rid: str
    doc_id: str
    doc_type: str
    chunk: object                      # the chunk it came from: carries country, period, status ...
    fields: dict = field(default_factory=dict)   # key -> raw string

    def num(self, key):
        return parse_value(self.fields[key])[1] if key in self.fields else None

    def get(self, key):
        return self.fields.get(key)


def parse_block(lines):
    """Fields of one record block (its lines, heading first)."""
    out = {}
    first = lines[0]
    h = _HEAD.match(first)
    if h:
        head = h.group("head")
        rid, _, title = head.partition(" — ")
        out["id"] = rid.split()[-1] if rid.split() else rid
        if title:
            out["title"] = title.strip()
    else:
        b = _BOLD_ID.match(first)
        out["id"] = b.group("id")
        # unlabelled `·` segments after the id are positional; keep the labelled ones
    for line in lines:
        s = line.strip()
        if not s:
            continue
        for m in _BOLD_FIELD.finditer(s):
            k, v = norm_key(m.group("k")), m.group("v").strip()
            if k and v and len(v) <= 80:
                out.setdefault(k, v)
        m = _BOLD_SENT.match(s)
        if m:
            out.setdefault(norm_key(m.group("k")), m.group("v").strip())
        m = _ITAL_FIELD.match(s)
        if m:
            out.setdefault(norm_key(m.group("k")), m.group("v").strip())
        if " · " in s:
            for seg in s.split(" · "):
                m = _PLAIN_FIELD.match(seg.strip().strip("*").strip())
                if m and "**" not in seg:
                    out.setdefault(norm_key(m.group("k")), m.group("v").strip())
    return out


def records_of_chunk(chunk):
    """Record blocks in one chunk; a chunk can hold one record (tickets) or several (survey comments)."""
    blocks, cur = [], None
    for line in str(chunk.text).splitlines():
        h = _HEAD.match(line)
        if h and (" — " in line or _ID.search(h.group("head"))) or _BOLD_ID.match(line.strip()):
            cur = [line.strip()]; blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    out = []
    for b in blocks:
        f = parse_block(b)
        if len([k for k in f if k != "id"]) >= 2:   # a record has an id and at least two fields
            out.append(f)
    return out


def build_records(chunks, record_types):
    """Every record in chunks of the given document types, de-duplicated by (doc, id)."""
    seen, out = set(), []
    for c in chunks:
        if c.doc_type not in record_types:
            continue
        for f in records_of_chunk(c):
            key = (c.doc_id, f["id"])
            if key in seen:
                continue
            seen.add(key)
            out.append(Record(f["id"], c.doc_id, c.doc_type, c, {k: v for k, v in f.items() if k != "id"}))
    return out


def catalogue(records, max_values=25):
    """Per document type: field -> {n, numeric, values (most common, for categorical fields)}."""
    by_type = defaultdict(list)
    for r in records:
        by_type[r.doc_type].append(r)
    cat = {}
    for t, rs in by_type.items():
        fields = Counter(k for r in rs for k in r.fields)
        entry = {}
        for k, n in fields.items():
            if n < 0.2 * len(rs):
                continue  # rare fields are noise
            vals = [r.fields[k] for r in rs if k in r.fields]
            parsed = [parse_value(v) for v in vals]
            numeric = sum(p[1] is not None for p in parsed) >= 0.8 * len(vals)
            dated = sum(p[2] is not None for p in parsed) >= 0.8 * len(vals)
            distinct = Counter(vals)
            info = {"n": n, "type": "date" if dated else "number" if numeric else "text"}
            short = sum(len(v) for v in vals) / len(vals) <= 45
            # many distinct values = an identifier (a person, a reference), not a category to filter on
            if not numeric and not dated and len(distinct) <= 30 and short:
                info["values"] = [v for v, _ in distinct.most_common(max_values)]
            elif numeric:
                nums = [p[1] for p in parsed if p[1] is not None]
                info["range"] = [min(nums), max(nums)]
            if info["type"] != "text" or "values" in info:
                entry[k] = info
        cat[t] = {"records": len(rs), "fields": entry}
    return cat


# --- structured query ----------------------------------------------------------------------
def _match(r, flt):
    k, op, want = flt.get("field"), flt.get("op", "eq"), flt.get("value")
    have = r.get(k)
    if have is None:
        return False
    if op in ("gte", "gt", "lte", "lt"):
        x = r.num(k)
        try:
            w = float(want)
        except (TypeError, ValueError):
            return False
        return x is not None and {"gte": x >= w, "gt": x > w, "lte": x <= w, "lt": x < w}[op]
    h, w = str(have).strip().lower(), str(want).strip().lower()
    if op == "in":
        return h in [str(x).strip().lower() for x in (want or [])]
    if op == "contains":
        return w in h
    if op == "ne":
        return h != w
    return h == w


def _matches(r, filters):
    return all(_match(r, f) for f in filters or [])


def run_query(records_by_group, q):
    """Execute a field query. records_by_group: {group label: [Record]} (already scoped).

    q = {operation: count|sum|mean|share|mode|top_k|rank_groups|max_group|min_group,
         filters: [{field, op, value}], target: field, condition: [filters] (for share), k: int}
    Returns an estimate-shaped dict (exact: lower = upper = estimate) or None when the
    operation can't run on these fields.
    """
    op = q.get("operation")
    flt = q.get("filters") or []
    groups = {}
    for g, rs in records_by_group.items():
        groups[g] = [r for r in rs if _matches(r, flt)]
    if op in ("rank_groups", "max_group", "min_group"):
        counts = {g: len(rs) for g, rs in groups.items()}
        values_are = "counts"
        if q.get("condition"):  # rank groups by a share, or a net share (share meeting condition minus share meeting minus_condition)
            counts = {g: v for g, rs in groups.items() if (v := net_share(rs, q["condition"], q.get("minus_condition"))) is not None}
            values_are = "net share (percentage points)" if q.get("minus_condition") else "shares"
        elif q.get("target"):  # rank groups by the mean of a numeric field instead of by count
            means = {g: _mean([r.num(q["target"]) for r in rs]) for g, rs in groups.items()}
            counts = {g: v for g, v in means.items() if v is not None}
            values_are = "means"
        total = sum(counts.values()) or 1
        order = sorted(counts, key=lambda g: (-counts[g], g)) if op != "min_group" else sorted(counts, key=lambda g: (counts[g], g))
        k = 1 if op in ("max_group", "min_group") else (q.get("k") or len(order))
        cats = [{"category": g, "count": counts[g], "estimate": counts[g] / total, "ci_low": counts[g] / total,
                 "ci_high": counts[g] / total} for g in _with_ties(order, counts, k)]
        if not cats:
            return None
        if values_are != "counts":  # a share or mean is the value itself, not a count to normalise
            cats = [dict(c, estimate=c["count"], ci_low=c["count"], ci_high=c["count"]) for c in cats]
        if values_are != "counts":
            total = sum(len(rs) for rs in groups.values())
        return {"groups": {"all": {"n": total, "population": total, "categories": cats, "values_are": values_are}}}
    out = {}
    for g, rs in groups.items():
        if op == "count":
            n = len(rs)
            out[g] = {"estimate": n, "ci_low": n, "ci_high": n, "n": n, "population": n, "what": "number of matching records"}
        elif op in ("sum", "mean"):
            nums = [r.num(q.get("target")) for r in rs]
            nums = [x for x in nums if x is not None]
            if not nums:
                return None
            v = sum(nums) if op == "sum" else sum(nums) / len(nums)
            v = round(v, 3)
            out[g] = {"estimate": v, "ci_low": v, "ci_high": v, "n": len(nums), "population": len(nums),
                      "what": "mean value" if op == "mean" else "total"}
        elif op == "share":
            if not rs:
                return None
            hit = sum(_matches(r, q.get("condition")) for r in rs)
            v = round(hit / len(rs), 3)
            out[g] = {"estimate": v, "ci_low": v, "ci_high": v, "n": len(rs), "population": len(rs),
                      "what": "share meeting the condition"}
        elif op == "net_share":
            v = net_share(rs, q.get("condition"), q.get("minus_condition"))
            if v is None:
                return None
            out[g] = {"estimate": v, "ci_low": v, "ci_high": v, "n": len(rs), "population": len(rs),
                      "what": "net share in percentage points" if q.get("minus_condition") else "share in percent"}
        elif op in ("mode", "top_k"):
            t = q.get("target")
            vals = [r.get(t) for r in rs if r.get(t)]
            if not vals:
                return None
            c = Counter(vals)
            k = 1 if op == "mode" else (q.get("k") or 3)
            ranked = [v for v, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
            cats = [{"category": v, "count": c[v], "estimate": c[v] / len(vals), "ci_low": c[v] / len(vals),
                     "ci_high": c[v] / len(vals)} for v in (ranked[:1] if op == "mode" else _with_ties(ranked, c, k))]
            out[g] = {"n": len(vals), "population": len(vals), "categories": cats}
        else:
            return None
    return {"groups": out}


def _with_ties(order, value, k):
    """The first k of order, plus any later item tied with the k-th: a cut through a tie
    would pick one of the tied items arbitrarily (by name)."""
    if k >= len(order):
        return list(order)
    cut = value[order[k - 1]]
    return list(order[:k]) + [g for g in order[k:] if value[g] == cut]


def net_share(rs, condition, minus_condition=None):
    """Percentage of records meeting condition, minus the percentage meeting minus_condition
    (a net score such as promoters minus detractors); None for no records or no condition."""
    if not rs or not condition:
        return None
    pct = lambda c: 100 * sum(_matches(r, c) for r in rs) / len(rs)
    return round(pct(condition) - (pct(minus_condition) if minus_condition else 0), 1)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None
