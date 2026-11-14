"""Hypothesis-level analysis of an experiment run (report Section 1.3: H1, H2, H3).

Reads `metrics.csv` (retrieval level, from `run`) and, when present, `answers.csv`
(answer level, from `answers`, which needs an LLM), and writes `hypotheses.md` and
`hypotheses.json` next to them.

Statistics: one-sided Mann–Whitney U (independent groups: local vs global questions),
one-sided Wilcoxon signed-rank (paired: two methods on the same questions), bootstrap 95%
confidence intervals for mean differences (2,000 resamples, seed 42), and Holm correction
within each hypothesis. Every row says which level it measures, so retrieval proxies are
never presented as answer accuracy.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ALPHA = 0.05
SEED = 42
BOOT = 2000
NONINFERIORITY_MARGIN = 0.05
STANDARD_RAG = ["bm25_topk", "hybrid_topk"]
LONG_CONTEXT = ["long_context_128k", "long_context_1m"]
LENSRAG = ["lensrag", "lensrag_rerank"]


# --- statistics ---------------------------------------------------------------------
def _boot_diff_independent(a, b, rng):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) == 0 or len(b) == 0:
        return (np.nan, np.nan)
    d = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(BOOT)]
    return tuple(np.percentile(d, [2.5, 97.5]))


def _boot_diff_paired(diff, rng):
    diff = np.asarray(diff, float)
    if len(diff) == 0:
        return (np.nan, np.nan)
    d = [rng.choice(diff, len(diff)).mean() for _ in range(BOOT)]
    return tuple(np.percentile(d, [2.5, 97.5]))


def _mannwhitney_greater(a, b):
    from scipy.stats import mannwhitneyu
    if len(a) < 2 or len(b) < 2:
        return np.nan
    return float(mannwhitneyu(a, b, alternative="greater").pvalue)


def _wilcoxon_greater(diff):
    from scipy.stats import wilcoxon
    diff = np.asarray(diff, float)
    if len(diff) < 2 or np.allclose(diff, 0):
        return 1.0 if len(diff) else np.nan
    return float(wilcoxon(diff, alternative="greater", zero_method="zsplit").pvalue)


def holm(pvalues):
    """Holm–Bonferroni adjusted p-values (NaNs are left as NaN)."""
    p = np.asarray(pvalues, float)
    out = np.full_like(p, np.nan)
    idx = [i for i in np.argsort(p) if not np.isnan(p[i])]
    m = len(idx); running = 0.0
    for rank, i in enumerate(idx):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


def _fmt(x, nd=3):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def _ci(ci):
    return f"[{_fmt(ci[0])}, {_fmt(ci[1])}]"


# --- H1 -------------------------------------------------------------------------------
def h1(df, rng):
    rows = []
    for tier in sorted(df.tier.unique()):
        for method in STANDARD_RAG:
            d = df[(df.tier == tier) & (df.method == method)]
            for metric in ("evidence_recall", "evidence_f1"):
                loc, glo = d[d.scope == "local"][metric].dropna(), d[d.scope == "global"][metric].dropna()
                if len(loc) == 0 or len(glo) == 0:
                    continue
                rows.append({"tier": tier, "method": method, "metric": metric, "n_local": len(loc), "n_global": len(glo),
                             "local": loc.mean(), "global": glo.mean(), "gap": loc.mean() - glo.mean(),
                             "ci": _boot_diff_independent(loc, glo, rng), "p": _mannwhitney_greater(loc, glo)})
    adj = holm([r["p"] for r in rows])
    for r, a in zip(rows, adj):
        r["p_holm"] = a; r["significant"] = bool(a < ALPHA) and r["gap"] > 0
    lc = []
    for method in LONG_CONTEXT + ["long_context_full"]:
        for tier in sorted(df.tier.unique()):
            d = df[(df.tier == tier) & (df.method == method)]
            if d.empty:
                continue
            lc.append({"method": method, "tier": tier, "global_recall": d[d.scope == "global"].evidence_recall.mean(),
                       "local_recall": d[d.scope == "local"].evidence_recall.mean(),
                       "context_tokens": int(d.context_tokens.iloc[0]), "docs_in_context": int(d.retrieved_docs.iloc[0]),
                       "corpus_docs": int(d.n_docs.iloc[0])})
    return rows, lc


# --- H2 -------------------------------------------------------------------------------
def _pair(df, tier, scope, a, b, metric):
    """Per-question values of methods a and b on the same questions (aligned by qid)."""
    x = df[(df.tier == tier) & (df.scope == scope) & (df.method == a)].set_index("qid")[metric]
    y = df[(df.tier == tier) & (df.scope == scope) & (df.method == b)].set_index("qid")[metric]
    common = x.index.intersection(y.index)
    keep = x[common].notna() & y[common].notna()
    return x[common][keep], y[common][keep]


def _paired(df, tier, scope, a, b, metric):
    x, y = _pair(df, tier, scope, a, b, metric)
    return x - y


def h2(df, rng):
    ours = [m for m in LENSRAG if m in set(df.method)]
    baselines = [m for m in STANDARD_RAG + LONG_CONTEXT if m in set(df.method)]
    rows = []
    for tier in sorted(df.tier.unique()):
        for a in ours:
            for b in baselines:
                for metric in ("evidence_f1", "evidence_recall"):
                    x, y = _pair(df, tier, "global", a, b, metric)
                    if x.empty:
                        continue
                    diff = x - y
                    rows.append({"tier": tier, "ours": a, "baseline": b, "metric": metric, "n": len(diff),
                                 "ours_mean": x.mean(), "baseline_mean": y.mean(),
                                 "diff": diff.mean(), "ci": _boot_diff_paired(diff, rng), "p": _wilcoxon_greater(diff)})
    adj = holm([r["p"] for r in rows])
    for r, a_ in zip(rows, adj):
        r["p_holm"] = a_; r["significant"] = bool(a_ < ALPHA) and r["diff"] > 0
    # Local non-inferiority against the best standard-RAG baseline (by mean local recall).
    nonin = []
    for tier in sorted(df.tier.unique()):
        loc = df[(df.tier == tier) & (df.scope == "local")]
        if loc.empty:
            continue
        best = max((m for m in STANDARD_RAG if m in set(loc.method)), key=lambda m: loc[loc.method == m].evidence_recall.mean())
        for a in ours:
            diff = _paired(df, tier, "local", a, best, "evidence_recall")
            ci = _boot_diff_paired(diff, rng)
            nonin.append({"tier": tier, "ours": a, "baseline": best, "n": len(diff), "diff": diff.mean(), "ci": ci,
                          "non_inferior": bool(ci[0] > -NONINFERIORITY_MARGIN)})
    cost = (df.groupby(["tier", "method", "scope"])
              .agg(context_tokens=("context_tokens", "mean"), latency_p50=("latency_ms", "median"),
                   latency_p95=("latency_ms", lambda x: x.quantile(.95)))
              .reset_index())
    return rows, nonin, cost


# --- H3 -------------------------------------------------------------------------------
def h3(df):
    rows = []
    d = df[(df.method == "lensrag_rerank") & (df.scope == "global")]
    for tier in sorted(d.tier.unique()):
        t = d[d.tier == tier]
        inc, com = t[~t.evidence_complete.astype(bool)], t[t.evidence_complete.astype(bool)]
        flag = lambda x: x.completeness_flag.astype(bool)
        rows.append({"tier": tier, "n": len(t), "incomplete": len(inc), "complete": len(com),
                     "flagged_incomplete": int(flag(inc).sum()), "flagged_complete": int(flag(com).sum()),
                     "detection_rate": flag(inc).mean() if len(inc) else np.nan,
                     "false_alarm_rate": flag(com).mean() if len(com) else np.nan})
    conflict = (df[df.query_type == "conflict"].groupby(["tier", "method"])
                  .agg(n=("qid", "count"), all_evidence_retrieved=("evidence_complete", "mean"),
                       evidence_recall=("evidence_recall", "mean")).reset_index())
    return rows, conflict


# --- answer level (optional) ------------------------------------------------------------
def answers_summary(answers: pd.DataFrame | None):
    if answers is None or answers.empty:
        return None
    ok = answers[answers.error.isna() | (answers.error == "")] if "error" in answers else answers
    if "interval_covered" not in ok:
        ok = ok.assign(interval_covered=np.nan)
    return (ok.groupby(["tier", "method", "scope"])
              .agg(n=("qid", "count"), exact_match=("exact_match", "mean"), set_f1=("set_f1", "mean"),
                   interval_coverage=("interval_covered", "mean"), n_interval=("interval_covered", "count"),
                   tokens=("total_tokens", "mean"), latency_s=("latency_s", "median"))
              .reset_index())


# --- report ------------------------------------------------------------------------------
def analyse(output_dir) -> dict:
    out = Path(output_dir)
    df = pd.read_csv(out / "metrics.csv")
    if "scope" not in df:
        df["scope"] = np.where(df.query_type == "local", "local", "global")
    answers = pd.read_csv(out / "answers.csv") if (out / "answers.csv").exists() else None
    rng = np.random.default_rng(SEED)
    h1_rows, lc_rows = h1(df, rng)
    h2_rows, nonin, cost = h2(df, rng)
    h3_rows, conflict = h3(df)
    ans = answers_summary(answers)
    result = {"h1": h1_rows, "h1_long_context": lc_rows, "h2": h2_rows, "h2_local_noninferiority": nonin,
              "h2_cost": cost.to_dict("records"), "h3_completeness": h3_rows, "h3_conflict_evidence": conflict.to_dict("records"),
              "answer_level": ans.to_dict("records") if ans is not None else None,
              "settings": {"alpha": ALPHA, "bootstrap": BOOT, "seed": SEED, "noninferiority_margin": NONINFERIORITY_MARGIN}}
    (out / "hypotheses.json").write_text(json.dumps(result, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                         encoding="utf-8")
    (out / "hypotheses.md").write_text(render(result, df), encoding="utf-8")
    return result


def render(r, df) -> str:
    L = ["# Hypothesis results", "",
         "Generated by `lensrag/hypotheses.py` from `metrics.csv`" + (" and `answers.csv`" if r["answer_level"] else "") + ".",
         f"One-sided tests at α = {ALPHA} with Holm correction within each hypothesis; 95% bootstrap CIs "
         f"({BOOT} resamples, seed {SEED}). Questions per tier: "
         + ", ".join(f"{t} {df[(df.tier == t)].qid.nunique()} ({(df[(df.tier == t) & (df.scope == 'local')].qid.nunique())} local)"
                     for t in sorted(df.tier.unique())) + ".", "",
         "**Measurement level.** Rows marked *retrieval* score whether the gold evidence documents reach the context "
         "(document-level recall/F1). They are a precondition for a correct answer, not answer accuracy. "
         "Answer-level metrics (exact match, set F1) need an LLM and come from `python -m lensrag.cli answers`.", ""]
    # H1
    L += ["## H1: standard top-k RAG is worse on global than local questions", "",
          "*Retrieval level.* Gap = local − global; p from Mann–Whitney U (local > global).", "",
          "| Tier | Method | Metric | Local | Global | Gap | 95% CI | p (Holm) | Supported |", "|---|---|---|---:|---:|---:|---|---:|---|"]
    for x in r["h1"]:
        L.append(f"| {x['tier']} | {x['method']} | {x['metric'].replace('evidence_', '')} | {_fmt(x['local'])} | {_fmt(x['global'])} | "
                 f"{_fmt(x['gap'])} | {_ci(x['ci'])} | {_fmt(x['p_holm'], 4)} | {'yes' if x['significant'] else 'no'} |")
    L += ["", "**Long-context prompting** (whole documents packed in corpus order; *retrieval level*: is the evidence "
          "inside the window at all?). `long_context_full` is an unlimited-window oracle.", "",
          "| Method | Tier | Corpus docs | Docs in context | Context tokens | Global recall | Local recall |", "|---|---|---:|---:|---:|---:|---:|"]
    for x in r["h1_long_context"]:
        L.append(f"| {x['method']} | {x['tier']} | {x['corpus_docs']} | {x['docs_in_context']} | {x['context_tokens']:,} | "
                 f"{_fmt(x['global_recall'])} | {_fmt(x['local_recall'])} |")
    L += ["", "Not measured: whether a model actually uses evidence placed in a long context (needs an LLM run).", ""]
    # H2
    L += ["## H2: LensRAG beats the baselines on global questions without hurting local ones", "",
          "*Retrieval level.* Paired over the same global questions; p from Wilcoxon signed-rank (ours > baseline).", "",
          "| Tier | Ours | Baseline | Metric | Ours | Baseline | Diff | 95% CI | p (Holm) | Supported |",
          "|---|---|---|---|---:|---:|---:|---|---:|---|"]
    for x in r["h2"]:
        L.append(f"| {x['tier']} | {x['ours']} | {x['baseline']} | {x['metric'].replace('evidence_', '')} | {_fmt(x['ours_mean'])} | "
                 f"{_fmt(x['baseline_mean'])} | {_fmt(x['diff'])} | {_ci(x['ci'])} | {_fmt(x['p_holm'], 4)} | "
                 f"{'yes' if x['significant'] else 'no'} |")
    L += ["", f"**Local questions: non-inferiority** (recall, ours − best standard RAG; non-inferior if the CI lower bound "
          f"> −{NONINFERIORITY_MARGIN}).", "", "| Tier | Ours | Baseline | n | Diff | 95% CI | Non-inferior |", "|---|---|---|---:|---:|---|---|"]
    for x in r["h2_local_noninferiority"]:
        L.append(f"| {x['tier']} | {x['ours']} | {x['baseline']} | {x['n']} | {_fmt(x['diff'])} | {_ci(x['ci'])} | "
                 f"{'yes' if x['non_inferior'] else 'no'} |")
    L += ["", "**Cost** (mean tokens of retrieved context a generator would read; retrieval latency on this machine).", "",
          "| Tier | Method | Scope | Context tokens | p50 ms | p95 ms |", "|---|---|---|---:|---:|---:|"]
    for x in r["h2_cost"]:
        L.append(f"| {x['tier']} | {x['method']} | {x['scope']} | {x['context_tokens']:,.0f} | {_fmt(x['latency_p50'], 1)} | {_fmt(x['latency_p95'], 1)} |")
    L += [""]
    if r["answer_level"]:
        L += ["**Answer level** (from `answers.csv`). *Interval coverage* is, for answers LensRAG estimated from a sample "
              "(Mode B), the share of gold values that fall inside the 95% interval (well-calibrated intervals cover about "
              "95%); *n with interval* is how many answers it is based on. Exact match uses a 1% tolerance, so an "
              "estimate can miss exact match and still be correct within its interval.", "",
              "| Tier | Method | Scope | n | Exact match | Set F1 | Interval coverage | n with interval | Tokens | p50 s |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
        for x in r["answer_level"]:
            L.append(f"| {x['tier']} | {x['method']} | {x['scope']} | {x['n']} | {_fmt(x['exact_match'])} | {_fmt(x['set_f1'])} | "
                     f"{_fmt(x.get('interval_coverage'))} | {int(x.get('n_interval') or 0)} | {x['tokens']:,.0f} | {_fmt(x['latency_s'], 2)} |")
    else:
        L += ["**Answer level: not measured.** H2 is stated in terms of set-level F1 and exact-match accuracy of the "
              "*answers*. No LLM was configured for this run, so `answers.csv` does not exist. Set `ANTHROPIC_API_KEY` "
              "(Claude) or `OPENAI_API_KEY` and rerun `RUN_EXPERIMENT.sh`."]
    L += [""]
    # H3
    L += ["## H3: completeness and conflict checks flag incomplete or conflicting answers", "",
          "**Completeness** (*retrieval level*, `lensrag_rerank`, global questions). An answer is *incomplete* when "
          "some gold evidence document was not retrieved; the check *flags* it when an entity scope found no relevant evidence. "
          "H3 expects a detection rate above 0.5 with a low false-alarm rate.", "",
          "| Tier | Global qs | Incomplete | Flagged of incomplete | Detection rate | Complete | Flagged of complete | False-alarm rate |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in r["h3_completeness"]:
        L.append(f"| {x['tier']} | {x['n']} | {x['incomplete']} | {x['flagged_incomplete']} | {_fmt(x['detection_rate'])} | "
                 f"{x['complete']} | {x['flagged_complete']} | {_fmt(x['false_alarm_rate'])} |")
    L += ["", "**Conflicts: evidence precondition** (conflict questions: share where every document needed to see "
          "the conflict was retrieved). Detecting the conflict itself needs extracted values, i.e. an LLM.", "",
          "| Tier | Method | n | All evidence retrieved | Recall |", "|---|---|---:|---:|---:|"]
    for x in r["h3_conflict_evidence"]:
        L.append(f"| {x['tier']} | {x['method']} | {x['n']} | {_fmt(x['all_evidence_retrieved'])} | {_fmt(x['evidence_recall'])} |")
    L += ["", "Not measured: conflict-flag precision/recall and claim-level faithfulness (both need LLM extraction "
          "and verification over `ledger/conflicts.json`)."]
    return "\n".join(L) + "\n"
