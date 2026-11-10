# Experimental protocol

## Research questions and hypotheses (from the supplied report)
- RQ1: How well do standard RAG and long-context prompting answer global questions compared with local questions?
- RQ2: Does context-enriched, coverage-oriented retrieval with query-time aggregation outperform standard RAG, long-context prompting and a GlobalRAG-style baseline, and at what token/latency cost?
- RQ3: Can verification detect incomplete answers and policy/version conflicts?
- H1: Standard top-k RAG scores significantly lower on global than local questions; long-context prompting narrows the gap only when the whole corpus fits and degrades as the corpus grows.
- H2: Routed LensRAG achieves higher set-level F1 and exact-match accuracy on global questions than baselines without reducing local accuracy.
- H3: Completeness and conflict checks flag a majority of incomplete or conflicting answers with a low false-alarm rate.

## Corpus controls
1. Tier S/M/L inclusion comes from `manifest.jsonl`.
2. Exclude all `retrieval_exclude=true` documents (including country comparison summary chapters and annual reports).
3. Use gold `evidence_docs` only after retrieval for scoring. Do not use them for query expansion, filtering or routing.
4. Only score a question at tiers at or above its `min_tier`.
5. Report actual token counts and tokenizer ID. The README's word count is not a token count.
6. Do not mix the synthetic ledger with document text at inference time. Ledger-derived gold is evaluation-only.

## Current implemented methods
- `bm25_topk`: sparse BM25, fixed top-k chunks.
- `hybrid_topk`: BM25 + word TF-IDF similarity, fixed top-k chunks.
- `lensrag`: context-enriched chunks, query type routing, entity list from corpus metadata, country-scoped subqueries, iterative retrieval until no new document candidates appear. It is a retrieval prototype: LLM passage filtering/extraction, neural embeddings, and LLM verification are extension points, not silently simulated. Deterministic aggregation, completeness and same-version conflict utilities are implemented in `lensrag/aggregation.py` and accept validated query-time evidence records.

## Metrics implemented
- Evidence document recall = retrieved gold evidence document IDs / all gold evidence document IDs.
- Evidence precision = retrieved gold evidence document IDs / all unique retrieved document IDs.
- Evidence F1 = harmonic mean of the above.
- Retrieval latency per query; index build time; chunk and document counts; corpus words/tokens.

## Metrics still required for full RQ/H testing
- Answer exact match and normalized numeric accuracy.
- Set precision/recall/F1 for multi-entity answers.
- Faithfulness: claims supported by extracted evidence spans, with human-validated judge reliability.
- Completeness flag recall and false-alarm rate against deliberately incomplete cases.
- Conflict detection precision/recall against the 12 planted conflicts, with legitimate version updates as negative controls.
- Prompt/input/output token usage, API cost, and successful-task cost.
- Long-context baseline with exact model/context window and explicit truncation policy.
- GlobalRAG-style document filter baseline, ideally using the same LLM and prompt budget.

## Statistical plan
Use paired comparisons on the same question IDs. Report per-tier and local/global strata, mean and 95% bootstrap confidence interval (resample questions, not individual chunks), and paired Wilcoxon signed-rank or permutation tests for method differences. Correct multiple comparisons (Holm). Report effect sizes and raw N. Do not infer significance from aggregate means alone. Use at least 3 repeated runs for nondeterministic LLM systems; retrieval-only methods are deterministic except runtime noise.

## Ablations recommended
A. Remove contextual header.
B. BM25 only vs hybrid.
C. Disable country/entity scoping.
D. Fixed top-k vs adaptive retrieval.
E. Disable completeness verification.
F. Chunk size 130/260/500 words and overlap 0/40/80.
G. Corpus S/M/L.
H. Include/exclude superseded versions and stale FAQ/handbook documents.

## Important limitations
The supplied corpus README states that many records are template-generated and versions 1.0/2.0 are synthetic derivatives, not historical snapshots. This may inflate lexical regularity and limits external validity. Sentiment labels exist in the ledger but are not explicitly present in the text; do not train/test sentiment classification using ledger labels as inference inputs.
