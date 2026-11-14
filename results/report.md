# LensRAG experiment report

> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.

## Retrieval results by corpus tier

| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| L | bm25_topk | aggregate | 5 | 0.417 | 0.503 | 2.0 |
| L | bm25_topk | comparison | 2 | 0.217 | 0.299 | 2.3 |
| L | bm25_topk | conflict | 5 | 0.333 | 0.114 | 2.2 |
| L | bm25_topk | count | 16 | 0.502 | 0.402 | 1.8 |
| L | bm25_topk | extremum | 11 | 0.391 | 0.315 | 1.9 |
| L | bm25_topk | filter | 5 | 0.117 | 0.127 | 2.0 |
| L | bm25_topk | local | 17 | 0.412 | 0.089 | 2.3 |
| L | bm25_topk | rank | 6 | 0.031 | 0.042 | 2.1 |
| L | bm25_topk | sentiment_shift | 2 | 0.225 | 0.364 | 2.4 |
| L | bm25_topk | temporal | 5 | 0.517 | 0.487 | 2.0 |
| L | bm25_topk | theme | 6 | 0.458 | 0.440 | 1.9 |
| L | bm25_topk | version_diff | 9 | 0.416 | 0.221 | 2.2 |
| L | hybrid_topk | aggregate | 5 | 0.407 | 0.484 | 9.0 |
| L | hybrid_topk | comparison | 2 | 0.167 | 0.254 | 9.0 |
| L | hybrid_topk | conflict | 5 | 0.333 | 0.122 | 9.5 |
| L | hybrid_topk | count | 16 | 0.497 | 0.346 | 9.3 |
| L | hybrid_topk | extremum | 11 | 0.355 | 0.368 | 9.5 |
| L | hybrid_topk | filter | 5 | 0.146 | 0.160 | 9.3 |
| L | hybrid_topk | local | 17 | 0.235 | 0.058 | 10.1 |
| L | hybrid_topk | rank | 6 | 0.014 | 0.026 | 9.4 |
| L | hybrid_topk | sentiment_shift | 2 | 0.225 | 0.367 | 9.7 |
| L | hybrid_topk | temporal | 5 | 0.517 | 0.480 | 9.4 |
| L | hybrid_topk | theme | 6 | 0.458 | 0.456 | 9.0 |
| L | hybrid_topk | version_diff | 9 | 0.178 | 0.092 | 10.0 |
| L | lensrag | aggregate | 5 | 0.448 | 0.585 | 6.6 |
| L | lensrag | comparison | 2 | 0.642 | 0.721 | 104.0 |
| L | lensrag | conflict | 5 | 0.333 | 0.106 | 62.2 |
| L | lensrag | count | 16 | 0.819 | 0.712 | 52.5 |
| L | lensrag | extremum | 11 | 0.845 | 0.583 | 55.0 |
| L | lensrag | filter | 5 | 0.800 | 0.486 | 60.3 |
| L | lensrag | local | 17 | 0.853 | 0.468 | 6.4 |
| L | lensrag | rank | 6 | 0.720 | 0.456 | 59.7 |
| L | lensrag | sentiment_shift | 2 | 0.975 | 0.987 | 104.3 |
| L | lensrag | temporal | 5 | 0.613 | 0.549 | 6.7 |
| L | lensrag | theme | 6 | 0.750 | 0.800 | 6.1 |
| L | lensrag | version_diff | 9 | 0.346 | 0.179 | 61.6 |
| L | lensrag_rerank | aggregate | 5 | 0.700 | 0.760 | 84.0 |
| L | lensrag_rerank | comparison | 2 | 0.721 | 0.806 | 1504.3 |
| L | lensrag_rerank | conflict | 5 | 0.500 | 0.195 | 270.2 |
| L | lensrag_rerank | count | 16 | 0.886 | 0.738 | 542.2 |
| L | lensrag_rerank | extremum | 11 | 0.780 | 0.598 | 546.2 |
| L | lensrag_rerank | filter | 5 | 0.569 | 0.262 | 613.4 |
| L | lensrag_rerank | local | 17 | 0.941 | 0.283 | 75.1 |
| L | lensrag_rerank | rank | 6 | 0.679 | 0.503 | 425.7 |
| L | lensrag_rerank | sentiment_shift | 2 | 0.950 | 0.974 | 1494.7 |
| L | lensrag_rerank | temporal | 5 | 0.647 | 0.295 | 67.0 |
| L | lensrag_rerank | theme | 6 | 0.833 | 0.889 | 82.4 |
| L | lensrag_rerank | version_diff | 9 | 0.746 | 0.319 | 549.4 |
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
| M | bm25_topk | count | 8 | 0.152 | 0.170 | 0.6 |
| M | bm25_topk | extremum | 6 | 0.100 | 0.100 | 0.5 |
| M | bm25_topk | filter | 5 | 0.117 | 0.127 | 0.5 |
| M | bm25_topk | local | 17 | 0.176 | 0.053 | 0.6 |
| M | bm25_topk | rank | 5 | 0.060 | 0.067 | 0.5 |
| M | bm25_topk | temporal | 5 | 0.623 | 0.484 | 0.5 |
| M | bm25_topk | version_diff | 9 | 0.179 | 0.092 | 0.6 |
| M | hybrid_topk | conflict | 5 | 0.700 | 0.350 | 2.0 |
| M | hybrid_topk | count | 8 | 0.142 | 0.160 | 2.0 |
| M | hybrid_topk | extremum | 6 | 0.000 | 0.000 | 2.1 |
| M | hybrid_topk | filter | 5 | 0.077 | 0.087 | 2.3 |
| M | hybrid_topk | local | 17 | 0.147 | 0.038 | 2.2 |
| M | hybrid_topk | rank | 5 | 0.000 | 0.000 | 2.4 |
| M | hybrid_topk | temporal | 5 | 0.623 | 0.451 | 2.1 |
| M | hybrid_topk | version_diff | 9 | 0.178 | 0.096 | 2.1 |
| M | lensrag | conflict | 5 | 0.700 | 0.229 | 27.1 |
| M | lensrag | count | 8 | 0.712 | 0.477 | 23.2 |
| M | lensrag | extremum | 6 | 1.000 | 0.458 | 22.9 |
| M | lensrag | filter | 5 | 0.820 | 0.455 | 23.9 |
| M | lensrag | local | 17 | 0.765 | 0.390 | 2.8 |
| M | lensrag | rank | 5 | 0.863 | 0.496 | 22.5 |
| M | lensrag | temporal | 5 | 0.613 | 0.458 | 3.0 |
| M | lensrag | version_diff | 9 | 0.178 | 0.190 | 23.6 |
| M | lensrag_rerank | conflict | 5 | 0.767 | 0.203 | 262.5 |
| M | lensrag_rerank | count | 8 | 0.767 | 0.517 | 396.4 |
| M | lensrag_rerank | extremum | 6 | 0.667 | 0.303 | 432.9 |
| M | lensrag_rerank | filter | 5 | 0.589 | 0.270 | 396.6 |
| M | lensrag_rerank | local | 17 | 0.912 | 0.281 | 57.1 |
| M | lensrag_rerank | rank | 5 | 0.769 | 0.512 | 319.2 |
| M | lensrag_rerank | temporal | 5 | 0.663 | 0.326 | 48.9 |
| M | lensrag_rerank | version_diff | 9 | 0.460 | 0.212 | 325.5 |
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
| S | hybrid_topk | count | 4 | 0.675 | 0.725 | 0.7 |
| S | hybrid_topk | extremum | 5 | 0.940 | 0.796 | 0.6 |
| S | hybrid_topk | filter | 4 | 0.950 | 0.962 | 0.6 |
| S | hybrid_topk | local | 17 | 1.000 | 0.239 | 0.7 |
| S | hybrid_topk | rank | 4 | 0.875 | 0.889 | 0.6 |
| S | lensrag | count | 4 | 1.000 | 0.880 | 7.0 |
| S | lensrag | extremum | 5 | 1.000 | 0.749 | 7.4 |
| S | lensrag | filter | 4 | 1.000 | 0.861 | 7.8 |
| S | lensrag | local | 17 | 1.000 | 0.812 | 1.0 |
| S | lensrag | rank | 4 | 0.975 | 0.839 | 6.9 |
| S | lensrag_rerank | count | 4 | 0.950 | 0.866 | 289.0 |
| S | lensrag_rerank | extremum | 5 | 0.800 | 0.762 | 297.3 |
| S | lensrag_rerank | filter | 4 | 0.775 | 0.739 | 228.3 |
| S | lensrag_rerank | local | 17 | 1.000 | 0.451 | 48.5 |
| S | lensrag_rerank | rank | 4 | 0.800 | 0.852 | 226.6 |
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