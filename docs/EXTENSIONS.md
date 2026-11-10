# Extensions to complete the full LensRAG pipeline

## Neural dense embeddings
Replace or complement TF-IDF with a fixed sentence-transformers model (e.g. `BAAI/bge-m3`). Record model ID, revision, embedding dimension, normalization, chunk text field, and index configuration. Build once per corpus tier and persist vectors. Do not call a TF-IDF vectorizer a neural embedding.

## LLM evidence extraction
For each candidate passage ask for strict JSON:
```json
{"relevant": true, "entity": "India", "value": 10, "unit": "working days",
 "evidence_span": "exact supporting quote", "doc_id": "POL-v3.0-CH39"}
```
Validate JSON, require evidence span substring match, and retain provenance. Reject unsupported values. Store only temporary query-time evidence records; do not build a permanent SQL schema over the corpus.

## Deterministic aggregation
Use Python over validated records for count, min/max, sort, top-k, filter and comparison. Define tie handling and missing-value policy before running evaluation. Never ask an LLM to perform arithmetic.

## Themes and sentiment
Map each relevant ticket/grievance/exit-note passage to a controlled theme and sentiment label; reduce by period and country. Since the supplied ledger contains sentiment labels not explicitly present in document text, use a text-only classifier or LLM at inference. Ledger labels are ground truth only. Report agreement against the ledger and manually audit a stratified sample.

## Verification
- Completeness: compare retrieved/extracted entities with the query's expected entity universe derived from corpus metadata and gold benchmark only for evaluation.
- Conflicts: compare values by entity, section, version and effective date. Distinguish a stale superseded statement from an active same-scope contradiction.
- Evidence support: require each answer claim to cite a source document and exact span.
- Negative controls: legitimate policy version changes must not be flagged as conflicts.

## Long-context baseline
Concatenate documents in a predeclared order and provide a single model call. Record exact model, context limit, truncation and prompt. Run only at sizes the model actually accepts; do not claim 2M-token coverage if truncation occurred.
