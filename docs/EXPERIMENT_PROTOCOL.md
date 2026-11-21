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
- `lensrag`: context-enriched chunks plus the shared planner (`lensrag/planning.py`). It classifies the question, decomposes it into scopes for countries, offices, versions and periods, and filters each scope by document type and current-versus-superseded status. It then retrieves one page (5 chunks) per scope. No LLM is used.
- `lensrag_rerank` (with `--rerank`): the same scopes, run through the coverage loop (`coverage_retrieve`). A cross-encoder (`ms-marco-MiniLM-L-6-v2`, logit ≥ −4) judges each chunk's relevance, and scopes keep paging until they yield no new relevant chunk. This stands in for the LLM relevance filter, which needs an API key. The threshold was chosen on this benchmark.
- `--semantic dense` swaps TF-IDF for `all-MiniLM-L6-v2` embeddings in every hybrid method. Deterministic aggregation, version resolution, completeness and conflict utilities are in `lensrag/aggregation.py`; they are exercised by the full runtime (`lensrag/full/`), not by this retrieval benchmark.

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

## Hypothesis metrics (H1–H3)
`RUN_EXPERIMENT.sh` captures what each hypothesis needs, and `results/hypotheses.md` (also `hypotheses.json`) reports it. The report is regenerated by `python -m lensrag.cli hypotheses`.

| Hypothesis | Measured now (no LLM) | Needs an LLM (`answers` step) |
|---|---|---|
| H1: top-k RAG worse on global than local; long context degrades beyond the window | Evidence recall/F1 local vs global for `bm25_topk` / `hybrid_topk` (Mann–Whitney U, Holm, bootstrap CI). Long-context baselines that pack whole documents in corpus order into 128k and 1M windows, plus an unlimited oracle: is the evidence inside the window? | Answer accuracy local vs global, and whether a model uses evidence placed in a long context |
| H2: LensRAG better on global questions, no worse on local; at what cost | Paired Wilcoxon of LensRAG vs each baseline on global questions; local non-inferiority (margin 0.05); context tokens and latency per query | Exact match and set-level F1 of answers; LLM tokens per answer (`answers.csv`) |
| H3: completeness and conflict checks flag problems with a low false-alarm rate | Completeness: detection rate and false-alarm rate of the coverage loop's "scope without evidence" flag (`lensrag_rerank`) against whether retrieval really missed gold evidence. Conflicts: whether all documents needed to see each conflict were retrieved | Conflict-flag precision/recall, claim-level faithfulness |

To get the answer-level numbers, set `ANTHROPIC_API_KEY` to use Claude (default model `claude-opus-5-5`, effort `medium`; override with `LENSRAG_LLM_MODEL` / `LENSRAG_LLM_EFFORT`), or `OPENAI_API_KEY` / `OPENAI_BASE_URL` for an OpenAI-compatible endpoint, and rerun `RUN_EXPERIMENT.sh`. The provider is chosen in `lensrag/full/providers.py`; `--llm-provider` on `ask` and `answers` overrides it. It builds the L index if it's missing and runs:

```bash
python -m lensrag.cli answers --tier L --output results
```

`answers.csv` holds the prediction, gold answer, exact match, set F1, tokens and latency for each question and method. The free-text conflict answer that isn't yes/no (Q054) is left unscored for a human or LLM judge.

Note for the answer-level run: questions over record logs (for example average CSAT over 2,208 tickets) are answered by the `lensrag` method as *estimates* from a sample, with 95% intervals. Exact match uses a 1% tolerance, so a well-calibrated estimate can still score as a miss. For these questions `answers.csv` records:
- `computation_mode`;
- the `estimate` with its intervals;
- `interval_covered`: the share of the gold answer's numbers that fall inside LensRAG's 95% intervals.

How each gold format is checked:
- **Single number:** against the main estimate.
- **Before/after pair:** against the two period estimates.
- **Category with count:** the category must be found, and the count must fall within its share interval scaled to the population.
- **Ranked list:** the same check, item by item.

`hypotheses.md` reports the mean coverage next to exact match. Well-calibrated intervals cover about 95% of gold values; much lower coverage means the labels are biased or the intervals too narrow. Raise `sample_size` for tighter intervals at higher LLM cost.

