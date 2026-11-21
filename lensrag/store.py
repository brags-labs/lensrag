"""Persistent chunk + vector storage in ChromaDB.

One Chroma collection holds one corpus build (e.g. one tier): every chunk's enriched
text, its metadata and, optionally, its embedding vector. The collection metadata
records a fingerprint of the chunks so a stale store is detected and rebuilt instead
of silently reused.

BM25 and TF-IDF are lexical structures that Chroma does not store; they are rebuilt
in memory from the stored chunk texts, which takes about 1-2 s for the L tier.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterable
import numpy as np
from .data import Chunk

FORMAT_VERSION = 2  # v2 adds each chunk's full metadata (meta_json) for domain configs
_BATCH = 2000


def corpus_fingerprint(chunks: Iterable[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.chunk_id.encode()); h.update(c.enriched_text.encode())
    return h.hexdigest()


def document_fingerprint(docs, chunk_params: dict) -> str:
    """Fingerprint of the source documents plus chunking settings.

    Lets a run decide whether the stored chunks are still valid without re-chunking.
    """
    h = hashlib.sha256(repr(sorted(chunk_params.items())).encode())
    for d in docs:
        h.update(f"{d.doc_id}|{d.doc_type}|{d.country}|{d.version}|{d.effective_date}|{d.status}|{d.period}|{d.title}|{d.employee_category}".encode())
        h.update(json.dumps(d.meta, sort_keys=True, default=str).encode())
        h.update(d.text.encode())
    return h.hexdigest()


def _chunk_metadata(c: Chunk, seq: int) -> dict:
    # Chroma metadata values must be str/int/float/bool, so tuples are joined.
    # `seq` keeps the original chunk order, which Chroma does not guarantee on read.
    return {"seq": seq, "doc_id": c.doc_id, "path": c.path, "doc_type": c.doc_type, "country": c.country,
            "version": c.version, "effective_date": c.effective_date, "status": c.status,
            "period": c.period, "entities": "|".join(c.entities), "section_path": c.section_path,
            "text": c.text, "title": c.title, "employee_category": c.employee_category,
            "meta_json": json.dumps(c.meta, sort_keys=True, default=str)}


def _chunk_from(chunk_id: str, enriched_text: str, m: dict) -> Chunk:
    return Chunk(chunk_id=chunk_id, doc_id=m["doc_id"], path=m["path"], doc_type=m["doc_type"],
                 country=m["country"], version=m["version"], effective_date=m["effective_date"],
                 status=m["status"], period=m["period"],
                 entities=tuple(x for x in m["entities"].split("|") if x),
                 section_path=m["section_path"], text=m["text"], enriched_text=enriched_text,
                 title=m["title"], employee_category=m["employee_category"],
                 meta=json.loads(m.get("meta_json") or "{}"))


class ChromaChunkStore:
    """A persistent Chroma collection of chunks (and optional embeddings)."""

    def __init__(self, path: str | Path, collection: str):
        import chromadb
        from chromadb.config import Settings
        self.path = Path(path); self.path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.path), settings=Settings(anonymized_telemetry=False))
        self.name = collection

    # --- lifecycle -----------------------------------------------------------------
    def info(self) -> dict | None:
        """Collection metadata, or None if the collection does not exist yet."""
        try:
            col = self.client.get_collection(self.name)
        except Exception:
            return None
        return dict(col.metadata or {}) | {"count": col.count()}

    def is_current(self, fingerprint: str, embedding_model: str | None) -> bool:
        info = self.info()
        return bool(info) and info.get("format_version") == FORMAT_VERSION \
            and info.get("corpus_fingerprint") == fingerprint \
            and info.get("embedding_model", "") == (embedding_model or "") \
            and info.get("count") == info.get("chunks")

    def write(self, chunks: list[Chunk], fingerprint: str, embeddings: np.ndarray | None = None,
              embedding_model: str | None = None, extra: dict | None = None):
        """Replace the collection with these chunks (and embeddings, if given)."""
        try:
            self.client.delete_collection(self.name)
        except Exception:
            pass
        meta = {"format_version": FORMAT_VERSION, "corpus_fingerprint": fingerprint,
                "chunks": len(chunks), "documents": len({c.doc_id for c in chunks}),
                "embedding_model": embedding_model or "", "hnsw:space": "cosine"} | (extra or {})
        # embedding_function=None: vectors always come from our own pinned encoder.
        col = self.client.create_collection(self.name, metadata=meta, embedding_function=None)
        for i in range(0, len(chunks), _BATCH):
            part = chunks[i:i + _BATCH]
            kwargs = dict(ids=[c.chunk_id for c in part], documents=[c.enriched_text for c in part],
                          metadatas=[_chunk_metadata(c, i + n) for n, c in enumerate(part)])
            if embeddings is not None:
                kwargs["embeddings"] = embeddings[i:i + _BATCH]
            else:
                # Chroma requires a vector per record; a 1-d zero vector marks "no embedding".
                kwargs["embeddings"] = np.zeros((len(part), 1), dtype=np.float32)
            col.add(**kwargs)
        return meta

    def load(self, with_embeddings: bool = False):
        """Return (chunks, embeddings|None) in the original chunk order."""
        col = self.client.get_collection(self.name)
        include = ["documents", "metadatas"] + (["embeddings"] if with_embeddings else [])
        got = col.get(include=include)
        chunks = [_chunk_from(cid, doc, m) for cid, doc, m in zip(got["ids"], got["documents"], got["metadatas"])]
        idx = sorted(range(len(chunks)), key=lambda n: got["metadatas"][n]["seq"])
        chunks = [chunks[n] for n in idx]
        vectors = None
        if with_embeddings and (col.metadata or {}).get("embedding_model"):
            vectors = np.asarray(got["embeddings"], dtype=np.float32)[idx]
        return chunks, vectors
