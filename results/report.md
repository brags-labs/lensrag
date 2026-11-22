# LensRAG experiment report

> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.

## Retrieval results by corpus tier

| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| L | bm25_topk | aggregate | 5 | 0.417 | 0.503 | 1.9 |
| L | bm25_topk | comparison | 2 | 0.217 | 0.299 | 2.1 |
| L | bm25_topk | conflict | 5 | 0.333 | 0.114 | 2.2 |
| L | bm25_topk | count | 16 | 0.502 | 0.402 | 1.9 |
| L | bm25_topk | extremum | 11 | 0.391 | 0.315 | 2.3 |
| L | bm25_topk | filter | 5 | 0.117 | 0.127 | 2.0 |
| L | bm25_topk | local | 17 | 0.412 | 0.089 | 2.4 |
| L | bm25_topk | rank | 6 | 0.031 | 0.042 | 2.1 |
| L | bm25_topk | sentiment_shift | 2 | 0.225 | 0.364 | 2.5 |
| L | bm25_topk | temporal | 5 | 0.517 | 0.487 | 2.0 |
| L | bm25_topk | theme | 6 | 0.458 | 0.440 | 1.9 |
| L | bm25_topk | version_diff | 9 | 0.416 | 0.221 | 2.1 |
| L | hybrid_topk | aggregate | 5 | 0.428 | 0.538 | 34.9 |
| L | hybrid_topk | comparison | 2 | 0.192 | 0.282 | 30.0 |
| L | hybrid_topk | conflict | 5 | 0.400 | 0.174 | 28.9 |
| L | hybrid_topk | count | 16 | 0.495 | 0.407 | 28.3 |
| L | hybrid_topk | extremum | 11 | 0.400 | 0.416 | 30.0 |
| L | hybrid_topk | filter | 5 | 0.117 | 0.130 | 33.6 |
| L | hybrid_topk | local | 17 | 0.529 | 0.122 | 24.0 |
| L | hybrid_topk | rank | 6 | 0.047 | 0.062 | 29.5 |
| L | hybrid_topk | sentiment_shift | 2 | 0.237 | 0.380 | 30.9 |
| L | hybrid_topk | temporal | 5 | 0.513 | 0.491 | 22.7 |
| L | hybrid_topk | theme | 6 | 0.542 | 0.550 | 35.1 |
| L | hybrid_topk | version_diff | 9 | 0.188 | 0.114 | 29.3 |
| L | lensrag | aggregate | 5 | 0.443 | 0.582 | 22.2 |
| L | lensrag | comparison | 2 | 0.650 | 0.731 | 264.9 |
| L | lensrag | conflict | 5 | 0.500 | 0.178 | 218.8 |
| L | lensrag | count | 16 | 0.818 | 0.720 | 218.7 |
| L | lensrag | extremum | 11 | 0.845 | 0.597 | 221.2 |
| L | lensrag | filter | 5 | 0.800 | 0.489 | 239.7 |
| L | lensrag | local | 17 | 0.853 | 0.452 | 23.5 |
| L | lensrag | rank | 6 | 0.763 | 0.478 | 222.1 |
| L | lensrag | sentiment_shift | 2 | 0.988 | 0.994 | 270.2 |
| L | lensrag | temporal | 5 | 0.613 | 0.558 | 22.5 |
| L | lensrag | theme | 6 | 0.792 | 0.844 | 22.7 |
| L | lensrag | version_diff | 9 | 0.512 | 0.210 | 230.8 |
| L | lensrag_rerank | aggregate | 5 | 0.700 | 0.760 | 876.5 |
| L | lensrag_rerank | comparison | 2 | 0.754 | 0.837 | 16919.4 |
| L | lensrag_rerank | conflict | 5 | 0.400 | 0.196 | 2255.5 |
| L | lensrag_rerank | count | 16 | 0.846 | 0.749 | 3640.6 |
| L | lensrag_rerank | extremum | 11 | 0.876 | 0.607 | 4036.2 |
| L | lensrag_rerank | filter | 5 | 0.883 | 0.488 | 4343.6 |
| L | lensrag_rerank | local | 17 | 1.000 | 0.290 | 849.4 |
| L | lensrag_rerank | rank | 6 | 0.702 | 0.462 | 4778.9 |
| L | lensrag_rerank | sentiment_shift | 2 | 0.963 | 0.981 | 21101.8 |
| L | lensrag_rerank | temporal | 5 | 0.647 | 0.315 | 522.8 |
| L | lensrag_rerank | theme | 6 | 0.833 | 0.889 | 1216.9 |
| L | lensrag_rerank | version_diff | 9 | 0.740 | 0.278 | 4233.1 |
| L | long_context_128k | aggregate | 5 | 0.030 | 0.021 | 0.0 |
| L | long_context_128k | comparison | 2 | 0.000 | 0.000 | 0.0 |
| L | long_context_128k | conflict | 5 | 0.233 | 0.015 | 0.0 |
| L | long_context_128k | count | 16 | 0.125 | 0.071 | 0.0 |
| L | long_context_128k | extremum | 11 | 0.000 | 0.000 | 0.0 |
| L | long_context_128k | filter | 5 | 0.000 | 0.000 | 0.0 |
| L | long_context_128k | local | 17 | 0.000 | 0.000 | 0.0 |
| L | long_context_128k | rank | 6 | 0.000 | 0.000 | 0.0 |
| L | long_context_128k | sentiment_shift | 2 | 0.150 | 0.103 | 0.0 |
| L | long_context_128k | temporal | 5 | 0.800 | 0.197 | 0.0 |
| L | long_context_128k | theme | 6 | 0.042 | 0.004 | 0.0 |
| L | long_context_128k | version_diff | 9 | 0.056 | 0.003 | 0.0 |
| L | long_context_1m | aggregate | 5 | 0.600 | 0.058 | 0.0 |
| L | long_context_1m | comparison | 2 | 0.500 | 0.053 | 0.0 |
| L | long_context_1m | conflict | 5 | 0.933 | 0.011 | 0.0 |
| L | long_context_1m | count | 16 | 0.487 | 0.061 | 0.0 |
| L | long_context_1m | extremum | 11 | 0.255 | 0.011 | 0.0 |
| L | long_context_1m | filter | 5 | 0.360 | 0.024 | 0.0 |
| L | long_context_1m | local | 17 | 0.471 | 0.003 | 0.0 |
| L | long_context_1m | rank | 6 | 0.300 | 0.020 | 0.0 |
| L | long_context_1m | sentiment_shift | 2 | 1.000 | 0.202 | 0.0 |
| L | long_context_1m | temporal | 5 | 1.000 | 0.064 | 0.0 |
| L | long_context_1m | theme | 6 | 0.667 | 0.026 | 0.0 |
| L | long_context_1m | version_diff | 9 | 0.970 | 0.128 | 0.0 |
| L | long_context_full | aggregate | 5 | 1.000 | 0.062 | 0.0 |
| L | long_context_full | comparison | 2 | 1.000 | 0.234 | 0.0 |
| L | long_context_full | conflict | 5 | 0.933 | 0.008 | 0.0 |
| L | long_context_full | count | 16 | 1.000 | 0.057 | 0.0 |
| L | long_context_full | extremum | 11 | 1.000 | 0.060 | 0.0 |
| L | long_context_full | filter | 5 | 1.000 | 0.043 | 0.0 |
| L | long_context_full | local | 17 | 1.000 | 0.005 | 0.0 |
| L | long_context_full | rank | 6 | 1.000 | 0.101 | 0.0 |
| L | long_context_full | sentiment_shift | 2 | 1.000 | 0.150 | 0.0 |
| L | long_context_full | temporal | 5 | 1.000 | 0.048 | 0.0 |
| L | long_context_full | theme | 6 | 1.000 | 0.020 | 0.0 |
| L | long_context_full | version_diff | 9 | 1.000 | 0.107 | 0.0 |
| M | bm25_topk | conflict | 5 | 0.600 | 0.309 | 0.5 |
| M | bm25_topk | count | 8 | 0.152 | 0.170 | 0.5 |
| M | bm25_topk | extremum | 6 | 0.100 | 0.100 | 0.5 |
| M | bm25_topk | filter | 5 | 0.117 | 0.127 | 0.5 |
| M | bm25_topk | local | 17 | 0.176 | 0.053 | 0.6 |
| M | bm25_topk | rank | 5 | 0.060 | 0.067 | 0.5 |
| M | bm25_topk | temporal | 5 | 0.623 | 0.484 | 0.5 |
| M | bm25_topk | version_diff | 9 | 0.179 | 0.092 | 0.6 |
| M | hybrid_topk | conflict | 5 | 0.600 | 0.334 | 24.4 |
| M | hybrid_topk | count | 8 | 0.177 | 0.194 | 29.7 |
| M | hybrid_topk | extremum | 6 | 0.133 | 0.133 | 30.8 |
| M | hybrid_topk | filter | 5 | 0.137 | 0.150 | 24.2 |
| M | hybrid_topk | local | 17 | 0.353 | 0.097 | 17.5 |
| M | hybrid_topk | rank | 5 | 0.040 | 0.044 | 29.4 |
| M | hybrid_topk | temporal | 5 | 0.623 | 0.497 | 17.7 |
| M | hybrid_topk | version_diff | 9 | 0.178 | 0.094 | 23.9 |
| M | lensrag | conflict | 5 | 0.600 | 0.191 | 181.8 |
| M | lensrag | count | 8 | 0.796 | 0.552 | 190.8 |
| M | lensrag | extremum | 6 | 1.000 | 0.487 | 191.4 |
| M | lensrag | filter | 5 | 0.780 | 0.439 | 188.3 |
| M | lensrag | local | 17 | 0.794 | 0.438 | 18.9 |
| M | lensrag | rank | 5 | 0.903 | 0.524 | 186.0 |
| M | lensrag | temporal | 5 | 0.613 | 0.605 | 18.6 |
| M | lensrag | version_diff | 9 | 0.178 | 0.191 | 206.4 |
| M | lensrag_rerank | conflict | 5 | 0.733 | 0.284 | 2159.3 |
| M | lensrag_rerank | count | 8 | 0.701 | 0.516 | 3965.8 |
| M | lensrag_rerank | extremum | 6 | 0.833 | 0.304 | 4378.5 |
| M | lensrag_rerank | filter | 5 | 0.889 | 0.490 | 4062.7 |
| M | lensrag_rerank | local | 17 | 0.912 | 0.276 | 659.7 |
| M | lensrag_rerank | rank | 5 | 0.794 | 0.483 | 3658.0 |
| M | lensrag_rerank | temporal | 5 | 0.643 | 0.321 | 511.7 |
| M | lensrag_rerank | version_diff | 9 | 0.626 | 0.251 | 3490.2 |
| M | long_context_128k | conflict | 5 | 0.300 | 0.017 | 0.0 |
| M | long_context_128k | count | 8 | 0.250 | 0.128 | 0.0 |
| M | long_context_128k | extremum | 6 | 0.000 | 0.000 | 0.0 |
| M | long_context_128k | filter | 5 | 0.000 | 0.000 | 0.0 |
| M | long_context_128k | local | 17 | 0.000 | 0.000 | 0.0 |
| M | long_context_128k | rank | 5 | 0.000 | 0.000 | 0.0 |
| M | long_context_128k | temporal | 5 | 0.800 | 0.179 | 0.0 |
| M | long_context_128k | version_diff | 9 | 0.056 | 0.002 | 0.0 |
| M | long_context_1m | conflict | 5 | 0.933 | 0.016 | 0.0 |
| M | long_context_1m | count | 8 | 1.000 | 0.127 | 0.0 |
| M | long_context_1m | extremum | 6 | 1.000 | 0.072 | 0.0 |
| M | long_context_1m | filter | 5 | 1.000 | 0.084 | 0.0 |
| M | long_context_1m | local | 17 | 1.000 | 0.009 | 0.0 |
| M | long_context_1m | rank | 5 | 1.000 | 0.084 | 0.0 |
| M | long_context_1m | temporal | 5 | 1.000 | 0.088 | 0.0 |
| M | long_context_1m | version_diff | 9 | 1.000 | 0.188 | 0.0 |
| M | long_context_full | conflict | 5 | 0.933 | 0.016 | 0.0 |
| M | long_context_full | count | 8 | 1.000 | 0.127 | 0.0 |
| M | long_context_full | extremum | 6 | 1.000 | 0.072 | 0.0 |
| M | long_context_full | filter | 5 | 1.000 | 0.084 | 0.0 |
| M | long_context_full | local | 17 | 1.000 | 0.009 | 0.0 |
| M | long_context_full | rank | 5 | 1.000 | 0.084 | 0.0 |
| M | long_context_full | temporal | 5 | 1.000 | 0.088 | 0.0 |
| M | long_context_full | version_diff | 9 | 1.000 | 0.188 | 0.0 |
| S | bm25_topk | count | 4 | 0.675 | 0.725 | 0.2 |
| S | bm25_topk | extremum | 5 | 0.920 | 0.781 | 0.2 |
| S | bm25_topk | filter | 4 | 0.900 | 0.922 | 0.2 |
| S | bm25_topk | local | 17 | 1.000 | 0.263 | 0.2 |
| S | bm25_topk | rank | 4 | 0.850 | 0.876 | 0.2 |
| S | hybrid_topk | count | 4 | 0.700 | 0.742 | 24.9 |
| S | hybrid_topk | extremum | 5 | 0.720 | 0.741 | 22.8 |
| S | hybrid_topk | filter | 4 | 0.875 | 0.909 | 28.6 |
| S | hybrid_topk | local | 17 | 1.000 | 0.265 | 16.4 |
| S | hybrid_topk | rank | 4 | 0.800 | 0.849 | 26.1 |
| S | lensrag | count | 4 | 1.000 | 0.912 | 163.6 |
| S | lensrag | extremum | 5 | 1.000 | 0.757 | 161.3 |
| S | lensrag | filter | 4 | 1.000 | 0.871 | 161.8 |
| S | lensrag | local | 17 | 1.000 | 0.833 | 15.8 |
| S | lensrag | rank | 4 | 0.975 | 0.848 | 160.7 |
| S | lensrag_rerank | count | 4 | 0.975 | 0.827 | 3437.8 |
| S | lensrag_rerank | extremum | 5 | 1.000 | 0.730 | 3598.9 |
| S | lensrag_rerank | filter | 4 | 0.950 | 0.938 | 2428.2 |
| S | lensrag_rerank | local | 17 | 1.000 | 0.393 | 630.8 |
| S | lensrag_rerank | rank | 4 | 0.975 | 0.821 | 3367.4 |
| S | long_context_128k | count | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_128k | extremum | 5 | 1.000 | 0.294 | 0.0 |
| S | long_context_128k | filter | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_128k | local | 17 | 1.000 | 0.047 | 0.0 |
| S | long_context_128k | rank | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_1m | count | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_1m | extremum | 5 | 1.000 | 0.294 | 0.0 |
| S | long_context_1m | filter | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_1m | local | 17 | 1.000 | 0.047 | 0.0 |
| S | long_context_1m | rank | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_full | count | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_full | extremum | 5 | 1.000 | 0.294 | 0.0 |
| S | long_context_full | filter | 4 | 1.000 | 0.357 | 0.0 |
| S | long_context_full | local | 17 | 1.000 | 0.047 | 0.0 |
| S | long_context_full | rank | 4 | 1.000 | 0.357 | 0.0 |

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