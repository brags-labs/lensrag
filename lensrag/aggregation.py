"""Deterministic evidence handling for LensRAG (steps 7 and 8).

Evidence records are query-time dicts with at least entity, attribute, value,
evidence_span and doc_id; extraction also attaches version, status, effective_date,
period and the scope label they were retrieved for.

The LLM only extracts records. Everything here is ordinary code: version resolution,
conflict flags, counting, extrema, ranking, filtering, averages, shares, grouping,
completeness and label reduction.
"""
from __future__ import annotations
import re
from collections import defaultdict, Counter

ACTIVE = {"current", "in force", "active", ""}   # defaults; domains pass their own
PENDING = {"announced"}


def validate_evidence_records(records):
    """Keep records with the required fields and a non-empty evidence span."""
    valid = []
    rejected = []
    required = {"entity", "attribute", "value", "evidence_span", "doc_id"}
    for i, record in enumerate(records):
        missing = required - set(record)
        span = str(record.get("evidence_span", "")).strip()
        if missing or not span:
            rejected.append({"index": i, "reason": f"missing fields: {sorted(missing)}"})
            continue
        valid.append(normalize_units(dict(record)))
    return valid, rejected


_WORKING_DAYS = re.compile(r"(\d+(?:\.\d+)?)\s+working\s+days?\b", re.I)


def normalize_units(record):
    """Put a value in the unit its attribute names. A table column headed '(weeks)' can hold
    '10 working days'; read as 10 weeks, that is five times too long. A working week is 5 days."""
    attr = str(record.get("attribute") or "").lower()
    if "week" not in attr:
        return record
    for text in (str(record.get("value")), str(record.get("evidence_span") or "")):
        m = _WORKING_DAYS.search(text)
        if m:
            try:
                same = float(m.group(1)) == float(str(record.get("value")).split()[0])
            except ValueError:
                same = "working day" in str(record.get("value")).lower()
            if same:
                weeks = float(m.group(1)) / 5
                record["value"] = int(weeks) if weeks.is_integer() else round(weeks, 2)
                record["unit_note"] = f"{m.group(0)} converted to weeks (5 working days a week)"
            break
    return record


def _status(r):
    return str(r.get("status", "")).strip().lower()


def _recency(r):
    # ISO dates sort correctly as strings; records without a date sort first.
    return (str(r.get("effective_date") or ""), str(r.get("version") or ""))


def _same(a, b):
    return str(a.get("value")).strip().lower() == str(b.get("value")).strip().lower()


def find_conflicts(records, key_fields=("entity", "attribute")):
    """Flag every disagreement between records about the same entity and attribute.

    kind = "conflict"            two records of the same version (or both unversioned) disagree
    kind = "version_difference"  records from different versions disagree, e.g. an older
                                 manual says 20 days and the current one 18
    """
    groups = defaultdict(list)
    for r in records:
        groups[tuple(r.get(f) for f in key_fields)].append(r)
    flags = []
    for key, items in groups.items():
        by_version = defaultdict(list)
        for r in items:
            by_version[str(r.get("version") or "unspecified")].append(r)
        for version, same in by_version.items():
            values = sorted({str(x.get("value")) for x in same})
            if len(values) > 1:
                flags.append({"kind": "conflict", "key": dict(zip(key_fields, key)), "version": version,
                              "values": values, "sources": _sources(same)})
        if len(by_version) > 1:
            values = sorted({str(x.get("value")) for x in items})
            if len(values) > 1:
                flags.append({"kind": "version_difference", "key": dict(zip(key_fields, key)),
                              "values_by_version": {v: sorted({str(x.get("value")) for x in rs}) for v, rs in by_version.items()},
                              "sources": _sources(items)})
    return flags


def _sources(items):
    return [{"doc_id": x.get("doc_id"), "version": x.get("version"), "status": x.get("status"),
             "effective_date": x.get("effective_date"), "value": x.get("value"),
             "evidence_span": x.get("evidence_span")} for x in items]


def resolve_versions(records, key_fields=("entity",), active_statuses=None, pending_statuses=None):
    """Choose one value per key and flag every alternative instead of hiding it.

    Rule: prefer records whose status is current/in force, then the latest effective
    date. Superseded values are flagged "superseded_value", announced future values
    "pending_change", and disagreeing active records "conflict" (resolved to the most
    recent one, and marked unresolved when they share a date). If only superseded
    evidence exists, the newest one is used and flagged "only_superseded_evidence".

    Returns (resolved_records, flags).
    """
    active_set = {s.lower() for s in (active_statuses if active_statuses is not None else ACTIVE)}
    pending_set = {s.lower() for s in (pending_statuses if pending_statuses is not None else PENDING)}
    groups = defaultdict(list)
    for r in records:
        groups[tuple(r.get(f) for f in key_fields)].append(r)
    resolved, flags = [], []
    for key, items in groups.items():
        active = [r for r in items if _status(r) in active_set]
        pool = active or [r for r in items if _status(r) not in pending_set] or items
        pool = sorted(pool, key=_recency, reverse=True)
        chosen = pool[0]
        resolved.append(chosen)
        label = dict(zip(key_fields, key))
        if not active:
            flags.append({"kind": "only_superseded_evidence", "key": label, "chosen": _sources([chosen])[0]})
        for other in items:
            if other is chosen or _same(other, chosen):
                continue
            st = _status(other)
            if st in pending_set:
                kind = "pending_change"
            elif st not in active_set:
                kind = "superseded_value"
            else:
                kind = "conflict"
            flag = {"kind": kind, "key": label, "chosen": _sources([chosen])[0], "other": _sources([other])[0]}
            if kind == "conflict":
                flag["unresolved"] = _recency(other)[0] == _recency(chosen)[0]
            flags.append(flag)
    return resolved, flags


def _numeric(records):
    out = []
    for r in records:
        v = r.get("value")
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append(r)
        elif isinstance(v, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", v.strip()):
            out.append(dict(r, value=float(v)))
    return out


def _truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() in {"yes", "true", "y"})


def aggregate_records(records, operation, top_k=None, threshold=None, comparator="gte", direction="desc",
                      group_by="scope", resolve=True, active_statuses=None, pending_statuses=None):
    """Deterministic operations over validated evidence records; no LLM arithmetic.

    count    number of distinct entities with evidence
    sum      total of all numeric values
    frequency / mode / crosstab   categorical counts (see `categorical`)
    all_of / any_of               entities meeting every / any yes-no criterion (see `criteria_match`)
    max/min  the entity (or entities, on ties) with the extreme value
    rank     entities sorted by value (direction), first `top_k`; ties at the cut are kept
    filter   entities whose value passes `comparator threshold`; with no threshold, entities
             whose value is a yes/true criterion match
    mean     mean of all numeric values (no per-entity resolution: each record is one item)
    share    fraction of records whose value is yes/true
    group    values grouped by `group_by` (e.g. period or version scope) for comparisons

    Per-entity operations first resolve versions so each entity contributes one value.
    """
    records, _ = validate_evidence_records(records)
    per_entity = resolve_versions(records, active_statuses=active_statuses, pending_statuses=pending_statuses)[0] if resolve else records
    if operation == "count":
        return len({r["entity"] for r in per_entity})
    if operation == "sum":
        values = [r["value"] for r in _numeric(records)]
        return {"sum": sum(values), "n": len(values)} if values else None
    if operation in ("frequency", "mode", "crosstab"):
        return categorical(records, operation, top_k=top_k, group_by=group_by)
    if operation in ("all_of", "any_of"):
        return criteria_match(per_entity if resolve else records, require_all=operation == "all_of")
    if operation in ("max", "min"):
        numeric = _numeric(per_entity)
        if not numeric:
            return None
        best = (max if operation == "max" else min)(r["value"] for r in numeric)
        ties = [r for r in numeric if r["value"] == best]
        return ties[0] if len(ties) == 1 else ties
    if operation in ("rank", "top_k"):
        numeric = sorted(_numeric(per_entity), key=lambda r: r["value"], reverse=direction != "asc")
        if not top_k or top_k >= len(numeric):
            return numeric
        cut = numeric[top_k - 1]["value"]
        return [r for i, r in enumerate(numeric) if i < top_k or r["value"] == cut]
    if operation == "filter":
        if threshold is None:
            return [r for r in per_entity if _truthy(r.get("value"))]
        ops = {"gte": lambda x: x >= threshold, "gt": lambda x: x > threshold, "lte": lambda x: x <= threshold,
               "lt": lambda x: x < threshold, "eq": lambda x: x == threshold}
        if comparator not in ops:
            raise ValueError("Unsupported comparator")
        return [r for r in _numeric(per_entity) if ops[comparator](r["value"])]
    if operation == "mean":
        values = [r["value"] for r in _numeric(records)]
        return {"mean": sum(values) / len(values), "n": len(values)} if values else None
    if operation == "share":
        flags = [r for r in records if isinstance(r.get("value"), bool) or str(r.get("value")).strip().lower() in {"yes", "no", "true", "false"}]
        return {"share": sum(_truthy(r["value"]) for r in flags) / len(flags), "n": len(flags)} if flags else None
    if operation == "group":
        groups = defaultdict(list)
        for r in records:
            groups[str(r.get(group_by) or r.get("version") or r.get("period") or "unspecified")].append(
                {"entity": r["entity"], "attribute": r["attribute"], "value": r["value"], "doc_id": r["doc_id"]})
        return dict(groups)
    raise ValueError(f"Unsupported aggregation operation: {operation}")


def categorical(records, operation="frequency", top_k=None, group_by="entity"):
    """Counts of categorical values, per group (Mode A, categorical).

    frequency  {group: [(category, count), ...]} most common first (top_k if given)
    mode       {group: [most common categories]} - several when tied
    crosstab   {group: {category: count}}
    Categories are normalised (case, punctuation, plurals) so variants count together;
    the first spelling seen is kept for display.
    """
    counts, display = defaultdict(Counter), {}
    for r in records:
        v = r.get("value")
        if v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
            continue
        key = normalize_label(v)
        if not key:
            continue
        display.setdefault(key, str(v))
        counts[str(r.get(group_by) or "all")][key] += 1
    if operation == "crosstab":
        return {g: {display[k]: n for k, n in c.most_common()} for g, c in counts.items()}
    if operation == "mode":
        out = {}
        for g, c in counts.items():
            top = max(c.values())
            out[g] = [display[k] for k, n in c.most_common() if n == top]
        return out
    return {g: [(display[k], n) for k, n in c.most_common(top_k)] for g, c in counts.items()}


def criteria_match(records, require_all=True):
    """Entities whose yes/no criteria are met: all of them (all_of) or at least one (any_of).

    The criteria are the distinct attributes present in the records (e.g. "on-site gym",
    "creche"); an entity with no record for a criterion does not meet it.
    """
    criteria = {normalize_label(r.get("attribute")) for r in records if normalize_label(r.get("attribute"))}
    met = defaultdict(set)
    for r in records:
        if _truthy(r.get("value")):
            met[r["entity"]].add(normalize_label(r.get("attribute")))
    test = (lambda s: criteria <= s) if require_all else (lambda s: bool(s & criteria))
    return {"criteria": sorted(criteria), "entities": sorted(e for e, s in met.items() if test(s))}


_NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers_in(obj):
    """Every number in a value, record list or nested result (strings are scanned for numbers)."""
    out = []
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return [float(m.replace(",", "")) for m in _NUM_RE.findall(obj)]
    if isinstance(obj, dict):
        for v in obj.values():
            out += numbers_in(v)
        return out
    if isinstance(obj, (list, tuple, set)):
        for v in obj:
            out += numbers_in(v)
    return out


def number_provenance(text, allowed, rel_tol=0.01):
    """Numbers in `text` that match none of the `allowed` numbers (also as percentages).

    Used to check that an answer only states numbers that code computed or that appear in
    the cited evidence. Small integers (0-10) are ignored, as they are usually list
    positions or counts of items named in the text itself.
    """
    pool = set()
    for a in allowed:
        pool.update({a, round(a, 2), round(a * 100, 1), round(a / 100, 4)})
    def ok(x):
        return any(abs(x - a) <= max(rel_tol * abs(a), 0.051) for a in pool)
    return [x for x in numbers_in(str(text)) if not (0 <= x <= 10 and float(x).is_integer()) and not ok(x)]


def completeness_report(records, expected_entities):
    present = {r.get("entity") for r in records}
    expected = set(expected_entities)
    missing = sorted(expected - present)
    return {"expected_count": len(expected), "present_count": len(expected & present),
            "missing_entities": missing, "complete": not missing}


def normalize_label(label: str) -> str:
    """Fold case, punctuation and simple plurals so near-identical labels count together."""
    s = re.sub(r"[^a-z0-9 ]+", " ", str(label).lower()).strip()
    s = re.sub(r"\s+", " ", s)
    def singular(w):
        if len(w) > 4 and w.endswith("ies"):
            return w[:-3] + "y"
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w
    return " ".join(singular(w) for w in s.split())


def reduce_labels(records, group_field="period"):
    """Reduce labelled theme/sentiment records per group; labels come from the map step."""
    grouped = defaultdict(Counter)
    for r in records:
        group = r.get(group_field, "unknown")
        for label in r.get("labels", []):
            grouped[group][normalize_label(label)] += 1
        if r.get("sentiment"):
            grouped[group][f"sentiment:{r['sentiment']}"] += 1
    return {group: dict(counts) for group, counts in grouped.items()}
