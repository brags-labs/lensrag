# LensRAG experiment report

> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.

## Retrieval results by corpus tier

| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| L | bm25_topk | aggregate | 5 | 0.417 | 0.503 | 2.1 |
| L | bm25_topk | comparison | 2 | 0.217 | 0.299 | 2.7 |
| L | bm25_topk | conflict | 5 | 0.333 | 0.114 | 2.1 |
| L | bm25_topk | count | 16 | 0.502 | 0.402 | 1.9 |
| L | bm25_topk | extremum | 11 | 0.391 | 0.315 | 2.2 |
| L | bm25_topk | filter | 5 | 0.117 | 0.127 | 2.0 |
| L | bm25_topk | local | 17 | 0.412 | 0.089 | 2.3 |
| L | bm25_topk | rank | 6 | 0.031 | 0.042 | 2.2 |
| L | bm25_topk | sentiment_shift | 2 | 0.225 | 0.364 | 2.5 |
| L | bm25_topk | temporal | 5 | 0.517 | 0.487 | 2.1 |
| L | bm25_topk | theme | 6 | 0.458 | 0.440 | 1.8 |
| L | bm25_topk | version_diff | 9 | 0.416 | 0.221 | 2.1 |
| L | hybrid_topk | aggregate | 5 | 0.393 | 0.479 | 7.5 |
| L | hybrid_topk | comparison | 2 | 0.246 | 0.350 | 8.3 |
| L | hybrid_topk | conflict | 5 | 0.533 | 0.244 | 7.7 |
| L | hybrid_topk | count | 16 | 0.485 | 0.369 | 7.6 |
| L | hybrid_topk | extremum | 11 | 0.391 | 0.406 | 7.7 |
| L | hybrid_topk | filter | 5 | 0.117 | 0.127 | 7.4 |
| L | hybrid_topk | local | 17 | 0.412 | 0.109 | 7.9 |
| L | hybrid_topk | rank | 6 | 0.064 | 0.077 | 8.0 |
| L | hybrid_topk | sentiment_shift | 2 | 0.237 | 0.380 | 7.7 |
| L | hybrid_topk | temporal | 5 | 0.613 | 0.528 | 7.6 |
| L | hybrid_topk | theme | 6 | 0.567 | 0.637 | 7.5 |
| L | hybrid_topk | version_diff | 9 | 0.399 | 0.179 | 8.1 |
| L | lensrag | aggregate | 5 | 0.492 | 0.639 | 10.7 |
| L | lensrag | comparison | 2 | 0.650 | 0.731 | 166.6 |
| L | lensrag | conflict | 5 | 0.533 | 0.138 | 109.5 |
| L | lensrag | count | 16 | 0.833 | 0.728 | 105.6 |
| L | lensrag | extremum | 11 | 0.846 | 0.601 | 110.5 |
| L | lensrag | filter | 5 | 0.820 | 0.498 | 110.6 |
| L | lensrag | local | 17 | 0.853 | 0.476 | 10.9 |
| L | lensrag | rank | 6 | 0.776 | 0.487 | 110.3 |
| L | lensrag | sentiment_shift | 2 | 0.975 | 0.987 | 163.0 |
| L | lensrag | temporal | 5 | 0.613 | 0.562 | 10.8 |
| L | lensrag | theme | 6 | 0.750 | 0.800 | 11.5 |
| L | lensrag | version_diff | 9 | 0.346 | 0.180 | 117.0 |
| L | lensrag_rerank | aggregate | 5 | 0.825 | 0.867 | 80.2 |
| L | lensrag_rerank | comparison | 2 | 0.750 | 0.833 | 1528.0 |
| L | lensrag_rerank | conflict | 5 | 0.700 | 0.321 | 430.6 |
| L | lensrag_rerank | count | 16 | 0.893 | 0.749 | 544.3 |
| L | lensrag_rerank | extremum | 11 | 0.787 | 0.600 | 507.0 |
| L | lensrag_rerank | filter | 5 | 0.663 | 0.307 | 601.2 |
| L | lensrag_rerank | local | 17 | 1.000 | 0.325 | 69.3 |
| L | lensrag_rerank | rank | 6 | 0.778 | 0.575 | 440.7 |
| L | lensrag_rerank | sentiment_shift | 2 | 0.950 | 0.974 | 1492.6 |
| L | lensrag_rerank | temporal | 5 | 0.647 | 0.299 | 65.3 |
| L | lensrag_rerank | theme | 6 | 0.833 | 0.889 | 82.9 |
| L | lensrag_rerank | version_diff | 9 | 0.743 | 0.307 | 582.5 |
| M | bm25_topk | conflict | 5 | 0.600 | 0.309 | 0.5 |
| M | bm25_topk | count | 8 | 0.152 | 0.170 | 0.5 |
| M | bm25_topk | extremum | 6 | 0.100 | 0.100 | 0.6 |
| M | bm25_topk | filter | 5 | 0.117 | 0.127 | 0.5 |
| M | bm25_topk | local | 17 | 0.176 | 0.053 | 0.6 |
| M | bm25_topk | rank | 5 | 0.060 | 0.067 | 0.5 |
| M | bm25_topk | temporal | 5 | 0.623 | 0.484 | 0.5 |
| M | bm25_topk | version_diff | 9 | 0.179 | 0.092 | 0.6 |
| M | hybrid_topk | conflict | 5 | 0.600 | 0.314 | 6.4 |
| M | hybrid_topk | count | 8 | 0.155 | 0.178 | 6.2 |
| M | hybrid_topk | extremum | 6 | 0.150 | 0.150 | 6.4 |
| M | hybrid_topk | filter | 5 | 0.117 | 0.127 | 6.5 |
| M | hybrid_topk | local | 17 | 0.324 | 0.078 | 6.4 |
| M | hybrid_topk | rank | 5 | 0.060 | 0.060 | 6.2 |
| M | hybrid_topk | temporal | 5 | 0.627 | 0.496 | 6.4 |
| M | hybrid_topk | version_diff | 9 | 0.177 | 0.105 | 6.4 |
| M | lensrag | conflict | 5 | 0.533 | 0.184 | 87.0 |
| M | lensrag | count | 8 | 0.745 | 0.500 | 74.8 |
| M | lensrag | extremum | 6 | 1.000 | 0.498 | 73.4 |
| M | lensrag | filter | 5 | 0.920 | 0.524 | 74.6 |
| M | lensrag | local | 17 | 0.853 | 0.448 | 7.7 |
| M | lensrag | rank | 5 | 0.883 | 0.520 | 72.0 |
| M | lensrag | temporal | 5 | 0.613 | 0.625 | 7.6 |
| M | lensrag | version_diff | 9 | 0.233 | 0.198 | 76.8 |
| M | lensrag_rerank | conflict | 5 | 0.867 | 0.224 | 250.4 |
| M | lensrag_rerank | count | 8 | 0.795 | 0.535 | 430.3 |
| M | lensrag_rerank | extremum | 6 | 0.667 | 0.302 | 470.0 |
| M | lensrag_rerank | filter | 5 | 0.649 | 0.296 | 410.3 |
| M | lensrag_rerank | local | 17 | 0.912 | 0.292 | 52.8 |
| M | lensrag_rerank | rank | 5 | 0.826 | 0.541 | 370.1 |
| M | lensrag_rerank | temporal | 5 | 0.643 | 0.304 | 49.0 |
| M | lensrag_rerank | version_diff | 9 | 0.630 | 0.247 | 342.7 |
| S | bm25_topk | count | 4 | 0.675 | 0.725 | 0.2 |
| S | bm25_topk | extremum | 5 | 0.920 | 0.781 | 0.2 |
| S | bm25_topk | filter | 4 | 0.900 | 0.922 | 0.3 |
| S | bm25_topk | local | 17 | 1.000 | 0.263 | 0.3 |
| S | bm25_topk | rank | 4 | 0.850 | 0.876 | 0.2 |
| S | hybrid_topk | count | 4 | 0.675 | 0.722 | 4.9 |
| S | hybrid_topk | extremum | 5 | 0.920 | 0.786 | 5.1 |
| S | hybrid_topk | filter | 4 | 0.925 | 0.949 | 5.3 |
| S | hybrid_topk | local | 17 | 1.000 | 0.277 | 5.2 |
| S | hybrid_topk | rank | 4 | 0.800 | 0.865 | 5.0 |
| S | lensrag | count | 4 | 1.000 | 0.912 | 50.0 |
| S | lensrag | extremum | 5 | 1.000 | 0.755 | 49.3 |
| S | lensrag | filter | 4 | 1.000 | 0.880 | 50.8 |
| S | lensrag | local | 17 | 1.000 | 0.829 | 5.5 |
| S | lensrag | rank | 4 | 0.975 | 0.830 | 49.8 |
| S | lensrag_rerank | count | 4 | 0.950 | 0.866 | 284.9 |
| S | lensrag_rerank | extremum | 5 | 0.800 | 0.762 | 270.6 |
| S | lensrag_rerank | filter | 4 | 0.775 | 0.746 | 261.0 |
| S | lensrag_rerank | local | 17 | 1.000 | 0.454 | 48.1 |
| S | lensrag_rerank | rank | 4 | 0.800 | 0.852 | 234.4 |

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