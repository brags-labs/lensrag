# LensRAG: corpus-level question answering over enterprise documents

LensRAG answers *global* questions over a document collection: questions that need evidence from many documents at once, such as counting, ranking, filtering, comparing versions, or finding themes and sentiment shifts. Standard top-k RAG handles these poorly because it sees only a few passages. This repository holds:

- the LensRAG method and a tested implementation;
- the evaluation against standard RAG and long-context baselines on the BragsLabs HR corpus (about 2.6M tokens);
- the project report.

The method is described in `docs/LensRAG_methodology.pdf` and in the report, `docs/report/corpus-rag-project.pdf`. A worked example is in [`docs/LENSRAG_ALGORITHM.md`](docs/LENSRAG_ALGORITHM.md).

## Results in brief

All runs use local open-source models (Qwen2.5-14B via Ollama, BGE-M3 embeddings) on one laptop. The full tables, tests and caveats are in the report.

| Measure | LensRAG (fast profile) | Standard RAG, same 14B model |
|---|---|---|
| Global exact match, 72 development questions (tier L) | 0.831 (repeat run 0.845) | 0.239 |
| Local exact match, 17 development questions | 17/17 | 17/17 |
| Global exact match, 32 **held-out** questions | **0.656** | 0.188 |
| Local exact match, 8 held-out questions | 6/8 | 8/8 |
| Median latency per answer (held-out) | 6.0 s | 7.3 s |

- **H1 (standard RAG is worse on global questions): supported.** Standard RAG answers every local question but only 24–28% of global ones. Long-context prompting holds the whole small tier but only 12–19% of the needed evidence on the larger tiers.
- **H2 (LensRAG is better on global questions without losing local accuracy): partly supported.** The global gain holds on held-out questions (19 wins, 4 losses, p = 0.0013), but LensRAG missed 2 of 8 held-out local questions, so the local condition fails. The development scores overstate accuracy, because the method was tuned on those questions.
- **H3 (checks flag most incomplete or conflicting answers): not supported.** The completeness flag catches 27–33% of incomplete retrievals. The index-time conflict scan finds 2 of 10 planted conflicts.

Most of the accuracy gain comes from reading facts once at index time, from tables, labelled record fields and document metadata, and computing answers in code. Better retrieval alone roughly doubled the evidence reaching the model but did not raise exact match.

## Dataset

The corpus archive is `data/bragslabs_corpus.zip`. The CLI extracts it to `data/extracted/` on first use and never modifies the ZIP. It contains:
- 501 Markdown documents in three cumulative size tiers (S, M, L). Tier L has 495 retrievable documents: 1,660,802 words, 2,572,335 tokens (`cl100k_base`). Five documents are marked `retrieval_exclude`.
- 89 development questions with gold answers (`gold/questions.jsonl`): 17 local, 72 global across eleven types.
- A ledger of policy values, planted conflicts and synthetic ticket, grievance, exit and survey records. Gold answers are computed from it, never from the text.

The 40 held-out questions are in `data/heldout/questions_heldout.jsonl` (see [Held-out evaluation](#held-out-evaluation)).

## Setup

Python 3.10+.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

For the local model stack (Ollama, Qwen2.5, BGE-M3, the BGE reranker, spaCy, NLI and sentiment models), follow [`docs/LOCAL_MODELS.md`](docs/LOCAL_MODELS.md). Claude or an OpenAI-compatible endpoint can be used instead: set `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` / `OPENAI_BASE_URL`, in your own shell.

Run the tests (157):

```bash
python -m unittest discover -s tests
```

## Reproducing the experiments

**1. Retrieval level (H1, H2 retrieval, H3 completeness), all tiers:**

```bash
python -m lensrag.cli run --tiers S M L --top-k 10 --semantic dense --embedding-model BAAI/bge-m3 --rerank --judge-model BAAI/bge-reranker-v2-m3 --output results
```

**2. Build the tier-L index once, and label opinion records once:**

```bash
python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L_bge-m3 --embedding-model BAAI/bge-m3
```

```bash
python -m lensrag.cli label-records --index-dir artifacts/index_L_bge-m3 --llm-stack local-qwen-14b
```

**3. Answer level, fast profile.** Start Ollama with four parallel slots first (see `docs/LOCAL_MODELS.md`):

```bash
LENSRAG_FAST=1 python -m lensrag.cli answers --tier L --index-dir artifacts/index_L_bge-m3 --methods lensrag --llm-stack local-qwen-14b --output results/fast_run_v3
```

```bash
LENSRAG_FAST=1 python -m lensrag.cli answers --tier L --index-dir artifacts/index_L_bge-m3 --methods rag_topk --llm-stack local-qwen-14b --output results/baseline_bge_14b
```

**4. H1–H3 tests from a results folder:**

```bash
python -m lensrag.cli hypotheses --output results/fast_run_v3
```

`RUN_EXPERIMENT.sh` runs steps 1–4 with the routed 3B/14B/32B stack, which was the first configuration evaluated.

A resumed `answers` run continues where it stopped. It refuses a folder written by a different experiment (other corpus, questions, models or settings); use a new output folder, or `--no-resume`.

## Held-out evaluation

The fast profile was developed on the 89 development questions, so its development scores are optimistic. To test it fairly:

1. The code was frozen first, at git tag `heldout-frozen`.
2. `scripts/make_heldout_questions.py` then drew 40 new questions from the ledger with a new seed, using entities and slots the development set does not use, and computed their gold answers in code.
3. The set was reviewed and committed before any system was run on it.
4. Each system was run once on it.

```bash
LENSRAG_FAST=1 LENSRAG_GOLD_FILE=data/heldout/questions_heldout.jsonl python -m lensrag.cli answers --tier L --index-dir artifacts/index_L_bge-m3 --methods lensrag --llm-stack local-qwen-14b --output results/heldout_lensrag
```

`LENSRAG_GOLD_FILE` selects the question file. It is the only change to the harness since the freeze.

## Conflict scan (H3)

`lensrag/conflict_scan.py` compares numeric table facts across documents at index time. It flags:
- version changes within a manual chapter;
- pending updates;
- in-force updates that a current source has not applied;
- FAQs, handbooks and summaries that disagree with the policy that applies.

Which document types play which role is set by `source_roles` in the domain config. To score the scan against the ledger's planted conflicts:

```bash
PYTHONPATH=. python scripts/score_conflict_scan.py --judge-stack local-qwen-14b
```

## Results folders

| Folder | What it holds |
|---|---|
| `results/` (top level) | Retrieval metrics for all tiers and methods, and the first answer run (routed 3B/14B/32B stack) |
| `results/rerun_fixes/` | The routed stack after the error-analysis fixes |
| `results/fast_run/`, `fast_run_v2/` | Intermediate fast-profile runs during development |
| `results/fast_run_v3/`, `fast_run_v3_repeat/` | **Final fast profile** on the development questions, run twice |
| `results/baseline_bge_14b/` | Standard RAG with the same 14B model and BGE-M3 retrieval |
| `results/heldout_lensrag/`, `heldout_baseline/` | **Held-out** runs (40 questions, frozen code) |
| `results/review_fixes_dev/` | Development rerun after the post-freeze code-review fixes (same scores) |
| `results/conflict_scan/` | Conflict-scan flags and scores |
| `results/archive/` | Earlier retrieval runs (TF-IDF, MiniLM, BGE-M3 calibration) |

Each answer folder has `answers.csv` (per-question prediction, gold, exact match, set F1, tokens, latency and answer path), `answers_config.json` (models, settings and run fingerprint) and `hypotheses.md`.

## Ground-truth discipline

- Gold evidence document ids are used only to score retrieval, never by the retriever or the pipeline.
- Ledger labels (such as sentiment) are evaluation-only. The system infers them from text.
- A question is scored only at tiers at or above its `min_tier`.
- Held-out questions were written after the code freeze and scored once.

## Repository map

| Path | Contents |
|---|---|
| `lensrag/` | Retrieval benchmark, planner, aggregation and estimation, fact and record extraction, conflict scan |
| `lensrag/full/` | End-to-end runtime: persistent index, pipeline, model routing, LLM clients, local models |
| `lensrag/domains/` | Domain configs (`hr.yaml`, `legal.yaml`); see [`docs/DOMAINS.md`](docs/DOMAINS.md) |
| `scripts/` | Held-out question generator, conflict-scan scorer, cost/recall plot |
| `tests/` | Unit tests, including a small legal corpus |
| `docs/` | Method, runtime, protocol, storage and local-model guides; the report |

Further guides:
- [`docs/FULL_RUNTIME_GUIDE.md`](docs/FULL_RUNTIME_GUIDE.md): how a question is answered;
- [`docs/EXPERIMENT_PROTOCOL.md`](docs/EXPERIMENT_PROTOCOL.md): methods, metrics and statistics;
- [`docs/INDEX_STORAGE.md`](docs/INDEX_STORAGE.md): the persistent index.

## Limitations

- The corpus is synthetic and template-generated, so its phrasing is more regular than real documents. Index-time parsing relies on Markdown tables, bold field labels and YAML front matter.
- The held-out questions share the development templates. Accuracy on new phrasings may be lower.
- Values stated only in prose, conflicts and free-text opinions still need passage retrieval, which is slower and less accurate.
- No GlobalRAG-style baseline was run, and long context was compared only at the retrieval level.
