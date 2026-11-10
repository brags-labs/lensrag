# LensRAG implementation audit against the capstone PDF

Audit basis: `MTechPESJan25AGrp5_1.pdf`, Section 1.1.1 (Recommended Approach), Figures 1.1–1.2, and Table 3.1. This audit compares those stated steps with the Python source in `lensrag/`.

## Executive finding

The current project is a useful retrieval prototype, but it is **not yet a complete implementation of the LensRAG pipeline described in the PDF**. The document parser, context-enriched chunk headers, BM25 index, lexical TF-IDF hybrid retrieval, and some deterministic aggregation/validation utilities exist. Several central stages in the PDF are missing or only approximated: dense embeddings, a general ingestion-time entity list, query routing in the live retrieval path, reranking, adaptive per-entity retrieval with a stopping condition, LLM relevance filtering and evidence extraction, map–reduce theme/sentiment analysis, and end-to-end verification and answer generation.

No change to the research algorithm is recommended by this audit. The implementation should be completed to match the PDF before proposing algorithmic extensions.

## Step-by-step comparison

| PDF requirement | Current Python implementation | Audit status |
|---|---|---|
| Parse each document into a chapter/section/table structure; do not split tables | `data.py` splits Markdown on heading lines and tries to keep table paragraphs intact. It does not build a full document tree; table detection depends on every non-empty line beginning with `|`. | Partial |
| Prepend document title and section path | `chunk_document()` prepends `doc_id` and Markdown heading path. A human-readable document title is not separately extracted. | Partial |
| Include scope (country, employee category), version, effective date and mentioned entities in each chunk header | Header includes country, version, effective date, status, period and a country name derived from a country code. Employee category and general entities mentioned in the chunk are not extracted. | Partial |
| Build hybrid index with BM25 and dense embeddings | `HybridIndex` builds BM25 plus scikit-learn word n-gram TF-IDF. TF-IDF is lexical sparse similarity, **not a dense neural embedding**. No vector embedding model is used. | Partial / not faithful |
| Build an ingestion-time entity list (e.g. all countries with addenda) | Country codes/names are hard-coded in `data.py` / `retrieval.py`. There is no general entity inventory extracted from corpus documents. | Partial |
| Classify query type (local, count, rank, filter, theme, sentiment, etc.) | `route_query()` has keyword rules, but `method_retrieve()` does not call it to select a full query pipeline. | Partial / not wired into retrieval |
| Local query: hybrid retrieval, rerank, generate | Local path is not separately implemented; BM25/Hybrid top-k methods return chunks only. No reranker or answer generator. | Missing |
| Global query: select relevant entities from entity list | `query_countries()` detects country names in the query; if none are explicit, LensRAG loops through a fixed list of all country names. | Partial |
| Per-entity adaptive retrieval; continue until no new relevant passages/entities | Current LensRAG makes one scoped retrieval call per selected country and deduplicates chunk IDs. It does not iterate adaptively or implement the PDF's stopping condition. | Missing / partial |
| LLM filter each candidate and extract value plus evidence span into query-time records | `aggregation.py` validates records if supplied, but no LLM passage filter/extractor creates those records and no retrieval-to-extraction pipeline is connected. | Missing |
| Deterministic code aggregation (count, extrema, ranking, top-k, filter) | Basic helper functions exist in `aggregation.py`. They are standalone utilities, not wired into a complete query execution flow. | Partial |
| Theme/sentiment map–reduce, grouped by period | `reduce_labels()` can count already-labelled records. No upstream classifier/LLM labelling or map–reduce summarisation is implemented. | Partial |
| Verify completeness against entity list, flag conflicts, verify evidence support | Helper functions exist for simple completeness and same-version differing-value checks. They are not connected to query execution; effective-date/supersession handling and claim-level support verification are not complete. | Partial |
| Generate final answer with cited evidence and flags | No answer-generation stage exists in this retrieval-only prototype. | Missing |

## Index lifecycle: what happens now

- During an experiment run, the code loads each requested tier, chunks it, and builds a fresh in-memory `HybridIndex` for that tier.
- The index is reused for all benchmark questions within that tier during that run. It is **not rebuilt for every question**.
- The index is not persisted to disk. A later run rebuilds it.
- `run_experiment()` loops over S, M and L by default, so it builds three separate in-memory indexes for the experiment. For deployment, the intended full-corpus configuration should build one index over L and reuse it across queries, rebuilding or updating it only when source documents change.
- BM25 uses an inverted postings structure. The TF-IDF hybrid component scores the query against the sparse document matrix for all indexed chunks (or the scope-filtered subset). Thus, it is already index-based retrieval, but it does not yet implement the PDF's dense-vector component or persistent index lifecycle.

## Important interpretation of S, M and L

S, M and L are experimental corpus-size tiers used to evaluate scaling. They are not three indexes that a deployed HR assistant must search simultaneously. For the final full-corpus system, use L as the active corpus and build/reuse its index. Keep S and M only for controlled scalability experiments.

## Recommended implementation order (without changing the algorithm)

1. **Complete ingestion metadata:** parse titles, section hierarchy, table blocks, scope including employee category where present, version/effective date, and mentioned entities; generate the entity inventory from corpus metadata/content rather than a fixed country list alone.
2. **Implement the specified hybrid index:** retain BM25 and add a named, version-pinned dense embedding model; persist the BM25/vector indexes and metadata; support rebuild-on-change or incremental document updates.
3. **Wire the query router:** make local/global/count/rank/filter/theme/sentiment query types select the corresponding PDF-defined path.
4. **Complete global coverage retrieval:** select entities, run per-entity hybrid retrieval, filter/extract evidence, and continue adaptively until the stated stopping condition is met.
5. **Connect aggregation and verification:** validated evidence records should flow into deterministic aggregation, completeness checks, version-aware conflict checks, and claim-to-span verification.
6. **Implement theme/sentiment map–reduce and final answer generation** as specified in the PDF.
7. **Evaluate the full L corpus (495 retrievable documents)** as the main experiment; retain S/M/L runs only to report scaling.

## What must not be claimed yet

Until the missing stages above are implemented, do not describe the current code as a full LensRAG implementation, a dense-embedding system, or an end-to-end answer-generation system. Its current metrics measure document-level evidence retrieval only; they do not establish answer accuracy, faithfulness, complete corpus coverage, or the performance of the full algorithm.

## Implementation status after the full-runtime extension

The separate `lensrag.full` runtime has now been added. It does not rewrite the original benchmark runner or its historical metrics. It adds:

- Persistent BM25 + sentence-transformers dense-vector indexing (`full/index.py`).
- Corpus-derived country/global entity inventory and enriched title/employee-category headers.
- LLM query routing, local reranking/generation, entity selection, bounded adaptive retrieval, evidence extraction, numeric deterministic aggregation, theme/sentiment map–reduce, verification and final cited answer generation (`full/pipeline.py`).
- OpenAI-compatible JSON/text LLM adapter (`full/llm.py`).
- `build-index` and `ask` CLI commands.

The code is unit-tested for index persistence, stale-index detection, entity inventory counts and existing core functions. A complete provider-backed answer run has **not** been executed in this build because it requires installing the optional neural/LLM dependencies, downloading the embedding model and supplying a valid API key. The original methodology audit remains valid for the old experiment runner; the new runtime is the implementation path for the missing stages.

Remaining engineering/research caveats: Markdown document parsing is heuristic rather than a universal document AST; employee-category metadata is populated only when present in front matter; entity expansion is limited to the ingestion inventory and a configured maximum number of rounds; cross-encoder reranking is optional; LLM verification requires its own labelled evaluation set; and map–reduce completeness depends on retrieval coverage. Record model names/versions, prompts, provider, token/cost usage and convergence telemetry in any final experiment.
