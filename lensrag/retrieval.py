from __future__ import annotations
import re, math, time
from collections import Counter, defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from .data import Chunk, COUNTRY_NAMES

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
    def __init__(self, chunks):
        self.chunks=chunks
        texts=[c.enriched_text for c in chunks]
        self.bm25=BM25(texts)
        self.word=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,max_features=120000,stop_words="english",dtype=np.float32)
        self.Xw=self.word.fit_transform(texts)
    def search(self, query, top_k=10, scope_country=None, method="hybrid"):
        if scope_country:
            allowed=np.asarray([i for i,c in enumerate(self.chunks) if c.country in (scope_country,"ALL","")],dtype=int)
        else:
            allowed=np.arange(len(self.chunks),dtype=int)
        if len(allowed)==0: return []
        bm=self.bm25.score(query,allowed)
        bm_local=bm[allowed]
        if method=="bm25":
            score=bm_local/(bm_local.max()+1e-9)
        else:
            q1=self.word.transform([query])
            Xw=self.Xw[allowed]
            dense=np.asarray((q1 @ Xw.T).toarray()).ravel()
            bm_local=bm_local/(bm_local.max()+1e-9)
            score=.55*bm_local+.45*dense
        take=min(top_k,len(allowed))
        local_idx=np.argpartition(score,-take)[-take:]
        local_idx=local_idx[np.argsort(score[local_idx])[::-1]]
        idx=allowed[local_idx]
        return [(self.chunks[i],float(score[j])) for j,i in zip(local_idx,idx)]

def route_query(question: str):
    q=question.lower()
    if any(x in q for x in ["theme","common","grievance","reason","sentiment","changed since","shift"]):
        return "theme" if "theme" in q or "common" in q or "reason" in q else "sentiment"
    if any(x in q for x in ["how many","in how many","count"]): return "count"
    if any(x in q for x in ["rank","longest","shortest","highest","lowest","top "]): return "rank"
    if any(x in q for x in ["which countries","in which countries","at least","more than","less than"]): return "filter"
    if any(x in q for x in ["conflict","contradict","inconsistent"]): return "conflict"
    return "local"

def query_countries(question):
    q=question.lower()
    return [name for name in COUNTRY_NAMES if name.lower() in q]

def method_retrieve(index, question, method, top_k=10):
    start=time.perf_counter()
    if method=="bm25_topk":
        hits=index.search(question,top_k,method="bm25")
    elif method=="hybrid_topk":
        hits=index.search(question,top_k,method="hybrid")
    elif method=="lensrag":
        # Entity list is derived at ingestion from corpus metadata.
        explicit=query_countries(question)
        entities=explicit or COUNTRY_NAMES
        by_id={}
        # One scoped query per entity; repeated retrieval is stopped when no new doc appears.
        for entity in entities:
            code=next((c for c,n in {"AE":"United Arab Emirates","AU":"Australia","CA":"Canada","DE":"Germany","IE":"Ireland","IN":"India","NL":"Netherlands","SG":"Singapore","UK":"United Kingdom","US":"United States"}.items() if n==entity),None)
            q=f"{question} {entity}"
            batch=index.search(q,top_k=max(4,top_k//2),scope_country=code,method="hybrid")
            for c,s in batch:
                if c.chunk_id not in by_id: by_id[c.chunk_id]=(c,s)
        hits=sorted(by_id.values(),key=lambda x:x[1],reverse=True)
    else:
        raise ValueError(method)
    return hits, (time.perf_counter()-start)*1000
