# Full LensRAG runtime guide

## What was added

The original benchmark runner is preserved. The new `lensrag.full` runtime adds:

1. A persistent L-tier index combining BM25 with normalized sentence-transformer embeddings.
2. A corpus-derived entity inventory including country addenda and global-scope documents.
3. LLM query routing to local, count, rank, filter, theme, sentiment, or conflict paths.
4. Local hybrid retrieval, optional cross-encoder reranking, evidence extraction, answer generation and verification.
5. Global entity selection and adaptive per-entity retrieval. The loop expands only to entities already present in the ingestion inventory and records whether it converged before its configured safety limit.
6. LLM passage filtering and structured evidence extraction with verbatim evidence-span validation.
7. Deterministic Python count/rank/extrema/filter operations; numeric values must be emitted as JSON numbers.
8. Theme/sentiment map–reduce, with sentiment labels grouped by period.
9. Completeness, same-version conflict and claim-support verification, followed by a cited final answer.

## Installation and first run

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-full.txt
```

Build the full corpus index once:

```bash
python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L
```

The default encoder is `sentence-transformers/all-MiniLM-L6-v2`. The first run downloads the model. The build command does not require an LLM API key.

Configure an OpenAI-compatible LLM key in the environment, then ask:

```bash
# PowerShell
$env:OPENAI_API_KEY="..."
# macOS/Linux
export OPENAI_API_KEY="..."
python -m lensrag.cli ask "How many countries have a maternity leave addendum?" --index-dir artifacts/index_L
```

`OPENAI_BASE_URL` can point to a compatible gateway. The CLI accepts `--llm-model` on the `ask` command; `LENSRAG_LLM_MODEL` is also supported as the adapter default.

## Re-indexing

The index is built once and persisted. Rebuild it when the corpus changes. The saved metadata includes a SHA-256 fingerprint, chunk/document counts, embedding type and model name. `PersistentHybridIndex.load(..., expected_fingerprint=...)` rejects a stale fingerprint when the caller supplies the current corpus fingerprint.

## Validation

Run:

```bash
python -m compileall -q lensrag
python -m unittest discover -s tests -v
```

The test suite includes an offline lexical fallback test for index persistence. That fallback is for software tests only and must not be reported as dense-embedding performance.

## Important research cautions

- The end-to-end LLM pipeline requires a configured API key and incurs provider cost. No LLM answers or end-to-end answer-accuracy metrics are included in this archive because no provider credentials were supplied for this build.
- The dense index must be built on the target machine after installing `requirements-full.txt`; model weights are downloaded separately and are not bundled.
- The current document parser preserves heading paths and intact Markdown table blocks heuristically; it is not a general-purpose DOCX/PDF parser or a fully typed document AST.
- The cross-encoder reranker is optional and silently falls back to hybrid ranking if unavailable; for a controlled experiment, disable fallback or record the reranker status.
- Adaptive retrieval has a configurable maximum number of rounds as a safety cap. `adaptive_retrieval.converged` reports whether no new entities remained before the cap.
- The current verification stage uses an LLM judge plus deterministic completeness/conflict rules; it is not a formal proof of factual entailment. Evaluate false positives/negatives on a labelled verification set before making H3 claims.
- Theme/sentiment map–reduce summarises retrieved passages, not every raw corpus item unless retrieval coverage is exhaustive. Its coverage limitation must be reported.
- Global completeness is only as reliable as the entity inventory and the LLM extraction of entity/value records.
