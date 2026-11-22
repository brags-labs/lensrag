"""Report figure: global evidence recall vs context tokens per question, tier L (results/metrics.csv)."""
import sys
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

metrics, out = (sys.argv[1:3] + ["results/metrics.csv", "docs/report/figures/cost_recall_L"])[0:2] if len(sys.argv) > 2 else ("results/metrics.csv", "docs/report/figures/cost_recall_L")
m = pd.read_csv(metrics); m = m[(m.tier == "L") & (m.scope == "global")]
g = m.groupby("method").agg(rec=("evidence_recall", "mean"), tok=("context_tokens", "mean"))
order = ["bm25_topk", "hybrid_topk", "lensrag", "lensrag_rerank", "long_context_128k", "long_context_1m", "long_context_full"]
names = {"bm25_topk": "BM25 top-10", "hybrid_topk": "Hybrid top-10", "lensrag": "LensRAG", "lensrag_rerank": "LensRAG + judge",
         "long_context_128k": "Long context 128k", "long_context_1m": "Long context 1M", "long_context_full": "Full corpus (oracle)"}
cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]  # validated categorical order
mk = ["o", "s", "D", "^", "v", "P", "X"]
off = {"bm25_topk": (9, 7), "hybrid_topk": (9, -8), "lensrag": (-9, 6), "lensrag_rerank": (9, -6), "long_context_128k": (9, 0),
       "long_context_1m": (9, 0), "long_context_full": (4, 10)}
ha = {"lensrag": "right", "long_context_full": "right"}
plt.rcParams.update({"font.family": "sans-serif", "font.size": 9})
fig, ax = plt.subplots(figsize=(6.2, 3.8), dpi=200)
fig.patch.set_facecolor("#ffffff"); ax.set_facecolor("#ffffff")
best, front = -1, []
for k, r in g.loc[order].sort_values("tok").iterrows():
    if r.rec > best:
        front.append(k); best = r.rec
ax.plot(g.loc[front, "tok"], g.loc[front, "rec"], color="#52514e", lw=1, ls="--", zorder=1, label="Pareto frontier")
for i, k in enumerate(order):
    ax.scatter(g.loc[k, "tok"], g.loc[k, "rec"], s=48, color=cols[i], marker=mk[i], edgecolor="#ffffff", linewidth=1.5, zorder=3, label=names[k])
    ax.annotate(f"{names[k]} ({g.loc[k, 'rec']:.2f})", (g.loc[k, "tok"], g.loc[k, "rec"]), xytext=off[k], textcoords="offset points",
                ha=ha.get(k, "left"), va="center", fontsize=7.5, color="#0b0b0b")
ax.set_xscale("log"); ax.set_ylim(0, 1.1); ax.set_xlim(1e3, 8e6)
ax.set_xlabel("Mean context tokens per question (log scale)", color="#52514e")
ax.set_ylabel("Global evidence recall", color="#52514e")
for s in ("top", "right"): ax.spines[s].set_visible(False)
for s in ("left", "bottom"): ax.spines[s].set_color("#c3c2b7")
ax.tick_params(colors="#52514e"); ax.grid(axis="y", color="#e6e5e0", lw=0.6); ax.set_axisbelow(True)
ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
fig.tight_layout(); fig.savefig(out + ".pdf"); fig.savefig(out + ".png")
