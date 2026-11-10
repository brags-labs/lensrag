from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

def build_report(metrics_path, output_path):
    p=Path(metrics_path); out=Path(output_path)
    df=pd.read_csv(p)
    lines=["# LensRAG experiment report","",
           "> This report is generated from the retrieval experiment. It does not claim answer accuracy, faithfulness, or LLM conflict-detection performance.","",
           "## Retrieval results by corpus tier","",
           "| Tier | Method | Query type | N | Evidence recall | Evidence F1 | p50 latency (ms) |",
           "|---|---|---:|---:|---:|---:|---:|"]
    g=df.groupby(["tier","method","query_type"])
    for (tier,method,qt),x in g:
        lines.append(f"| {tier} | {method} | {qt} | {len(x)} | {x.evidence_recall.mean():.3f} | {x.evidence_f1.mean():.3f} | {x.latency_ms.median():.1f} |")
    lines += ["","## Hypothesis status","",
      "- **H1 (global vs local gap):** evaluate the global/local difference using `bm25_topk` and `hybrid_topk` rows. The current retrieval benchmark can test evidence retrieval differences, but not generated-answer accuracy or long-context prompting.",
      "- **H2 (LensRAG answer quality):** not established by this run. The experiment compares evidence recall/F1; exact-match answer accuracy and set-level answer F1 require executing the LLM extraction and answer-generation stages.",
      "- **H3 (verification):** not established by this run. Completeness flags can be computed from evidence coverage, but conflict detection precision/recall requires a labelled conflict benchmark and verifier predictions.",
      "",
      "## Interpretation guardrails","",
      "- Retrieval evidence recall is the fraction of gold evidence document IDs present in retrieved documents.",
      "- Evidence precision is the fraction of retrieved unique documents that are gold evidence documents. It is strict and may penalise useful supporting documents not listed in gold.",
      "- Latency is retrieval wall-clock time on this machine and is not comparable across machines without hardware details.",
      "- The current dense-like component is TF-IDF lexical vector similarity, not a neural embedding model. Call this a BM25 + TF-IDF hybrid baseline, not a production dense retriever.",
      "- Do not use illustrative numbers in the source PDF as experiment outcomes.",
      "",
      "## Next required experiment stage","",
      "Add a fixed LLM extraction adapter, record model/version/prompt, parse evidence records `(entity, value, span, doc_id)`, run deterministic aggregation, and score generated answers against the 89 gold questions. Then evaluate conflict flags against `ledger/conflicts.json` and legitimate version changes as negative controls.",
    ]
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text("\n".join(lines),encoding="utf-8")
    return out
