#!/usr/bin/env bash
# LensRAG experiment: captures the metrics for hypotheses H1-H3 (report Section 1.3).
# Everything goes to one folder, results/ (earlier runs are kept in results/archive/):
#   metrics.csv, summary.csv, run_config.json, report.md   retrieval level, all tiers and methods
#   answers.csv, answers_config.json                       answer level (needs an LLM)
#   hypotheses.md, hypotheses.json                         H1-H3 analysis
# and the LaTeX write-up docs/hypothesis_results.tex.
set -euo pipefail
RESULTS=results

python -m lensrag.cli inspect

if [[ "${LENSRAG_LLM_STACK:-}" == local-* ]]; then
  # Open-source stack (report Table 3.1): BGE-M3 embeddings, BGE reranker as the relevance judge.
  EMBEDDING=BAAI/bge-m3
  RETRIEVAL_OPTS=(--semantic dense --embedding-model "$EMBEDDING" --judge-model BAAI/bge-reranker-v2-m3)
  INDEX_DIR=artifacts/index_L_bge-m3
  # Local models have a 32k context, so the 128k long-context answer baseline can't run;
  # long context is still measured at the retrieval level.
  ANSWER_METHODS=(rag_topk lensrag)
else
  EMBEDDING=sentence-transformers/all-MiniLM-L6-v2
  RETRIEVAL_OPTS=()
  INDEX_DIR=artifacts/index_L
  ANSWER_METHODS=(rag_topk long_context_128k lensrag)
fi

# Retrieval level, tiers S/M/L: standard top-k RAG (bm25, hybrid), long-context packing
# (128k, 1M, full), LensRAG, and LensRAG with the relevance-judge coverage loop.
python -m lensrag.cli run --tiers S M L --top-k 10 --output "$RESULTS" --rerank ${RETRIEVAL_OPTS[@]+"${RETRIEVAL_OPTS[@]}"}

# Answer level (H2: exact match, set F1, interval coverage): needs an LLM. Claude is used when
# ANTHROPIC_API_KEY is set, an OpenAI-compatible endpoint with OPENAI_API_KEY / OPENAI_BASE_URL,
# local models with LENSRAG_LLM_STACK=local-qwen. Progress is saved after every answer; rerunning
# the script resumes where it stopped.
if [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${ANTHROPIC_AUTH_TOKEN:-}" || -n "${LENSRAG_LLM_PROVIDER:-}" \
      || -n "${LENSRAG_LLM_STACK:-}" || -n "${OPENAI_API_KEY:-}" || -n "${OPENAI_BASE_URL:-}" ]]; then
  if [[ ! -f "$INDEX_DIR/metadata.json" ]]; then
    python -m lensrag.cli build-index --tier L --index-dir "$INDEX_DIR" --embedding-model "$EMBEDDING"
  fi
  python -m lensrag.cli answers --tier L --output "$RESULTS" --index-dir "$INDEX_DIR" --methods "${ANSWER_METHODS[@]}" ${LENSRAG_LLM_STACK:+--llm-stack "$LENSRAG_LLM_STACK"}
else
  echo "Skipping answer-level evaluation (H2 exact match / set F1): set ANTHROPIC_API_KEY (Claude), OPENAI_API_KEY, or LENSRAG_LLM_STACK=local-qwen."
fi

# H1-H3 analysis and its LaTeX write-up.
python -m lensrag.cli hypotheses --output "$RESULTS" --tex docs/hypothesis_results.tex

python -m unittest discover -s tests -v
