#!/usr/bin/env bash
# LensRAG experiment: captures the metrics for hypotheses H1-H3 (report Section 1.3).
# Outputs in results/: metrics.csv (per question x method), summary.csv, run_config.json,
# report.md, hypotheses.md / hypotheses.json, and answers.csv when an LLM is configured.
set -euo pipefail

python -m lensrag.cli inspect

# Retrieval level, tiers S/M/L: standard top-k RAG (bm25, hybrid), long-context packing
# (128k, 1M, full), LensRAG, and LensRAG with the relevance-judge coverage loop.
# Also writes the H1-H3 analysis (hypotheses.md).
python -m lensrag.cli run --tiers S M L --top-k 10 --output results --rerank

# Answer level (H2: exact match and set F1 of the answers): needs an LLM. Claude is used when
# ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is set, else an OpenAI-compatible endpoint;
# LENSRAG_LLM_PROVIDER=anthropic also works with an `ant auth login` profile.
if [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${ANTHROPIC_AUTH_TOKEN:-}" || -n "${LENSRAG_LLM_PROVIDER:-}" || -n "${LENSRAG_LLM_STACK:-}" \
      || -n "${OPENAI_API_KEY:-}" || -n "${OPENAI_BASE_URL:-}" ]]; then
  if [[ ! -f artifacts/index_L/metadata.json ]]; then
    python -m lensrag.cli build-index --tier L --index-dir artifacts/index_L
  fi
  python -m lensrag.cli answers --tier L --output results
else
  echo "Skipping answer-level evaluation (H2 exact match / set F1): set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY."
fi

python -m unittest discover -s tests -v
