from __future__ import annotations
import re, math, time
from collections import Counter, defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

TOKEN_RE=re.compile(r"[A-Za-z0-9₹$%]+",re.UNICODE)
def tokenize(text): return [t.lower() for t in TOKEN_RE.findall(text)]

class BM25:
    def __init__(self, texts, k1=1.5, b=.75):
        self.docs=[tokenize(t) for t in texts]
        self.k1,self.b=k1,b
        self.lengths=np.asarray([len(d) for d in self.docs],dtype=np.float32)
        self.avgdl=float(self.lengths.mean()) if len(self.lengths) else 1.0
        self.df=Counter()
        postings=defaultdict(list)
        for i,d in enumerate(self.docs):
            tf=Counter(d); self.df.update(tf.keys())
            for term,freq in tf.items(): postings[term].append((i,freq))
        n=len(self.docs)
        self.postings={}
        self.idf={}
        for term, pairs in postings.items():
            arr=np.asarray(pairs,dtype=np.int32)
            self.postings[term]=(arr[:,0],arr[:,1].astype(np.float32))
            self.idf[term]=math.log(1+(n-self.df[term]+.5)/(self.df[term]+.5))
    def score(self, query, allowed=None):
        scores=np.zeros(len(self.docs),dtype=np.float32)
        allow=None if allowed is None else np.zeros(len(self.docs),dtype=bool)
        if allow is not None: allow[allowed]=True
        for term in tokenize(query):
            if term not in self.postings: continue
            ids,freq=self.postings[term]
            if allow is not None:
                mask=allow[ids]; ids=ids[mask]; freq=freq[mask]
            if len(ids)==0: continue
            dl=self.lengths[ids]
            denom=freq+self.k1*(1-self.b+self.b*dl/max(1,self.avgdl))
            scores[ids]+=self.idf[term]*(freq*(self.k1+1))/denom
        return scores

class HybridIndex:
    """BM25 plus a second scorer: word TF-IDF (default) or dense embeddings.

    For semantic="dense", pass the chunk `vectors` (e.g. loaded from Chroma) and the
    `encoder` that produced them, so queries are embedded with the same model.
    """
    def __init__(self, chunks, semantic="tfidf", vectors=None, encoder=None):
        self.chunks=chunks
        self.semantic=semantic
        texts=[c.enriched_text for c in chunks]
        self.bm25=BM25(texts)
        if semantic=="tfidf":
            self.word=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,max_features=120000,stop_words="english",dtype=np.float32)
            self.Xw=self.word.fit_transform(texts)
        elif semantic=="dense":
            if vectors is None or encoder is None: raise ValueError("dense semantic scoring needs vectors and an encoder")
            if len(vectors)!=len(chunks): raise ValueError("one vector per chunk required")
            self.vectors=np.asarray(vectors,dtype=np.float32); self.encoder=encoder
            self._qcache={}
        else:
            raise ValueError(semantic)
    def _semantic_scores(self, query, allowed):
        if self.semantic=="tfidf":
            return np.asarray((self.word.transform([query]) @ self.Xw[allowed].T).toarray()).ravel()
        if query not in self._qcache: self._qcache[query]=self.encoder.encode([query])[0]
        return np.maximum(self.vectors[allowed] @ self._qcache[query],0)
    def search(self, query, top_k=10, scope_country=None, method="hybrid", where=None, offset=0):
        """Top chunks for `query`, optionally restricted to a country and/or a chunk predicate.

        `offset` skips the best `offset` results, so callers can page through a scope.
        """
        allowed=[i for i,c in enumerate(self.chunks)
                 if (not scope_country or c.country in (scope_country,"ALL","GLOBAL",""))
                 and (where is None or where(c))]
        allowed=np.asarray(allowed,dtype=int)
        if len(allowed)==0: return []
        bm=self.bm25.score(query,allowed)
        bm_local=bm[allowed]
        if method=="bm25":
            score=bm_local/(bm_local.max()+1e-9)
        else:
            dense=self._semantic_scores(query,allowed)
            bm_local=bm_local/(bm_local.max()+1e-9)
            score=.55*bm_local+.45*dense
        # Stable sort: ties break by chunk order, so results are reproducible across machines.
        local_idx=np.argsort(-score,kind="stable")[offset:offset+top_k]
        idx=allowed[local_idx]
        return [(self.chunks[i],float(score[j])) for j,i in zip(local_idx,idx)]

def route_query(question: str):
    """Query type from the shared planner's keyword classifier (see planning.detect_type)."""
    from .planning import detect_type
    return detect_type(question)


def coverage_retrieve(index, plan, scopes, judge=None, page=5, max_rounds=4, workers=1):
    """Per-entity retrieval that keeps going until no scope yields new relevant evidence.

    Each round fetches the next `page` chunks for every still-active scope. With a
    `judge`, a scope stays active only while its new chunks include relevant ones, and
    the loop stops when a whole round adds no relevant evidence (or after `max_rounds`).
    Without a judge every retrieved chunk counts as relevant and one round is run.

    A chunk can serve several scopes (a company-wide table, a contract with two
    counterparties): every scope judges it independently and gets its own hit, so
    evidence is credited to each entity it covers.

    judge(scope, [(chunk, score)]) -> [(chunk, score, payload)] for the relevant chunks.
    With workers > 1 the scopes' pages of a round are judged concurrently (a local server with
    several parallel slots decodes them together); the result is the same as judging in turn.
    Returns (hits, telemetry); hits are (chunk, score, scope_label, payload), one per
    (scope, chunk) pair, best first.
    """
    from .planning import scope_filter
    kept={}; seen={s.key():set() for s in scopes}; offsets={s.key():0 for s in scopes}
    active=list(scopes); evidence_by_scope={s.label:0 for s in scopes}
    rounds=0; converged=False
    for _ in range(max_rounds if judge else 1):
        rounds+=1; next_active=[]; pages=[]
        for sc in active:
            batch=index.search(sc.query,page,where=scope_filter(plan,sc),offset=offsets[sc.key()])
            offsets[sc.key()]+=page
            fresh=[(c,s) for c,s in batch if c.chunk_id not in seen[sc.key()]]
            seen[sc.key()].update(c.chunk_id for c,_ in fresh)
            pages.append((sc,batch,fresh))
        judged=lambda item: [(c,s,None) for c,s in item[2]] if judge is None else (judge(item[0],item[2]) if item[2] else [])
        if workers>1 and judge is not None and len(pages)>1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results=list(pool.map(judged,pages))
        else:
            results=[judged(x) for x in pages]
        for (sc,batch,fresh),relevant in zip(pages,results):
            for c,s,payload in relevant:
                kept.setdefault((sc.key(),c.chunk_id),(c,s,sc.label,payload))
            evidence_by_scope[sc.label]+=len(relevant)
            # A scope continues only while it is still producing new relevant evidence.
            if relevant and len(batch)==page: next_active.append(sc)
        active=next_active
        if not active:
            converged=True; break
    if judge is None: converged=True
    hits=sorted(kept.values(),key=lambda x:x[1],reverse=True)
    per_chunk=Counter(c.chunk_id for c,*_ in hits)
    telemetry={"rounds":rounds,"converged":converged,"scopes":len(scopes),
               "chunks":len(per_chunk),"shared_chunks":sum(1 for n in per_chunk.values() if n>1),
               "scopes_without_evidence":[k for k,v in evidence_by_scope.items() if v==0]}
    return hits,telemetry


# Relevance thresholds per judge model. Scores are on different scales (MS MARCO gives logits,
# the BGE reranker probabilities), so each is calibrated: MS MARCO on the benchmark, BGE on odd
# question ids with even ones held out (results/archive/dense_bge_m3/judge_calibration.csv, docs/LOCAL_MODELS.md).
JUDGE_THRESHOLDS = {"cross-encoder/ms-marco-MiniLM-L-6-v2": -4.0, "BAAI/bge-reranker-v2-m3": 0.05}


def judge_threshold_for(model_name, threshold=None):
    if threshold is not None:
        return threshold
    if model_name not in JUDGE_THRESHOLDS:
        raise ValueError(f"No calibrated threshold for {model_name}: pass --judge-threshold")
    return JUDGE_THRESHOLDS[model_name]


class CrossEncoderJudge:
    """Passage relevance judge for the benchmark: a cross-encoder with an absolute cut-off.

    Stands in for the LLM relevance filter (which needs an API key): a chunk counts as
    relevant when its cross-encoder logit against the question is at least `threshold`.
    """
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2", threshold=0.0, model=None):
        self.model_name,self.threshold=model_name,threshold
        self._model=model
    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model=CrossEncoder(self.model_name)
        return self._model
    def for_question(self, question):
        cache={}  # the score depends only on question and chunk, so shared chunks are scored once
        def judge(scope, items):
            todo=[c for c,_ in items if c.chunk_id not in cache]
            if todo:
                for c,x in zip(todo,self.model.predict([(question,c.enriched_text) for c in todo],batch_size=64)):
                    cache[c.chunk_id]=float(x)
            return [(c,cache[c.chunk_id],None) for c,_ in items if cache[c.chunk_id]>=self.threshold]
        return judge


def method_retrieve(index, question, method, top_k=10, judge_model=None, inventory=None, info=None):
    """Run one benchmark retrieval method. LensRAG methods plan, decompose and cover entities."""
    from .planning import plan_query,build_scopes,build_inventory
    start=time.perf_counter()
    if method=="bm25_topk":
        hits=index.search(question,top_k,method="bm25")
    elif method=="hybrid_topk":
        hits=index.search(question,top_k,method="hybrid")
    elif method in ("lensrag","lensrag_rerank"):
        inventory=inventory or build_inventory(index.chunks)
        plan=plan_query(question,inventory)
        scopes=build_scopes(plan,inventory)
        page=max(4,top_k//2)  # same evidence budget for every scope
        judge=None
        if method=="lensrag_rerank":
            if judge_model is None: raise ValueError("lensrag_rerank needs a relevance judge")
            judge=judge_model.for_question(question)
        found,telemetry=coverage_retrieve(index,plan,scopes,judge=judge,page=page)
        if info is not None:
            info.update(telemetry,planned_type=plan.qtype,fanout=plan.fanout)
        best={}
        for c,s,_,_ in found: best.setdefault(c.chunk_id,(c,s))  # one entry per chunk, best score first
        hits=list(best.values())
    else:
        raise ValueError(method)
    return hits, (time.perf_counter()-start)*1000
