# LensRAG: BragsLabs 2M-token corpus experiment

Reproducible evaluation scaffold for the LensRAG method described in `docs/LensRAG_methodology.pdf`.

## What this project tests
- Conventional sparse top-k retrieval baseline.
- Hybrid BM25 + TF-IDF retrieval baseline.
- LensRAG-style context-enriched chunking, query routing, entity-scoped retrieval, evidence-record validation, deterministic aggregation, completeness checks, and same-version conflict detection.
- Corpus scaling across S / M / L tiers.
- Retrieval coverage, evidence-document recall, latency, index size, and token estimates.

**Important research-integrity note:** this first runnable experiment measures retrieval/evidence coverage, not LLM answer accuracy. No generated answer accuracy or hypothesis acceptance is fabricated. To measure extraction accuracy, faithfulness, and theme/sentiment quality, connect a fixed LLM and complete the gold-answer evaluator described in `docs/EXPERIMENT_PROTOCOL.md`.

## Dataset
The original uploaded corpus archive is preserved at `data/bragslabs_corpus.zip`. It contains:
- 519 archive entries, 501 Markdown documents
- manifest tiers: S=47, M=200, L=253 entries (tier is cumulative by inclusion)
- 495 retrievable documents; 5 marked `retrieval_exclude`
- 89 gold questions in `gold/questions.jsonl`
- ledgers for policy values, conflicts, and synthetic ticket/grievance/exit/survey records.

The experiment measured 1,660,802 whitespace-delimited words in the retrievable L corpus. Its current fallback estimates 2,208,867 tokens (words × 1.33); this is an estimate, not tokenizer-exact. Install `tiktoken` and rerun to record cl100k_base counts.

## Quick start
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
python -m lensrag.cli inspect
python -m lensrag.cli run --tiers S M L --top-k 10 --output results
python -m lensrag.cli report --input results/metrics.csv --output results/report.md
```

The CLI extracts the corpus archive to `data/extracted/` on first run. It never modifies the source ZIP.

## Optional dense embeddings
The default hybrid experiment uses BM25 + word TF-IDF so it runs on CPU without model downloads or API credentials. For a production-like dense retrieval extension, install:
```bash
pip install sentence-transformers faiss-cpu
```
Then implement/enable the optional adapter in `docs/EXTENSIONS.md`. Do not compare embedding models without recording exact model IDs and versions.

## Outputs
- `results/metrics.csv`: per-question/per-method retrieval metrics
- `results/summary.csv`: aggregated metrics by tier and method
- `results/latency.png`: latency comparison
- `results/recall.png`: evidence recall comparison
- `results/report.md`: generated descriptive report and hypothesis status
- `results/run_config.json`: reproducibility metadata

## Ground truth discipline
The gold benchmark is read from the archive's `gold/questions.jsonl`. Evidence document IDs are used only for scoring after retrieval. They are never passed to the retriever. Tier `min_tier` controls which questions are eligible at each corpus size. The reports distinguish:
- retrieval evidence recall (measured here),
- exact answer accuracy (not measured by this retrieval-only run),
- statistical support for H1/H2/H3 (not claimed unless the relevant outcomes are actually measured).

## Research hypotheses
H1: standard top-k RAG scores significantly lower on global than local questions; long-context prompting narrows the gap only while the corpus fits.
H2: routed LensRAG achieves higher set-level F1 and exact-match accuracy on global questions than baselines without reducing local accuracy.
H3: completeness/conflict checks flag most incomplete/conflicting answers with a low false-alarm rate.

See `results/report.md` for the executed experiment and `docs/EXPERIMENT_PROTOCOL.md` before interpreting results. Run unit tests with `python -m unittest discover -s tests`.

## End-to-end LensRAG runtime (PDF-aligned implementation)

The original retrieval-only experiment remains unchanged. A separate runtime is available in `lensrag/full/` and follows the PDF's two query paths: local retrieve/rerank/generate and global entity selection, adaptive per-entity retrieval, LLM evidence extraction, deterministic aggregation or theme/sentiment map–reduce, verification, and cited answer generation.

### Install full runtime

```bash
pip install -r requirements.txt
pip install -r requirements-full.txt
```

The first build downloads the configured sentence-transformers model. Set `OPENAI_API_KEY` and optionally `LENSRAG_LLM_MODEL` / `OPENAI_BASE_URL` for query-time LLM stages.

### Build the persistent L-tier index once

```bash
python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L
```

### Ask a question (index is reused)

```bash
# PowerShell: $env:OPENAI_API_KEY="..."
# macOS/Linux: export OPENAI_API_KEY="..."
python -m lensrag.cli ask "Compare annual leave entitlements across all countries" --index-dir artifacts/index_L
```

The persisted index contains BM25 postings, dense vectors, chunk metadata and an entity inventory. Rebuild it when source documents change. Pickle artifacts must only be loaded from a trusted local directory created by this application.

### Offline smoke test (no neural model/API key)

The complete runtime intentionally does not silently substitute TF-IDF for dense embeddings. The legacy benchmark remains runnable offline. To exercise the pipeline without external models, instantiate `PersistentHybridIndex(..., allow_lexical_fallback=True)` in a development test; this fallback must not be reported as dense LensRAG.

### Provider and research limitations

- The default dense encoder is `sentence-transformers/all-MiniLM-L6-v2`; record its exact revision in final experiments.
- The LLM adapter uses OpenAI-compatible Chat Completions with JSON mode. Compatible providers can be configured through `OPENAI_BASE_URL` and a provider key.
- Cross-encoder reranking is optional and falls back to hybrid rank if unavailable.
- Entity-level adaptive retrieval is bounded by the inventory and configured round limit; this is a safety cap. Log this cap and report whether convergence occurred.
- Counts/ranks/extrema are computed in Python from extracted records; LLMs do not do arithmetic.
- Theme/sentiment map–reduce labels each retrieved passage, then summarizes grouped labels. Coverage is limited to retrieved passages and must be disclosed.
