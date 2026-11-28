"""Index-time conflict scan: table facts that disagree across documents.

At question time a conflict is visible only when every document that states the fact is
retrieved together, which happens for a minority of conflict questions. The table facts are
already read once at load time (lensrag/facts.py), so disagreements can be found there instead,
without an LLM:

* version_change   the same chapter states a different number in different manual versions;
* update_pending   an announced (future) update changes a number the current primary source states;
* update_unapplied an in-force update changed a number, but a current source still states the old one;
* stale_secondary  a restating source (FAQ, handbook, benefits summary) disagrees with the current
                   primary source or an in-force update.

Facts are matched across documents by scope (the same country, or company-wide), by the kind
of unit, and by the similarity of their row labels, embedded once. Labels alone are a weak match
('Earned leave increase' in a circular, 'Paid annual leave' in the manual), so with a judge an LLM
picks, from a fact's few nearest candidates, the one stating the same entitlement (one call per
fact); without one a fixed similarity threshold decides. Each
flag names the value that applies under a fixed precedence: an in-force update, then the current
primary source; secondary sources never win. Which document types play which role comes from the
domain config (`source_roles`), not from this module.

Conflicts that need a rule about the values themselves (a country figure below a company-wide
minimum) are not detected here.
"""
from __future__ import annotations
import re
from collections import defaultdict

import numpy as np

from .facts import norm_attr, number

_CHAPTER_VERSION = re.compile(r"-v\d+(\.\d+)*-")
_UNITS = [("percent", re.compile(r"%|per ?cent", re.I)),
          ("money", re.compile(r"[₹$€£]|\b(aed|sgd|usd|eur|gbp|inr|aud|cad)\b|\bdirhams?\b", re.I)),
          ("days", re.compile(r"\bdays?\b", re.I)), ("weeks", re.compile(r"\bweeks?\b", re.I)),
          ("months", re.compile(r"\bmonths?\b", re.I)), ("hours", re.compile(r"\bhours?\b|\bhrs?\b", re.I)),
          ("years", re.compile(r"\byears?\b", re.I))]
_TIME = re.compile(r"\d{1,2}[:.]\d{2}\s*(am|pm)?|\b\d{1,2}\s*(am|pm)\b", re.I)


def unit_kind(value, label=""):
    """The kind of unit a fact's number is in ('days', 'money', 'percent', ...), or None."""
    for text in (str(value), str(label)):
        for kind, rx in _UNITS:
            if rx.search(text):
                return kind
    return None


def _compatible(a, b):
    ua, ub = unit_kind(a["value"], a["attribute"]), unit_kind(b["value"], b["attribute"])
    return ua == ub or ua is None or ub is None


def _usable(f):
    """Numeric facts only: not cross-references, clock times or bare row numbers."""
    return (f.get("number") is not None and not f.get("reference") and not _TIME.search(str(f["value"]))
            and not re.fullmatch(r"\d+", str(f["attribute"]).strip()))


def _scope(f, global_values):
    c = str(f.get("country") or "").upper()
    return "GLOBAL" if c in global_values else c


def _label(f):
    """The text matched across documents: the row label, its subject and section heading."""
    parts = [f.get("section") or "", f.get("subject") or "", str(f["attribute"])]
    return " — ".join(p for p in parts if p)


def _same(x, y):
    return x is not None and y is not None and abs(x - y) < 1e-9


JUDGE_SYSTEM = ("You compare rows from tables in an organisation's documents. Answer only with JSON.")
JUDGE_PROMPT = """Row A comes from {a_doc} ({a_scope}):
  {a}

Candidate rows from the main policy documents:
{cands}

Which candidate states the same entitlement, amount, rate or limit as row A, for the same group of
people, so that the two values should agree unless one document is out of date? The values may
differ; judge only what the rows are about. A different benefit, a different employee group or
grade, a different country or a different period is not the same. Answer {{"match": <candidate
number>}} or {{"match": null}} when none is the same."""


def _row(f):
    return f"{_label(f)} = {f['value']}"


def llm_judge(json_call, workers=4):
    """A judge for scan(): json_call(system, user) -> dict (an LLM client's json method)."""
    def judge(items):
        from concurrent.futures import ThreadPoolExecutor
        def one(item):
            f, cands = item
            user = JUDGE_PROMPT.format(a_doc=f["doc_id"], a_scope=f["_scope"], a=_row(f),
                                       cands="\n".join(f"  {k + 1}. [{c['doc_id']}, {c['_scope']}] {_row(c)}" for k, c in enumerate(cands)))
            try:
                m = (json_call(JUDGE_SYSTEM, user) or {}).get("match")
                m = int(m) if m is not None and str(m).strip().isdigit() else None
            except Exception:
                return None
            return cands[m - 1] if m and 1 <= m <= len(cands) else None
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(one, items))
    return judge


def scan(facts, encode, roles, global_values=("ALL", "GLOBAL", ""), active=("current", "in force", ""),
         pending=("announced",), threshold=0.85, judge=None, top_k=5, floor=0.5):
    """Flags for facts that disagree. facts: fact records from lensrag.facts with 'country' and
    optionally 'section' added; encode(texts) -> unit-normalised vectors; roles: {primary, update,
    secondary: [doc types]}. judge([(fact, candidates)]) -> [matching candidate or None]; without
    it the nearest candidate at or above threshold matches."""
    glob = {str(g).upper() for g in global_values}
    active, pending = {s.lower() for s in active}, {s.lower() for s in pending}
    primary, update, secondary = (set(roles.get(k) or []) for k in ("primary", "update", "secondary"))
    usable = [f for f in facts if _usable(f)]
    for f in usable:
        f["_scope"] = _scope(f, glob)
    flags = []

    # 1. the same chapter across manual versions
    by_row = defaultdict(list)
    for f in usable:
        if f["doc_type"] in primary and f.get("version"):
            by_row[(_CHAPTER_VERSION.sub("-", f["doc_id"]), f["_scope"], norm_attr(f["attribute"]))].append(f)
    for (chapter, scope, attr), fs in by_row.items():
        versions = {}
        for f in sorted(fs, key=lambda f: f["version"]):
            versions.setdefault(f["version"], f)
        if len(versions) > 1 and len({v["number"] for v in versions.values()}) > 1:
            latest = versions[max(versions)]
            flags.append(_flag("version_change", list(versions.values()), latest, scope))

    # 2. updates and restating sources against the current primary source
    current = [f for f in usable if f["doc_type"] in primary and str(f.get("status") or "").lower() in active]
    others = [f for f in usable if f["doc_type"] in update | secondary]
    if not current or not others:
        return flags
    cv = encode([_label(f) for f in current])
    ov = encode([_label(f) for f in others])
    sims = ov @ cv.T
    matched = []                                      # (fact, the current primary fact it restates)
    pending_judge = []
    for i, f in enumerate(others):
        cands = [j for j in np.argsort(-sims[i]) if sims[i, j] >= (floor if judge else threshold)
                 and current[j]["_scope"] in (f["_scope"], "GLOBAL") and _compatible(f, current[j])][:top_k]
        if not cands:
            continue
        if judge:
            pending_judge.append((f, [current[j] for j in cands]))
        else:
            own = [j for j in cands if current[j]["_scope"] == f["_scope"]]   # a country's own chapter first
            matched.append((f, current[(own or cands)[0]]))
    if pending_judge:
        matched += [(f, p) for (f, _), p in zip(pending_judge, judge(pending_judge)) if p is not None]

    # updates first: an in-force update replaces the primary value for the secondary check below.
    # Only active updates apply (a superseded or withdrawn circular never does), and when several
    # change the same primary fact the latest effective one wins, whatever the traversal order.
    in_force = defaultdict(list)                      # id(primary fact) -> [(update, primary)]
    for f, p in matched:
        if f["doc_type"] not in update:
            continue
        status = str(f.get("status") or "").lower()
        if status in pending:
            if not _same(f["number"], p["number"]):
                flags.append(_flag("update_pending", [p, f], p, f["_scope"], pending_value=f["value"]))
        elif status in active:
            in_force[id(p)].append((f, p))
    applies = {}                                      # id(primary fact) -> the in-force update fact
    for pid, ups in in_force.items():
        f, p = max(ups, key=lambda fp: (str(fp[0].get("effective_date") or ""), str(fp[0]["doc_id"])))
        if _same(f["number"], p["number"]):
            continue                                  # the primary source already states the latest update
        before = number(f.get("previous_value")) if f.get("previous_value") else None
        if before is None or _same(before, p["number"]) or len(ups) > 1:
            flags.append(_flag("update_unapplied", [p] + [u for u, _ in ups], f, f["_scope"]))
            applies[pid] = f
    for f, p in matched:
        if f["doc_type"] not in secondary:
            continue
        u = applies.get(id(p))
        right = u or p
        if not _same(f["number"], right["number"]):
            flags.append(_flag("stale_secondary", [f, p] + ([u] if u else []), right, f["_scope"]))
    return flags


def _source(f):
    return {"doc_id": f["doc_id"], "version": f.get("version") or "", "status": f.get("status") or "",
            "effective_date": f.get("effective_date") or "", "attribute": f["attribute"], "value": f["value"],
            "evidence_span": f.get("evidence_span")}


def _flag(kind, sources, applies, scope, **extra):
    return {"kind": kind, "scope": scope, "documents": sorted({s["doc_id"] for s in sources}),
            "sources": [_source(s) for s in sources], "applies": _source(applies), **extra}


def facts_for_scan(chunks, fact_index):
    """Fact records with each chunk's country and section heading added."""
    by_id = {c.chunk_id: c for c in chunks}
    out = []
    for cid, fs in fact_index.items():
        c = by_id.get(cid)
        sec = c.section_path if c is not None else ""
        sec = sec[-1] if isinstance(sec, (list, tuple)) and sec else (str(sec or "").split(">")[-1].strip())
        for f in fs:
            out.append({**f, "country": getattr(c, "country", "") or "", "section": sec})
    return out
