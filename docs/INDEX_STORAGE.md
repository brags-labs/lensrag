# Persistent index storage with ChromaDB

Before this change, every `run` re-read the corpus, re-chunked it and rebuilt all indexes in memory, and the full runtime saved its index as a Python pickle. Now chunks, their metadata and (optionally) dense embedding vectors are stored in [ChromaDB](https://docs.trychroma.com/) and reused until the corpus changes.

## What is stored, and what is rebuilt

| Structure | Where it lives | Why |
|---|---|---|
| Chunk text with its context header (`enriched_text`) | ChromaDB `documents` | Source of truth for every other index |
| Chunk metadata: doc id, type, country, version, effective date, status, period, section, entities, title, employee category, original order (`seq`), and every front-matter field as JSON (`meta_json`) | ChromaDB `metadatas` | Rebuilds `Chunk` objects exactly, including domain-specific fields such as `parties` or `jurisdiction`; usable for metadata filters |
| Dense embedding per chunk (`--semantic dense`) | ChromaDB `embeddings` (cosine space) | Expensive to compute (about 20 s for tier L on an M-series Mac); worth storing |
| Corpus fingerprint, chunk/document counts, embedding model, format version | Collection metadata | Detects a stale store; it is rebuilt, never silently reused |
| BM25 postings and the TF-IDF matrix | Rebuilt in memory from the stored texts | Lexical structures Chroma does not hold; rebuilding takes about 1–2 s for L |

Vectors are always produced by the project's own pinned encoder (`embedding_function=None` on the collection), so Chroma never embeds text with a different default model.

Scoring stays exact: the stored vectors are loaded into memory and scored with a dot product against every chunk in scope, the same way as before. This keeps benchmark results reproducible; Chroma's approximate nearest-neighbour search is not used for scoring.

## Layout on disk

```
artifacts/                         (git-ignored)
  chroma/                          benchmark store, one collection per domain, tier and scorer
    lensrag_hr_S_tfidf, lensrag_hr_M_tfidf, lensrag_hr_L_tfidf
    lensrag_hr_S_dense, lensrag_hr_M_dense, lensrag_hr_L_dense
  index_L/                         full runtime (build-index / ask)
    chroma/   collection "lensrag_index"
    metadata.json
    entities.json
```

## When the store is rebuilt

**Benchmark (`run`).** A tier's collection is reused only if all of these match:
- the fingerprint of that tier's source documents (text and front-matter fields);
- the chunking settings (`max_words=260`, `overlap_words=40`);
- the domain config's fields, defaults and header template (`docs/DOMAINS.md`);
- the scorer (`tfidf` or `dense`) and the embedding model;
- the store's format version;
- the stored chunk count.

Otherwise the collection is dropped and rewritten.

**Full runtime (`ask`).** `PersistentHybridIndex.load` refuses a store whose fingerprint, format version or contents do not match `metadata.json`. Old pickle indexes (format v1) are rejected; rebuild them.

## Setup steps

1. Install the dependencies (now includes `chromadb`):
   ```bash
   pip install -r requirements.txt
   ```
2. Run the benchmark. The first run builds and stores each tier; later runs load from `artifacts/chroma`:
   ```bash
   python -m lensrag.cli run --tiers S M L --top-k 10 --output results --rerank
   ```
   Each tier prints `index=built+stored` or `index=chroma`. `run_config.json` records the source and the load/build times under `index_stats`.
3. Optional: use dense embeddings instead of TF-IDF as the second scorer fused with BM25:
   ```bash
   python -m lensrag.cli run --tiers S M L --top-k 10 --output results_dense --semantic dense --rerank
   ```
4. Optional flags:
   - `--store DIR` chooses another store location;
   - `--no-store` restores the old fully in-memory behaviour;
   - `--embedding-model NAME` pins a different sentence-transformers model, which builds a separate store.
5. Full runtime: build once, then ask questions against the stored index:
   ```bash
   python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L
   ```
   ```bash
   python -m lensrag.cli ask "Which countries offer at least 25 days of annual leave?" --index-dir artifacts/index_L
   ```
6. To force a rebuild, delete the store directory (`artifacts/chroma` or `artifacts/index_L`).

## Measured effect (MacBook, Python 3.13, tier L, 13,187 chunks)

| Scorer | First run (build + store) | Later runs (load from Chroma) |
|---|---|---|
| TF-IDF | 9.5 s | 2.4 s |
| Dense (all-MiniLM-L6-v2) | 22.5 s | 1.6 s |

For TF-IDF the original in-memory build took about 1.6 s, so storage mainly adds persistence and inspectability. For dense embeddings it avoids re-encoding every chunk on each run. Retrieval scores from a stored index are identical to a freshly built one: two consecutive runs produced the same per-question results.

The full store for both scorers and all three tiers is about 500 MB on disk.

## Code map

| File | Role |
|---|---|
| `lensrag/store.py` | `ChromaChunkStore` (write, load, freshness check) plus corpus and document fingerprints |
| `lensrag/embeddings.py` | `DenseEncoder`, the shared sentence-transformers wrapper |
| `lensrag/retrieval.py` | `HybridIndex(chunks, semantic="tfidf" or "dense", vectors, encoder)` |
| `lensrag/experiment.py` | `tier_index()` reuses or rebuilds a tier's store; records the source in `run_config.json` |
| `lensrag/full/index.py` | `PersistentHybridIndex.save/load` now use Chroma instead of pickle |
| `tests/test_store.py` | Round-trip, order, staleness and reuse tests |

## Related fix: unique chunk ids

Chroma requires unique record ids, which exposed a bug: `chunk_document` restarted numbering in every section, so different chunks of one document shared ids such as `POL-v3.0-CH39::C0000`. Besides breaking storage, LensRAG's merge step treated those distinct chunks as duplicates and dropped them. Chunk ids are now numbered per document, and `test_chunk_ids_are_unique` guards this.

Effect on the benchmark: `bm25_topk`, `hybrid_topk` and `lensrag` scores are unchanged. `lensrag_rerank` changed slightly (tier L F1 0.392 → 0.389), because the reranker now sees chunks that were previously dropped.
