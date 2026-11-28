# LensRAG experiment report

> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.

## Retrieval results by corpus tier

| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| L | bm25_topk | aggregate | 5 | 0.417 | 0.503 | 1.8 |
| L | bm25_topk | comparison | 2 | 0.217 | 0.299 | 2.2 |
| L | bm25_topk | conflict | 5 | 0.333 | 0.114 | 1.8 |
| L | bm25_topk | count | 16 | 0.502 | 0.402 | 1.8 |
| L | bm25_topk | extremum | 11 | 0.391 | 0.315 | 1.9 |
| L | bm25_topk | filter | 5 | 0.117 | 0.127 | 1.8 |
| L | bm25_topk | local | 17 | 0.412 | 0.089 | 2.2 |
| L | bm25_topk | rank | 6 | 0.031 | 0.042 | 1.9 |
| L | bm25_topk | sentiment_shift | 2 | 0.225 | 0.364 | 2.1 |
| L | bm25_topk | temporal | 5 | 0.517 | 0.487 | 1.8 |
| L | bm25_topk | theme | 6 | 0.458 | 0.440 | 1.9 |
| L | bm25_topk | version_diff | 9 | 0.416 | 0.221 | 1.9 |
| L | hybrid_topk | aggregate | 5 | 0.428 | 0.538 | 21.5 |
| L | hybrid_topk | comparison | 2 | 0.192 | 0.282 | 21.7 |
| L | hybrid_topk | conflict | 5 | 0.400 | 0.174 | 21.6 |
| L | hybrid_topk | count | 16 | 0.495 | 0.407 | 21.4 |
| L | hybrid_topk | extremum | 11 | 0.400 | 0.416 | 21.8 |
| L | hybrid_topk | filter | 5 | 0.117 | 0.130 | 21.5 |
| L | hybrid_topk | local | 17 | 0.529 | 0.122 | 21.6 |
| L | hybrid_topk | rank | 6 | 0.047 | 0.062 | 21.5 |
| L | hybrid_topk | sentiment_shift | 2 | 0.237 | 0.380 | 22.4 |
| L | hybrid_topk | temporal | 5 | 0.513 | 0.491 | 21.6 |
| L | hybrid_topk | theme | 6 | 0.542 | 0.550 | 21.4 |
| L | hybrid_topk | version_diff | 9 | 0.188 | 0.114 | 21.3 |
| L | lensrag | aggregate | 5 | 0.443 | 0.582 | 20.5 |
| L | lensrag | comparison | 2 | 0.650 | 0.731 | 244.7 |
| L | lensrag | conflict | 5 | 0.500 | 0.178 | 203.9 |
| L | lensrag | count | 16 | 0.818 | 0.720 | 197.0 |
| L | lensrag | extremum | 11 | 0.845 | 0.597 | 200.8 |
| L | lensrag | filter | 5 | 0.800 | 0.489 | 203.6 |
| L | lensrag | local | 17 | 0.853 | 0.452 | 21.0 |
| L | lensrag | rank | 6 | 0.763 | 0.478 | 202.4 |
| L | lensrag | sentiment_shift | 2 | 0.988 | 0.994 | 247.5 |
| L | lensrag | temporal | 5 | 0.613 | 0.558 | 20.3 |
| L | lensrag | theme | 6 | 0.792 | 0.844 | 21.0 |
| L | lensrag | version_diff | 9 | 0.512 | 0.210 | 215.2 |
| M | bm25_topk | conflict | 5 | 0.600 | 0.309 | 0.4 |
| M | bm25_topk | count | 8 | 0.152 | 0.170 | 0.4 |
| M | bm25_topk | extremum | 6 | 0.100 | 0.100 | 0.4 |
| M | bm25_topk | filter | 5 | 0.117 | 0.127 | 0.5 |
| M | bm25_topk | local | 17 | 0.176 | 0.053 | 0.5 |
| M | bm25_topk | rank | 5 | 0.060 | 0.067 | 0.5 |
| M | bm25_topk | temporal | 5 | 0.623 | 0.484 | 0.4 |
| M | bm25_topk | version_diff | 9 | 0.179 | 0.092 | 0.5 |
| M | hybrid_topk | conflict | 5 | 0.600 | 0.334 | 15.2 |
| M | hybrid_topk | count | 8 | 0.177 | 0.194 | 17.8 |
| M | hybrid_topk | extremum | 6 | 0.133 | 0.133 | 16.9 |
| M | hybrid_topk | filter | 5 | 0.137 | 0.150 | 16.9 |
| M | hybrid_topk | local | 17 | 0.353 | 0.097 | 16.7 |
| M | hybrid_topk | rank | 5 | 0.040 | 0.044 | 15.9 |
| M | hybrid_topk | temporal | 5 | 0.623 | 0.497 | 15.0 |
| M | hybrid_topk | version_diff | 9 | 0.178 | 0.094 | 15.0 |
| M | lensrag | conflict | 5 | 0.600 | 0.191 | 158.4 |
| M | lensrag | count | 8 | 0.796 | 0.552 | 171.7 |
| M | lensrag | extremum | 6 | 1.000 | 0.487 | 175.2 |
| M | lensrag | filter | 5 | 0.780 | 0.439 | 175.4 |
| M | lensrag | local | 17 | 0.794 | 0.438 | 18.4 |
| M | lensrag | rank | 5 | 0.903 | 0.524 | 165.7 |
| M | lensrag | temporal | 5 | 0.613 | 0.605 | 16.1 |
| M | lensrag | version_diff | 9 | 0.178 | 0.191 | 188.3 |
| S | bm25_topk | count | 4 | 0.675 | 0.725 | 0.1 |
| S | bm25_topk | extremum | 5 | 0.920 | 0.781 | 0.2 |
| S | bm25_topk | filter | 4 | 0.900 | 0.922 | 0.2 |
| S | bm25_topk | local | 17 | 1.000 | 0.263 | 0.2 |
| S | bm25_topk | rank | 4 | 0.850 | 0.876 | 0.2 |
| S | hybrid_topk | count | 4 | 0.700 | 0.742 | 71.7 |
| S | hybrid_topk | extremum | 5 | 0.720 | 0.741 | 15.6 |
| S | hybrid_topk | filter | 4 | 0.875 | 0.909 | 15.5 |
| S | hybrid_topk | local | 17 | 1.000 | 0.265 | 15.4 |
| S | hybrid_topk | rank | 4 | 0.800 | 0.849 | 14.7 |
| S | lensrag | count | 4 | 1.000 | 0.912 | 161.6 |
| S | lensrag | extremum | 5 | 1.000 | 0.757 | 149.5 |
| S | lensrag | filter | 4 | 1.000 | 0.871 | 151.7 |
| S | lensrag | local | 17 | 1.000 | 0.833 | 15.7 |
| S | lensrag | rank | 4 | 0.975 | 0.848 | 150.7 |

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