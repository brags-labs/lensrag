from __future__ import annotations
from collections import defaultdict, Counter
from typing import Any

def validate_evidence_records(records):
    """Validate query-time evidence records and preserve exact provenance."""
    valid=[]
    rejected=[]
    required={"entity","attribute","value","evidence_span","doc_id"}
    for i,record in enumerate(records):
        missing=required-set(record)
        span=str(record.get("evidence_span","")).strip()
        if missing or not span:
            rejected.append({"index":i,"reason":f"missing fields: {sorted(missing)}"})
            continue
        valid.append(dict(record))
    return valid,rejected

def aggregate_records(records, operation, top_k=None, threshold=None, comparator="gte"):
    """Deterministic operations over validated evidence records; no LLM arithmetic."""
    records,_=validate_evidence_records(records)
    if operation=="count":
        return len({(r["entity"],r["attribute"]) for r in records})
    if operation in ("max","min","rank","top_k"):
        numeric=[r for r in records if isinstance(r["value"],(int,float))]
        reverse=operation in ("max","rank","top_k")
        ordered=sorted(numeric,key=lambda r:r["value"],reverse=reverse)
        if operation=="max": return ordered[0] if ordered else None
        if operation=="min": return ordered[0] if ordered else None
        return ordered[:(top_k or 3)]
    if operation=="filter":
        if threshold is None: raise ValueError("threshold is required for filter")
        ops={"gte":lambda x:x>=threshold,"gt":lambda x:x>threshold,"lte":lambda x:x<=threshold,"lt":lambda x:x<threshold}
        if comparator not in ops: raise ValueError("Unsupported comparator")
        return [r for r in records if isinstance(r["value"],(int,float)) and ops[comparator](r["value"])]
    raise ValueError(f"Unsupported aggregation operation: {operation}")

def completeness_report(records, expected_entities):
    present={r.get("entity") for r in records}
    expected=set(expected_entities)
    missing=sorted(expected-present)
    return {"expected_count":len(expected),"present_count":len(expected&present),
            "missing_entities":missing,"complete":not missing}

def find_conflicts(records):
    """Flag differing values for the same entity/attribute/version; different versions are not conflicts."""
    groups=defaultdict(list)
    for r in records:
        key=(r.get("entity"),r.get("attribute"),r.get("version","unspecified"))
        groups[key].append(r)
    conflicts=[]
    for (entity,attribute,version),items in groups.items():
        values={str(x.get("value")) for x in items}
        if len(values)>1:
            conflicts.append({"entity":entity,"attribute":attribute,"version":version,
                              "values":sorted(values),
                              "sources":[{"doc_id":x.get("doc_id"),"evidence_span":x.get("evidence_span")} for x in items]})
    return conflicts

def reduce_labels(records, group_field="period"):
    """Reduce pre-labelled theme/sentiment records; labels must come from an upstream classifier."""
    grouped=defaultdict(Counter)
    for r in records:
        group=r.get(group_field,"unknown")
        for label in r.get("labels",[]):
            grouped[group][label]+=1
        if r.get("sentiment"):
            grouped[group][r["sentiment"]]+=1
    return {group:dict(counts) for group,counts in grouped.items()}
