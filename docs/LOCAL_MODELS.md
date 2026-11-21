# Running LensRAG on open-source, self-hosted models

This follows the "Open-source / self-hosted" column of the report's Table 3.1, sized for a laptop with 36 GB of memory (Apple M4 Max). Nothing here needs an API key or costs money.

## Model per stage

| Stage (Table 3.1) | Table 3.1 choice | Used here | Role in code |
|---|---|---|---|
| Classify query type | Qwen2.5-3B-Instruct | `qwen2.5:3b` via Ollama | `classify` |
| Search + rerank | BM25 + BGE-M3 + bge-reranker-v2-m3 | BM25 + `BAAI/bge-m3` + `BAAI/bge-reranker-v2-m3` (sentence-transformers) | retrieval |
| Select relevant entities | Entity-list lookup + spaCy NER, small LLM fallback | Entity-list lookup from the domain config (`planning.py`); spaCy not used | rules |
| Per-entity adaptive retrieval | Qwen2.5-7B | `qwen2.5:14b` (relevance judge in the coverage loop) | `extract` |
| LLM filter + extract | Qwen2.5-7B/14B, JSON output | `qwen2.5:14b`, Ollama JSON mode | `extract` |
| Compute in code | Python | Python (`aggregation.py`, `estimation.py`) | – |
| Map–reduce summarise | Qwen2.5-72B | `qwen2.5:14b` for map, **`qwen2.5:32b`** for reduce | `map`, `reduce` |
| Verify evidence | Rules + DeBERTa NLI + Qwen2.5-14B judge | Rules + `qwen2.5:14b` judge (no NLI model yet) | `verify` |
| Generate answer | Qwen2.5-72B | **`qwen2.5:32b`** | `answer` |

Qwen2.5-72B needs about 47 GB even 4-bit quantised, so the strong roles use Qwen2.5-32B, the largest that fits. Report this substitution in Chapter 4.

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
4. Run with the local stack:
   ```bash
   export LENSRAG_LLM_STACK=local-qwen
   ```
   ```bash
   python -m lensrag.cli answers --tier L --limit 5 --methods rag_topk lensrag --output results_local_check
   ```
   With `LENSRAG_LLM_STACK` set, `RUN_EXPERIMENT.sh` runs the answer-level evaluation with these models too.

## Retrieval models

```bash
python -m lensrag.cli run --tiers S M L --semantic dense --embedding-model BAAI/bge-m3 --rerank --judge-model BAAI/bge-reranker-v2-m3 --judge-threshold <t> --output results_bge
```

- Each embedding model gets its own ChromaDB collection, so BGE-M3 and MiniLM stores coexist.
- The judge threshold is model-specific: the MS MARCO cross-encoder's −4 doesn't carry over to the BGE reranker. Calibrate it, and report how it was chosen.

## Choosing other models

- **Change one role:** set `LENSRAG_MODEL_<ROLE>`, for example `LENSRAG_MODEL_ANSWER=lensrag-qwen2.5-14b` to avoid loading the 32B model.
- **One model everywhere:** `LENSRAG_LLM_STACK=local-qwen-14b` (faster, about 15 GB).
- **Presets:** defined in `lensrag/full/routing.py` (`STACKS`).
- **Cost accounting:** `answers.csv` records tokens per role (`usage_by_role`).

## Memory and speed on 36 GB
- **Memory:** `qwen2.5:32b` with a 32k context needs about 29 GB, and the 14B about 15 GB. Both don't fit at once, so Ollama swaps them in and out, which adds a few seconds each time the role changes.
- **Speed:** expect a full 89-question run to take hours, mostly in LensRAG's extraction and labelling calls (about 3,200 calls). Use `--limit` for checks.
- **Faster runs:** use `local-qwen-14b`, or lower `sample_size` and `label_passes` in `PipelineConfig`.

## Reproducibility
Record the Ollama model digests (`ollama list` shows the ID column) and the Hugging Face model names in the report. `answers_config.json` records the role-to-model mapping of each run.
