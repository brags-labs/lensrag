# Full LensRAG runtime guide

## What was added

The original benchmark runner is preserved. The new `lensrag.full` runtime adds:

1. A persistent L-tier index combining BM25 with normalized sentence-transformer embeddings.
2. A corpus-derived entity inventory: countries (from metadata), offices (from office handbooks), and the policy versions and periods present in the corpus.
3. Query planning (`lensrag/planning.py`): an LLM classifies the question into the 12 gold types (local, count, extremum, rank, filter, aggregate, comparison, temporal, version_diff, theme, sentiment_shift, conflict) and extracts K, direction, threshold and comparator. A rule-based planner fills in or replaces anything missing or invalid.
4. Entity decomposition: one bounded scope per country or office. When the question contrasts versions or periods, scopes are also split by version and period. Each scope filters by country, version, period, document type, and current versus superseded status.
5. Coverage retrieval (`coverage_retrieve`): each round fetches the next page of chunks for every active scope. One LLM call per scope page judges relevance and extracts evidence records. A scope stops when its new page holds no relevant evidence, and the loop stops when no scope adds any. A chunk shared by several scopes is judged for each of them, and duplicate records are removed before aggregation. `adaptive_round_limit` is only a safety cap.
6. Evidence records (entity, attribute, value, verbatim evidence span) carry the source document's version, status, effective date, period and scope.
7. Deterministic operations in Python: count of entities, max/min with ties, rank/top-K (K taken from the question, ties kept), numeric or yes/no filters, mean, share, and grouping by version or period. Before per-entity operations, `resolve_versions` keeps one value per entity: current/in-force first, then the latest effective date.
8. Theme/sentiment map–reduce: map is one LLM call per entity scope; the reduce step counts normalised labels in code, by period or by before/after scope.
9. Verification: completeness per scope, conflict flags (same-version conflicts and cross-version differences), version-resolution flags (superseded, pending, unresolved conflicts) and LLM claim support. A final answer with citations discloses all of these.

## Index-time structures: answering without passage retrieval

Steps 4–8 above read passages at question time. Most questions in this corpus ask about values the documents already state in a regular form, so the pipeline first tries three structures built once at load time. Each is computed in code and checked against the question before it is used:

| Path | Built from | Answers | Code |
|---|---|---|---|
| Fact table | Every row of every Markdown table: entity, attribute, value, document, version, status, effective date | Lookups, extrema, ranks, numeric and yes/no filters (including negated criteria such as "a gym but no crèche"), counts, version differences | `lensrag/facts.py`, `_fact_answer` in `full/pipeline.py` |
| Record fields | Bold-labelled fields of tickets, grievances, exit notes and survey responses, plus a sentiment label for each opinion record (`label-records`, cached as `record_labels.json`) | Counts, shares, means, most common categories and group rankings over all records in scope, exactly | `lensrag/records.py`, `lensrag/record_labels.py`, `_field_estimate` |
| Document catalogue | One metadata row per document (type, title, version, country, office, dates, status) | Which documents exist: counts, lists and version additions | `lensrag/doc_catalogue.py`, `_catalogue_answer` |

The LLM only maps the question to a small query over the structure. Code then validates that query:
- each filter must be stated in the question;
- a stated numeric condition the model misreads sends the question to another path, instead of running a broader query;
- each criterion keeps the polarity the question asks for.

When no structure covers the question, it falls back to passage retrieval (steps 4–8).

The index-time conflict scan (`lensrag/conflict_scan.py`, scored by `scripts/score_conflict_scan.py`) uses the same table facts to flag values that disagree across documents. It is evaluated separately and does not change answers.

## Fast profile

`LENSRAG_FAST=1` (or `fast_config(cfg)`) is the low-latency configuration used for the final results. It runs with one resident model (`LENSRAG_LLM_STACK=local-qwen-14b`) and:
- plans with the rule-based planner (no classify call);
- writes computed answers from a template in code (no write or finalize call); verification findings are appended to the answer as "Verification notes";
- verifies with NLI and number provenance only (no LLM verify call);
- uses smaller samples and fewer reduce runs for estimated and generated answers;
- judges the scopes of a retrieval round in parallel (`LENSRAG_LLM_WORKERS`, default 4; start Ollama with `OLLAMA_NUM_PARALLEL=4`).

On the 89 development questions it answers at a median of about 5 s per question, against several minutes for the first configuration.

## Installation and first run

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Build the full corpus index once:

```bash
python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L
```

The default encoder is `sentence-transformers/all-MiniLM-L6-v2`; the experiments use `--embedding-model BAAI/bge-m3` with `--index-dir artifacts/index_L_bge-m3`. The first run downloads the model. The build command does not need an LLM.

To ask a question, either set `LENSRAG_LLM_STACK=local-qwen-14b` for local models, or configure an API key in the environment:

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

- The end-to-end pipeline needs an LLM: local models through Ollama (no cost; see `LOCAL_MODELS.md`), Claude, or an OpenAI-compatible endpoint. Answer-level results for the local stacks are in `results/` (see the README's results table).
- The dense index must be built on the target machine; model weights are downloaded separately and are not bundled.
- The current document parser preserves heading paths and intact Markdown table blocks heuristically; it is not a general-purpose DOCX/PDF parser or a fully typed document AST.
- Adaptive retrieval has a configurable maximum number of rounds as a safety cap. `adaptive_retrieval.converged` reports whether the loop stopped because no scope produced new relevant evidence, and `scopes_without_evidence` lists entity scopes that found nothing.
- The rule-based planner was tuned on the 89 development questions (it classifies all of them correctly), so it is not evidence of generalisation. The fast profile plans with it; the default configuration uses the LLM classifier, with the rules filling or replacing invalid fields. The held-out questions (README) test the frozen planner on new questions.
- The current verification stage uses an LLM judge plus deterministic completeness/conflict rules; it is not a formal proof of factual entailment. Evaluate false positives/negatives on a labelled verification set before making H3 claims.
- Theme/sentiment map–reduce summarises retrieved passages, not every raw corpus item unless retrieval coverage is exhaustive. Its coverage limitation must be reported.
- Global completeness is only as reliable as the entity inventory and the LLM extraction of entity/value records.

## LLM provider
The runtime works with Claude or any OpenAI-compatible endpoint (`lensrag/full/providers.py`).

- **Claude** (`lensrag/full/claude_llm.py`):
  - Turned on by `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or `--llm-provider anthropic` with an `ant auth login` profile.
  - Defaults to `claude-opus-5-5` at effort `medium`; override with `LENSRAG_LLM_MODEL` and `LENSRAG_LLM_EFFORT`.
  - Server-side refusal fallback is on: a declined request is re-run on a fallback model in the same call. Turn it off with `LENSRAG_CLAUDE_FALLBACKS=off`.
  - The system prompt is cached, so a long shared context is billed at the cache-read rate after the first call.
  - JSON replies are parsed from text, with one retry if a reply isn't valid JSON.
- **OpenAI-compatible** (`lensrag/full/llm.py`): turned on by `OPENAI_API_KEY` or `OPENAI_BASE_URL`; the default model is `gpt-4o-mini`.

Both clients report token usage, which `answers.csv` records per question, including cache reads and writes for Claude.

## Step 7 computation modes
Each question's plan has a `mode`. The answer labels each statement [exact], [estimated] or [generated], and the result includes `computation_mode`, `deterministic_result`, `estimate` and `insights`.

| Mode | When | What happens |
|---|---|---|
| exact | numbers, rankings, filters and categories over evidence that can be read in full | Records are extracted from the retrieved passages and computed in code (`aggregation.py`), including frequency, most common category, cross-tab and all-of/any-of criteria |
| estimated | shares, means, counts or most-common-category questions over record logs | All records in scope form the population. Up to `max_exact_records` are labelled in full; above that, a stratified sample of `sample_size` is labelled `label_passes` times, and code computes estimates with 95% intervals (`estimation.py`) |
| generated | themes, insights, explanations, sentiment change | Map per entity, counts or estimates in code, then the reduce step runs `reduce_runs` times; insights kept by more than `support_threshold` of runs, with citations and support (`synthesis.py`) |

The settings are on `PipelineConfig`: `max_exact_records` (150), `sample_size` (150), `label_passes` (3), `label_batch` (10), `reduce_runs` (5), `support_threshold` (0.5) and `seed` (42).

Cost is roughly `sample_size × label_passes / label_batch` labelling calls for an estimated question (45 by default), plus `reduce_runs` calls for a generated one.

Step 8 adds `verification.uncertainty`, which checks that estimates have intervals and that insights have support and citations. `verification.number_provenance` lists any number in the final answer that no code result, record or retrieved passage contains.

