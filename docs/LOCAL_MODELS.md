# Running LensRAG on open-source, self-hosted models

This follows the "Open-source / self-hosted" column of the report's Table 3.1, sized for a laptop with 36 GB of memory (Apple M4 Max). Nothing here needs an API key or costs money.

## Model per stage

| Stage (Table 3.1) | Table 3.1 choice | Used here | Role in code |
|---|---|---|---|
| Classify query type | Qwen2.5-3B-Instruct | `qwen2.5:3b` via Ollama | `classify` |
| Search + rerank | BM25 + BGE-M3 + bge-reranker-v2-m3 | BM25 + `BAAI/bge-m3`; local questions are reranked by `BAAI/bge-reranker-v2-m3` before the LLM filter | `Reranker` |
| Select relevant entities | Entity-list lookup + spaCy NER, small LLM fallback | Entity-list lookup from the domain config, plus spaCy `en_core_web_sm` NER fuzzy-matched to the inventory (spelling variants, possessives), plus the classify model | rules, `EntityNER`, `classify` |
| Per-entity adaptive retrieval | Qwen2.5-7B | `qwen2.5:14b` (relevance judge in the coverage loop) | `extract` |
| LLM filter + extract | Qwen2.5-7B/14B, JSON output | `qwen2.5:14b`, Ollama JSON mode | `extract` |
| Compute in code | Python | Python (`aggregation.py`, `estimation.py`) | – |
| Map–reduce summarise | Qwen2.5-72B, optional RoBERTa sentiment classifier | `qwen2.5:14b` for map, **`qwen2.5:32b`** for reduce; per-record sentiment from `cardiffnlp/twitter-roberta-base-sentiment-latest` as soft labels (P(negative)) in Mode B estimates | `map`, `reduce`, `SentimentClassifier` |
| Verify evidence | Rules + DeBERTa NLI + Qwen2.5-14B judge | Rules + `cross-encoder/nli-deberta-v3-large` NLI on every answer sentence (entailed / contradicted / unsupported) + `qwen2.5:14b` judge | `verify`, `NLIVerifier` |
| Generate answer | Qwen2.5-72B | **`qwen2.5:32b`** | `answer` |

Qwen2.5-72B needs about 47 GB even 4-bit quantised, so the strong roles use Qwen2.5-32B, the largest that fits. Report this substitution in Chapter 4.

The non-LLM components are in `lensrag/full/local_models.py`. The local stacks switch them all on (`routing.LOCAL_COMPONENTS`); a plain Claude or OpenAI run leaves them off. Turn one off with `LENSRAG_<NAME>=off`, for example `LENSRAG_NLI_MODEL=off`, or swap the model by setting the variable to another model name.

Not implemented from the table: a fine-tuned DeBERTa-v3 or SetFit query classifier. It needs labelled training questions; the rule-based planner plus `qwen2.5:3b` covers classification.

Check that everything is ready:

```bash
python -m lensrag.cli local-check
```

## Setup

1. Install and start Ollama (once):
   ```bash
   brew install ollama
   ```
   ```bash
   ollama serve
   ```
2. Download the models (about 31 GB):
   ```bash
   ollama pull qwen2.5:3b
   ```
   ```bash
   ollama pull qwen2.5:14b
   ```
   ```bash
   ollama pull qwen2.5:32b
   ```
3. Create the 32k-context variants. Ollama's default context is only a few thousand tokens and silently truncates longer prompts; LensRAG's largest prompts are about 27k tokens.
   ```bash
   python -m lensrag.cli ollama-setup
   ```
   This writes the `lensrag-qwen2.5-*` variants: the same weights with `num_ctx 32768`.
4. Download the non-LLM models (about 4.5 GB; they also download on first use):
   ```bash
   python -c "from huggingface_hub import snapshot_download as d; [d(r) for r in ['BAAI/bge-m3','BAAI/bge-reranker-v2-m3','cross-encoder/nli-deberta-v3-large','cardiffnlp/twitter-roberta-base-sentiment-latest']]"
   ```
   ```bash
   pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
   ```
   (`python -m spacy download` fails with the installed spaCy/typer versions; the wheel is the same model.)
5. Run with the local stack:
   ```bash
   export LENSRAG_LLM_STACK=local-qwen
   ```
   ```bash
   python -m lensrag.cli answers --tier L --limit 5 --methods rag_topk lensrag --output results/check
   ```
   With `LENSRAG_LLM_STACK` set, `RUN_EXPERIMENT.sh` runs the answer-level evaluation with these models too.

## Retrieval models

```bash
python -m lensrag.cli run --tiers S M L --semantic dense --embedding-model BAAI/bge-m3 --rerank --judge-model BAAI/bge-reranker-v2-m3 --output results
```

- Each embedding model gets its own ChromaDB collection, so BGE-M3 and MiniLM stores coexist.
- The judge threshold is model-specific: the MS MARCO cross-encoder outputs logits (threshold −4), while the BGE reranker outputs probabilities from 0 to 1. Leave `--judge-threshold` unset and the calibrated value for `--judge-model` is used (`retrieval.JUDGE_THRESHOLDS`).
- **BGE reranker calibration** (BGE-M3 embeddings, all three tiers). The threshold was chosen on odd-numbered gold questions (dev) and reported on even-numbered ones (test), so it isn't tuned on the questions it's scored on. Data: `results/archive/dense_bge_m3/judge_calibration.csv`.

  | Threshold | Dev F1 | Test recall | Test precision | Test F1 |
  |---:|---:|---:|---:|---:|
  | 0.01 | 0.448 | 0.846 | 0.392 | 0.446 |
  | 0.03 | 0.470 | 0.842 | 0.430 | 0.472 |
  | **0.05 (chosen)** | **0.475** | 0.834 | 0.457 | 0.491 |
  | 0.1 | 0.466 | 0.793 | 0.501 | 0.515 |
  | 0.2 | 0.432 | 0.702 | 0.546 | 0.475 |
  | 0.5 | 0.346 | 0.561 | 0.414 | 0.378 |
  | plain `lensrag` (no judge) | 0.545 | 0.791 | 0.530 | 0.568 |

  As with the MS MARCO judge, the judge loop finds more evidence than plain LensRAG (test recall 0.83 vs 0.79) but at lower precision, so plain LensRAG keeps the higher F1. A generic reranker isn't a substitute for the LLM relevance filter, which is what the full pipeline uses.

## End-to-end check (21 Nov 2026)
One tier-S question with a deliberate typo, run through the full `local-qwen` stack: *"Under policy version 3.0, what is the paid annual leave (working days) for employees in Germny?"*

| Stage | What happened |
|---|---|
| spaCy NER | Matched "Germny" to Germany (`DE`) |
| Classify (`qwen2.5:3b`) | Called it `aggregate`, not `local`. The LLM's type overrides the rules, so the question skipped the rerank path and used the coverage loop instead |
| Retrieval, extract (`qwen2.5:14b`) | Found the right chapter (POL-v3.0-CH41) in 2 rounds and extracted 9 records, including 28 days |
| Answer (`qwen2.5:32b`) | "[exact] … 28 working days [POL-v3.0-CH41]": correct (gold: 28) |
| LLM judge (`qwen2.5:14b`) | Supported |
| NLI (DeBERTa) | At first called the correct claim *unsupported*, because the evidence is a Markdown table and the premise was cut before the table. Fixed: premises are now the chunk's context header plus the most relevant lines, with tables written as sentences (`focus_premise`). On the same passage the claim is now entailed (0.997), and a false 25-day claim contradicted (0.998) |

The question took 110 seconds end to end.

Watch the 3B classifier: if it mislabels many local questions in the full run, consider trusting the rule-based type over the LLM's for that stack.

## Choosing other models

- **Change one role:** set `LENSRAG_MODEL_<ROLE>`, for example `LENSRAG_MODEL_ANSWER=lensrag-qwen2.5-14b` to avoid loading the 32B model.
- **One model everywhere:** `LENSRAG_LLM_STACK=local-qwen-14b` (faster, about 15 GB).
- **Presets:** defined in `lensrag/full/routing.py` (`STACKS`).
- **Cost accounting:** `answers.csv` records tokens per role (`usage_by_role`).

## Fast profile (final configuration)
The final results use one 14B model for every role and the fast profile (`docs/FULL_RUNTIME_GUIDE.md`):

1. Start Ollama with four parallel slots and keep only one model loaded:
   ```bash
   OLLAMA_NUM_PARALLEL=4 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
   ```
2. Label the opinion records once (cached in the index directory):
   ```bash
   python -m lensrag.cli label-records --index-dir artifacts/index_L_bge-m3 --llm-stack local-qwen-14b
   ```
3. Run the questions:
   ```bash
   LENSRAG_FAST=1 python -m lensrag.cli answers --tier L --index-dir artifacts/index_L_bge-m3 --methods lensrag --llm-stack local-qwen-14b --output results/fast_run_v3
   ```

The 89 development questions take a median of about 5 s each. The slowest are the few that still need passages read (up to a few minutes).

## Memory and speed on 36 GB
- **Memory:** `qwen2.5:32b` with a 32k context needs about 29 GB, and the 14B about 15 GB. Both don't fit at once, so Ollama swaps them in and out, which adds a few seconds each time the role changes.
- **Speed:** with the routed `local-qwen` stack and the default configuration, a full 89-question run takes hours, mostly in LensRAG's extraction and labelling calls (about 3,200 calls). The fast profile above takes minutes. Use `--limit` for checks.
- **Faster runs:** use `local-qwen-14b`, or lower `sample_size` and `label_passes` in `PipelineConfig`.

## Reproducibility
Record the Ollama model digests (`ollama list` shows the ID column) and the Hugging Face model names in the report. `answers_config.json` records the role-to-model mapping of each run.
