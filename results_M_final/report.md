# LensRAG experiment report

> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.

## Retrieval results by corpus tier

| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| M | bm25_topk | conflict | 5 | 0.533 | 0.227 | 0.6 |
| M | bm25_topk | count | 8 | 0.013 | 0.014 | 0.4 |
| M | bm25_topk | extremum | 6 | 0.067 | 0.067 | 0.6 |
| M | bm25_topk | filter | 5 | 0.060 | 0.060 | 0.5 |
| M | bm25_topk | local | 17 | 0.176 | 0.054 | 0.7 |
| M | bm25_topk | rank | 5 | 0.020 | 0.024 | 0.5 |
| M | bm25_topk | temporal | 5 | 0.600 | 0.271 | 0.4 |
| M | bm25_topk | version_diff | 9 | 0.222 | 0.100 | 0.6 |
| M | hybrid_topk | conflict | 5 | 0.633 | 0.270 | 2.9 |
| M | hybrid_topk | count | 8 | 0.013 | 0.014 | 2.9 |
| M | hybrid_topk | extremum | 6 | 0.000 | 0.000 | 3.0 |
| M | hybrid_topk | filter | 5 | 0.000 | 0.000 | 3.3 |
| M | hybrid_topk | local | 17 | 0.118 | 0.037 | 2.9 |
| M | hybrid_topk | rank | 5 | 0.000 | 0.000 | 3.2 |
| M | hybrid_topk | temporal | 5 | 0.600 | 0.267 | 2.8 |
| M | hybrid_topk | version_diff | 9 | 0.167 | 0.079 | 3.5 |
| M | lensrag | conflict | 5 | 0.233 | 0.165 | 10.1 |
| M | lensrag | count | 8 | 0.338 | 0.156 | 12.3 |
| M | lensrag | extremum | 6 | 0.833 | 0.279 | 12.3 |
| M | lensrag | filter | 5 | 0.500 | 0.230 | 14.1 |
| M | lensrag | local | 17 | 0.647 | 0.263 | 1.6 |
| M | lensrag | rank | 5 | 0.600 | 0.284 | 10.9 |
| M | lensrag | temporal | 5 | 0.600 | 0.210 | 16.8 |
| M | lensrag | version_diff | 9 | 0.111 | 0.017 | 16.7 |

## Hypothesis status

- **H1 (global vs local gap):** evaluate the global/local difference using `bm25_topk` and `hybrid_topk` rows. The current retrieval benchmark can test evidence retrieval differences, but not generated-answer accuracy or long-context prompting.
- **H2 (LensRAG answer quality):** not established by this run. The experiment compares evidence recall/F1; exact-match answer accuracy and set-level answer F1 require executing the LLM extraction and answer-generation stages.
- **H3 (verification):** not established by this run. Completeness flags can be computed from evidence coverage, but conflict detection precision/recall requires a labelled conflict benchmark and verifier predictions.

## Interpretation guardrails

- Retrieval evidence recall is the fraction of gold evidence document IDs present in retrieved documents.
- Evidence precision is the fraction of retrieved unique documents that are gold evidence documents. It is strict and may penalise useful supporting documents not listed in gold.
- Latency is retrieval wall-clock time on this machine and is not comparable across machines without hardware details.
- The current dense-like component is TF-IDF lexical vector similarity, not a neural embedding model. Call this a BM25 + TF-IDF hybrid baseline, not a production dense retriever.
- Do not use illustrative numbers in the source PDF as experiment outcomes.

## Next required experiment stage

Add a fixed LLM extraction adapter, record model/version/prompt, parse evidence records `(entity, value, span, doc_id)`, run deterministic aggregation, and score generated answers against the 89 gold questions. Then evaluate conflict flags against `ledger/conflicts.json` and legitimate version changes as negative controls.