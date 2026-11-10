from __future__ import annotations
import json, time, platform, hashlib
from pathlib import Path
import pandas as pd
from .data import ensure_extracted,load_documents,load_gold,chunk_document
from .retrieval import HybridIndex,method_retrieve,route_query
from .metrics import evidence_recall,evidence_precision,set_f1

def run_experiment(zip_path, extract_dir, tiers=("S","M","L"), top_k=10, output=Path("results")):
    zip_path=Path(zip_path); extract_dir=Path(extract_dir); output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    corpus=ensure_extracted(zip_path,extract_dir)
    gold=load_gold(corpus)
    rows=[]; configs={}
    for tier in tiers:
        docs=load_documents(corpus,tier)
        chunks=[ch for d in docs for ch in chunk_document(d)]
        t0=time.perf_counter(); index=HybridIndex(chunks); build_ms=(time.perf_counter()-t0)*1000
        # Gold evidence is read only after retrieval and used solely for scoring.
        eligible=[q for q in gold if {"S":1,"M":2,"L":3}[q.get("min_tier","S")] <= {"S":1,"M":2,"L":3}[tier]]
        for q in eligible:
            for method in ("bm25_topk","hybrid_topk","lensrag"):
                hits,lat=method_retrieve(index,q["question"],method,top_k)
                doc_ids=list(dict.fromkeys(c.doc_id for c,s in hits))
                gold_ids=q.get("evidence_docs",[])
                rows.append({
                    "tier":tier,"qid":q["qid"],"question":q["question"],
                    "query_type":q.get("type",route_query(q["question"])),"method":method,
                    "evidence_recall":evidence_recall(doc_ids,gold_ids),
                    "evidence_precision":evidence_precision(doc_ids,gold_ids),
                    "evidence_f1":set_f1(doc_ids,gold_ids),
                    "latency_ms":lat,"retrieved_docs":len(doc_ids),
                    "gold_evidence_docs":len(set(gold_ids)),"retrieved_doc_ids":";".join(doc_ids),
                    "build_ms":build_ms,"n_docs":len(docs),"n_chunks":len(chunks)
                })
        configs[tier]={"documents":len(docs),"chunks":len(chunks),"index_build_ms":build_ms}
        print(f"[{tier}] documents={len(docs)} chunks={len(chunks)} eligible_questions={len(eligible)} build_ms={build_ms:.1f}")
    df=pd.DataFrame(rows)
    df.to_csv(output/"metrics.csv",index=False)
    summary=(df.groupby(["tier","method","query_type"])
             .agg(n=("qid","count"),evidence_recall=("evidence_recall","mean"),
                  evidence_precision=("evidence_precision","mean"),evidence_f1=("evidence_f1","mean"),
                  latency_ms_p50=("latency_ms","median"),latency_ms_p95=("latency_ms",lambda x:x.quantile(.95)),
                  retrieved_docs=("retrieved_docs","mean")).reset_index())
    summary.to_csv(output/"summary.csv",index=False)
    try:
        import tiktoken
        enc=tiktoken.get_encoding("cl100k_base")
        token_method="tiktoken cl100k_base"
    except Exception:
        enc=None; token_method="fallback: whitespace words × 1.33 (estimate)"
    corpus_stats={}
    for tier in tiers:
        docs=load_documents(corpus,tier)
        chars=sum(len(d.text) for d in docs)
        words=sum(len(d.text.split()) for d in docs)
        tokens=(sum(len(enc.encode(d.text)) for d in docs) if enc else round(words*1.33))
        corpus_stats[tier]={"documents":len(docs),"words":words,"characters":chars,"tokens":tokens}
    config={"python":platform.python_version(),"platform":platform.platform(),"top_k":top_k,
            "tiers":list(tiers),"token_count_method":token_method,"corpus_stats":corpus_stats,
            "index_stats":configs,"methods":["bm25_topk","hybrid_topk","lensrag"],
            "seed":42,"note":"Retrieval-only evaluation; no LLM generation or answer accuracy measured."}
    (output/"run_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    return df,summary,config
