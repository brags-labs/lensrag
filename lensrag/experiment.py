from __future__ import annotations
import json, re, time, platform
from pathlib import Path
import pandas as pd
from .data import ensure_extracted,load_documents,load_gold,chunk_document
from .embeddings import DenseEncoder,DEFAULT_EMBEDDING_MODEL
from .retrieval import HybridIndex,method_retrieve,route_query,CrossEncoderJudge,judge_threshold_for
from .planning import build_inventory
from .domain import Domain,load_domain
from .metrics import evidence_recall,evidence_precision,set_f1,expand_gold_ids

CHUNK_PARAMS={"chunker":"chunk_document","max_words":260,"overlap_words":40}
# Long-context baselines: whole documents packed in corpus order into a fixed window,
# keeping room for instructions, the question and the answer. "full" sends everything
# (an oracle with an unlimited window), giving the upper bound on evidence availability.
LONG_CONTEXT_WINDOWS={"long_context_128k":128_000,"long_context_1m":1_000_000,"long_context_full":None}
PROMPT_RESERVE_TOKENS=4_000


class TokenCounter:
    """cl100k_base token counts (the tokenizer of the candidate API models), cached per text key."""
    def __init__(self):
        try:
            import tiktoken
            self._enc=tiktoken.get_encoding("cl100k_base"); self.method="tiktoken cl100k_base"
        except Exception:
            self._enc=None; self.method="fallback: whitespace words x 1.33 (estimate)"
        self._cache={}
    def __call__(self, key, text):
        if key not in self._cache:
            self._cache[key]=len(self._enc.encode(text,disallowed_special=())) if self._enc else round(len(text.split())*1.33)
        return self._cache[key]


def long_context_docs(docs, doc_tokens, window):
    """Documents that fit in `window` tokens when packed in corpus order (None = all)."""
    if window is None:
        return [d.doc_id for d in docs], sum(doc_tokens[d.doc_id] for d in docs)
    budget=window-PROMPT_RESERVE_TOKENS; used=0; kept=[]
    for d in docs:
        t=doc_tokens[d.doc_id]
        if used+t>budget: break
        kept.append(d.doc_id); used+=t
    return kept, used

def tier_index(docs, tier, store_dir=None, semantic="tfidf", encoder=None, domain: Domain | None=None):
    """Build the tier's HybridIndex, reusing chunks/vectors stored in Chroma when still valid.

    Returns (index, chunks, info) where info says whether the store was reused.
    """
    domain=domain or load_domain()
    t0=time.perf_counter()
    model=encoder.model_name if encoder else None
    store=None; source="memory"
    if store_dir:
        from .store import ChromaChunkStore,document_fingerprint
        fp=document_fingerprint(docs,CHUNK_PARAMS|{"semantic":semantic,"domain":domain.fingerprint()})
        # One collection per embedding model, so switching models doesn't overwrite another model's vectors.
        suffix="" if not model or model==DEFAULT_EMBEDDING_MODEL else "_"+re.sub(r"[^A-Za-z0-9]+","-",model.split("/")[-1]).strip("-")
        store=ChromaChunkStore(store_dir,f"lensrag_{domain.name}_{tier}_{semantic}{suffix}"[:60])
        if store.is_current(fp,model):
            chunks,vectors=store.load(with_embeddings=semantic=="dense"); source="chroma"
    if source!="chroma":
        chunks=[ch for d in docs for ch in chunk_document(d,domain=domain)]
        vectors=encoder.encode([c.enriched_text for c in chunks]) if semantic=="dense" else None
        if store: store.write(chunks,fp,vectors,model); source="built+stored"
    t1=time.perf_counter()
    index=HybridIndex(chunks,semantic=semantic,vectors=vectors,encoder=encoder)
    t2=time.perf_counter()
    return index,chunks,{"source":source,"load_or_build_chunks_ms":(t1-t0)*1000,"in_memory_index_ms":(t2-t1)*1000}

def run_experiment(zip_path, extract_dir, tiers=("S","M","L"), top_k=10, output=Path("results"), rerank=False,
                   store_dir=None, semantic="tfidf", embedding_model=DEFAULT_EMBEDDING_MODEL, judge_threshold=None,
                   domain="hr", long_context=True, judge_model="cross-encoder/ms-marco-MiniLM-L-6-v2"):
    domain=load_domain(domain) if not isinstance(domain,Domain) else domain
    zip_path=Path(zip_path); extract_dir=Path(extract_dir); output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    corpus=ensure_extracted(zip_path,extract_dir)
    gold=load_gold(corpus)
    rows=[]; configs={}
    methods=["bm25_topk","hybrid_topk","lensrag"]
    judge=None
    encoder=DenseEncoder(embedding_model) if semantic=="dense" else None
    if rerank:
        judge=CrossEncoderJudge(model_name=judge_model,threshold=judge_threshold_for(judge_model,judge_threshold))
        judge.model  # load up front so model loading is not counted as query latency
        methods.append("lensrag_rerank")
    lc_methods=list(LONG_CONTEXT_WINDOWS) if long_context else []
    count=TokenCounter()
    for tier in tiers:
        docs=load_documents(corpus,tier,domain)
        index,chunks,store_info=tier_index(docs,tier,store_dir,semantic,encoder,domain)
        build_ms=store_info["load_or_build_chunks_ms"]+store_info["in_memory_index_ms"]
        inventory=build_inventory(docs,domain)
        # Gold evidence is read only after retrieval and used solely for scoring.
        tier_doc_ids=[d.doc_id for d in docs]
        doc_tokens={d.doc_id:count(("doc",d.doc_id),d.text) for d in docs}
        packed={m:long_context_docs(docs,doc_tokens,w) for m,w in LONG_CONTEXT_WINDOWS.items() if m in lc_methods}
        eligible=[q for q in gold if {"S":1,"M":2,"L":3}[q.get("min_tier","S")] <= {"S":1,"M":2,"L":3}[tier]]
        for q in eligible:
            gold_ids=expand_gold_ids(q.get("evidence_docs",[]),tier_doc_ids)
            qtype=q.get("type",route_query(q["question"]))
            for method in methods+lc_methods:
                info={}
                if method in lc_methods:
                    doc_ids,context_tokens=packed[method]; lat=0.0
                else:
                    hits,lat=method_retrieve(index,q["question"],method,top_k,judge,inventory,info)
                    doc_ids=list(dict.fromkeys(c.doc_id for c,s in hits))
                    seen=set(); context_tokens=0
                    for c,_ in hits:
                        if c.chunk_id not in seen:
                            seen.add(c.chunk_id); context_tokens+=count(("chunk",c.chunk_id),c.enriched_text)
                recall=evidence_recall(doc_ids,gold_ids)
                missing_scopes=info.get("scopes_without_evidence",[])
                rows.append({
                    "tier":tier,"qid":q["qid"],"question":q["question"],
                    "query_type":qtype,"scope":"local" if qtype=="local" else "global","method":method,
                    "evidence_recall":recall,
                    "evidence_precision":evidence_precision(doc_ids,gold_ids),
                    "evidence_f1":set_f1(doc_ids,gold_ids),
                    "evidence_complete":bool(recall==1.0),
                    "latency_ms":lat,"retrieved_docs":len(doc_ids),"context_tokens":context_tokens,
                    "gold_evidence_docs":len(set(gold_ids)),"retrieved_doc_ids":";".join(doc_ids),
                    "planned_type":info.get("planned_type",""),"scopes":info.get("scopes",0),
                    "scopes_without_evidence":len(missing_scopes),
                    "completeness_flag":bool(missing_scopes) if method=="lensrag_rerank" else None,
                    "coverage_rounds":info.get("rounds",0),
                    "build_ms":build_ms,"n_docs":len(docs),"n_chunks":len(chunks)
                })
        configs[tier]={"documents":len(docs),"chunks":len(chunks),"index_build_ms":build_ms,
                       "corpus_tokens":sum(doc_tokens.values()),
                       "long_context_docs_packed":{m:len(v[0]) for m,v in packed.items()}}|store_info
        print(f"[{tier}] documents={len(docs)} chunks={len(chunks)} eligible_questions={len(eligible)} "
              f"index={store_info['source']} build_ms={build_ms:.1f}")
    df=pd.DataFrame(rows)
    df.to_csv(output/"metrics.csv",index=False)
    summary=(df.groupby(["tier","method","query_type"])
             .agg(n=("qid","count"),evidence_recall=("evidence_recall","mean"),
                  evidence_precision=("evidence_precision","mean"),evidence_f1=("evidence_f1","mean"),
                  latency_ms_p50=("latency_ms","median"),latency_ms_p95=("latency_ms",lambda x:x.quantile(.95)),
                  retrieved_docs=("retrieved_docs","mean"),context_tokens=("context_tokens","mean")).reset_index())
    summary.to_csv(output/"summary.csv",index=False)
    corpus_stats={}
    for tier in tiers:
        docs=load_documents(corpus,tier,domain)
        corpus_stats[tier]={"documents":len(docs),"words":sum(len(d.text.split()) for d in docs),
                            "characters":sum(len(d.text) for d in docs),
                            "tokens":sum(count(("doc",d.doc_id),d.text) for d in docs)}
    config={"python":platform.python_version(),"platform":platform.platform(),"top_k":top_k,
            "tiers":list(tiers),"token_count_method":count.method,"corpus_stats":corpus_stats,
            "index_stats":configs,"methods":methods+lc_methods,
            "long_context":{"windows":LONG_CONTEXT_WINDOWS,"prompt_reserve_tokens":PROMPT_RESERVE_TOKENS,
                            "packing":"whole documents in corpus (manifest) order until the window is full"},
            "domain":domain.name,"domain_config":domain.source,
            "semantic":semantic,"embedding_model":(embedding_model if semantic=="dense" else None),
            "store":(str(store_dir) if store_dir else None),
            "relevance_judge":({"model":judge.model_name,"threshold":judge.threshold} if judge else None),
            "seed":42,"note":"Retrieval-level evaluation. Answer-level metrics (exact match, set F1, faithfulness) "
                            "come from `lensrag.cli answers`, which needs an LLM."}
    (output/"run_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    return df,summary,config
