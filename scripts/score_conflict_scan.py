"""Run the index-time conflict scan and score it against the corpus's planted conflicts.

Matching rule (fixed before scoring): a planted conflict is detected when one flag names at
least two of its documents. Its resolution is right when that flag's applying value has the
ledger's resolution as its number. Version-change flags are reported apart: every changed row
between manual versions is a true difference, so they are not counted as false alarms.

    PYTHONPATH=. python scripts/score_conflict_scan.py [--index-dir ...] [--thresholds 0.85,0.80,0.90]
    PYTHONPATH=. python scripts/score_conflict_scan.py --judge-stack local-qwen-14b   # LLM picks the match
"""
import argparse, json
from collections import Counter
from pathlib import Path

from lensrag.conflict_scan import facts_for_scan, llm_judge, scan
from lensrag.domain import load_domain
from lensrag.facts import build_facts, number
from lensrag.full.index import PersistentHybridIndex

ap = argparse.ArgumentParser()
ap.add_argument("--index-dir", default="artifacts/index_L_bge-m3")
ap.add_argument("--ledger", default="data/bragslabs_corpus/bragslabs_corpus/ledger/conflicts.json")
ap.add_argument("--thresholds", default="0.85,0.80,0.90")
ap.add_argument("--out", default="results/conflict_scan")
ap.add_argument("--judge-stack", default=None, help="LLM stack whose extract model judges candidate matches")
ap.add_argument("--workers", type=int, default=4)
a = ap.parse_args()

dom = load_domain("hr")
idx, _ = PersistentHybridIndex.load(a.index_dir)
facts = facts_for_scan(idx.chunks, build_facts(idx.chunks, skip_types=set(dom.record_types)))
encode = idx.encoder.encode
planted = json.loads(Path(a.ledger).read_text())
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
judge, settings = None, [float(x) for x in a.thresholds.split(",")]
if a.judge_stack:
    import time
    from lensrag.full.providers import create_llm
    from lensrag.full.routing import role as _role
    llm = create_llm(None, None, a.judge_stack)
    judge, settings = llm_judge(_role(llm, "extract").json, workers=a.workers), ["judge"]
summary = {}
for t in settings:
    t0 = time.perf_counter() if judge else 0
    flags = scan([dict(f) for f in facts], encode, dom.source_roles, dom.global_values,
                 dom.active_statuses, dom.pending_statuses, **({"judge": judge} if judge else {"threshold": t}))
    rows = []
    for c in planted:
        hits = [f for f in flags if len(set(f["documents"]) & set(c["docs"])) >= 2]
        want = c["resolution"] if isinstance(c["resolution"], (int, float)) else number(c["resolution"])  # '₹600 until ...': the value now
        right = [f for f in hits if want is not None and number(f["applies"]["value"]) == want]
        rows.append({"id": c["id"], "kind": c["kind"], "detected": bool(hits), "flags": len(hits),
                     "resolution_scored": want is not None, "resolution_right": bool(right),
                     "flag_kinds": sorted({f["kind"] for f in hits})})
    used = {id(f) for c in planted for f in flags if len(set(f["documents"]) & set(c["docs"])) >= 2}
    other = [f for f in flags if f["kind"] != "version_change"]
    s = {"threshold": t, "flags": len(flags), "by_kind": dict(Counter(f["kind"] for f in flags)),
         "detected": sum(r["detected"] for r in rows), "planted": len(rows),
         "resolution_right": sum(r["resolution_right"] for r in rows),
         "resolution_scored": sum(r["resolution_scored"] for r in rows),
         "non_version_flags": len(other), "non_version_matching_planted": sum(id(f) in used for f in other),
         "conflicts": rows}
    if judge:
        s.update(threshold=None, judge_stack=a.judge_stack, seconds=round(time.perf_counter() - t0, 1),
                 usage=getattr(llm, "usage", None))
    summary[str(t)] = s
    (out / (f"flags_{t}.json" if judge else f"flags_t{t:.2f}.json")).write_text(json.dumps(flags, indent=1, ensure_ascii=False))
    print(f"{t}: detected {s['detected']}/{s['planted']}, resolution {s['resolution_right']}/{s['resolution_scored']}, "
          f"flags {s['flags']} {s['by_kind']}, non-version flags matching planted {s['non_version_matching_planted']}/{s['non_version_flags']}")
    for r in rows:
        print("   ", r["id"], r["kind"], "detected" if r["detected"] else "missed", r["flag_kinds"], "res ok" if r["resolution_right"] else "")
(out / ("summary_judge.json" if judge else "summary.json")).write_text(json.dumps(summary, indent=1))
