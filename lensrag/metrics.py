from __future__ import annotations
import numpy as np
from fnmatch import fnmatchcase

def expand_gold_ids(gold_doc_ids, corpus_doc_ids):
    """Expand wildcard gold IDs (e.g. "TKT-IN-*") into the matching corpus doc IDs.

    Exact IDs are kept as-is. A pattern that matches nothing is kept literally, so it
    still counts as missed evidence rather than silently disappearing.
    """
    corpus=list(dict.fromkeys(corpus_doc_ids))
    out=[]
    for gid in gold_doc_ids or []:
        if any(ch in gid for ch in "*?["):
            hits=[d for d in corpus if fnmatchcase(d,gid)]
            out.extend(hits or [gid])
        else:
            out.append(gid)
    return list(dict.fromkeys(out))
def evidence_recall(retrieved_doc_ids, gold_doc_ids):
    gold=set(gold_doc_ids or [])
    return len(gold & set(retrieved_doc_ids))/len(gold) if gold else float("nan")
def evidence_precision(retrieved_doc_ids, gold_doc_ids):
    gold=set(gold_doc_ids or []); got=set(retrieved_doc_ids)
    return len(gold & got)/len(got) if got else 0.0
def set_f1(retrieved_doc_ids, gold_doc_ids):
    p=evidence_precision(retrieved_doc_ids,gold_doc_ids)
    r=evidence_recall(retrieved_doc_ids,gold_doc_ids)
    return 2*p*r/(p+r) if p+r else 0.0
def aggregate_summary(df):
    return (df.groupby(["tier","method","query_type"],dropna=False)
            .agg(n=("qid","count"), evidence_recall=("evidence_recall","mean"),
                 evidence_precision=("evidence_precision","mean"), evidence_f1=("evidence_f1","mean"),
                 latency_ms_p50=("latency_ms","median"), latency_ms_p95=("latency_ms",lambda x:x.quantile(.95)),
                 retrieved_docs=("retrieved_docs","mean"))
            .reset_index())
