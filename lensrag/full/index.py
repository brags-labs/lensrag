from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from ..retrieval import BM25
from ..data import Chunk
from ..embeddings import DenseEncoder
from ..store import ChromaChunkStore, corpus_fingerprint  # re-exported for pipeline.py

__all__ = ["DenseEncoder", "PersistentHybridIndex", "corpus_fingerprint"]

class PersistentHybridIndex:
    """BM25 + dense neural embeddings + metadata; optional TF-IDF fallback is explicit."""
    FORMAT_VERSION = 2  # v2: chunks and vectors live in ChromaDB (v1 was a pickle file)
    COLLECTION = "lensrag_index"
    def __init__(self, chunks: list[Chunk], encoder: DenseEncoder | None = None, allow_lexical_fallback=False, vectors=None):
        if not chunks: raise ValueError("Cannot index an empty corpus")
        self.chunks = chunks
        self.texts = [c.enriched_text for c in chunks]
        self.bm25 = BM25(self.texts)
        self.encoder = encoder
        self.embedding_kind = "dense" if encoder else "tfidf_fallback"
        if encoder:
            self.vectors = encoder.encode(self.texts) if vectors is None else np.asarray(vectors, dtype=np.float32)
            self.vectorizer = None
        elif allow_lexical_fallback:
            self.vectorizer = TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True, max_features=120000, stop_words="english", dtype=np.float32)
            self.matrix = self.vectorizer.fit_transform(self.texts)
            self.vectors = None
        else:
            raise RuntimeError("Dense encoder required. Set allow_lexical_fallback=True only for offline development.")
        self._metadata = [{"country":c.country,"doc_type":c.doc_type,"status":c.status,"period":c.period,"doc_id":c.doc_id} for c in chunks]

    def search(self, query, top_k=10, countries=None, doc_types=None, method="hybrid", where=None, offset=0):
        """Hybrid search with optional country/doc-type/predicate filters; `offset` pages results."""
        allowed=np.arange(len(self.chunks))
        if where is not None:
            allowed=np.asarray([i for i in allowed if where(self.chunks[i])],dtype=int)
        if countries:
            allowed=np.asarray([i for i in allowed if self.chunks[i].country in set(countries)|{"ALL","GLOBAL",""}],dtype=int)
        if doc_types:
            allowed=np.asarray([i for i in allowed if self.chunks[i].doc_type in set(doc_types)],dtype=int)
        if not len(allowed): return []
        bm=self.bm25.score(query, allowed); bm=bm[allowed]
        if bm.max()>0: bm=bm/(bm.max()+1e-9)
        if method=="bm25": scores=bm
        else:
            if self.embedding_kind=="dense":
                qv=self.encoder.encode([query])[0]
                semantic=self.vectors[allowed] @ qv
                semantic=np.maximum(semantic,0)
            else:
                qv=self.vectorizer.transform([query]); semantic=np.asarray((qv @ self.matrix[allowed].T).toarray()).ravel()
            scores=.5*bm+.5*semantic
        loc=np.argsort(-scores,kind="stable")[offset:offset+max(1,int(top_k))]
        return [(self.chunks[int(allowed[j])],float(scores[j])) for j in loc if scores[j]>0]

    def save(self, directory: str | Path, corpus_fingerprint: str):
        """Persist chunks, metadata and dense vectors to a ChromaDB store in `directory`.

        BM25 (and the TF-IDF fallback) are rebuilt from the stored texts on load.
        """
        directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
        model=getattr(self.encoder,"model_name",None)
        ChromaChunkStore(directory/"chroma",self.COLLECTION).write(
            self.chunks,corpus_fingerprint,self.vectors if self.embedding_kind=="dense" else None,model)
        meta={"format_version":self.FORMAT_VERSION,"store":"chromadb","corpus_fingerprint":corpus_fingerprint,
              "chunks":len(self.chunks),"documents":len({c.doc_id for c in self.chunks}),
              "embedding_kind":self.embedding_kind,"embedding_model":model}
        (directory/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
        return meta

    @classmethod
    def load(cls, directory: str | Path, expected_fingerprint: str | None=None):
        directory=Path(directory); meta=json.loads((directory/"metadata.json").read_text())
        if meta.get("format_version")!=cls.FORMAT_VERSION: raise ValueError("Index format mismatch; rebuild index")
        if expected_fingerprint and meta.get("corpus_fingerprint")!=expected_fingerprint: raise ValueError("Corpus changed; rebuild index")
        store=ChromaChunkStore(directory/"chroma",cls.COLLECTION)
        if not store.is_current(meta["corpus_fingerprint"],meta.get("embedding_model")): raise ValueError("Chroma store incomplete or stale; rebuild index")
        chunks,vectors=store.load(with_embeddings=meta["embedding_kind"]=="dense")
        if meta["embedding_kind"]=="dense":
            return cls(chunks,encoder=DenseEncoder(meta["embedding_model"]),vectors=vectors),meta
        return cls(chunks,allow_lexical_fallback=True),meta
