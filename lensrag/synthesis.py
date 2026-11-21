"""Mode C (generated) synthesis: grounded insights checked for agreement across runs.

The reduce step of map-reduce runs `k` times over the same notes and computed statistics.
Each run returns insights with a short canonical `key`; insights are matched across runs by
that key, and an insight is kept only when a majority of runs produce it. Each kept insight
carries:

- `support`: the fraction of runs that produced it (e.g. 0.8 = 4 of 5);
- `citations`: document ids that exist in the retrieved evidence (others are dropped);
- `status`: "supported" with citations, otherwise "hypothesis";
- `unverified_numbers`: numbers in its text that neither code computed nor the evidence contains.

The numbers inside insights must come from the supplied statistics; the check makes that visible.
"""
from __future__ import annotations
import json
from collections import defaultdict
from .aggregation import normalize_label, numbers_in, number_provenance

REDUCE_PROMPT = (
    "You write insights that answer the question from the supplied notes and computed statistics. "
    "Return JSON {\"insights\": [{\"key\": short canonical label of the insight (3-6 words), \"text\": one or two sentences, "
    "\"citations\": [doc_id, ...]}]}. Use only numbers that appear in the computed statistics or notes; never compute new "
    "ones. Cite the doc_ids whose evidence supports each insight. Give at most {max_insights} insights, most important first.")


def _call(llm, system, user, run):
    # Each run must be an independent sample, so ask for normal sampling where the client allows it.
    try:
        return llm.json(system, user, temperature=1.0)
    except TypeError:  # clients without a temperature argument (e.g. test stubs)
        return llm.json(system, user)


def consistent_insights(llm, question, notes, stats, evidence_doc_ids, k=5, threshold=0.5, max_insights=5):
    """Run the reduce step k times and keep the insights most runs agree on."""
    system = REDUCE_PROMPT.replace("{max_insights}", str(max_insights))
    user = json.dumps({"question": question, "computed_statistics": stats, "notes": notes},
                      ensure_ascii=False, default=str)
    seen = defaultdict(list)  # key -> [(run, insight)]
    for run in range(k):
        out = _call(llm, system, user, run)
        keys_this_run = set()
        for ins in (out or {}).get("insights", []) or []:
            if not isinstance(ins, dict) or not ins.get("text"):
                continue
            key = normalize_label(ins.get("key") or ins["text"][:60])
            if key and key not in keys_this_run:
                keys_this_run.add(key); seen[key].append((run, ins))
    allowed_numbers = numbers_in(stats) + numbers_in(notes)
    valid_ids = set(evidence_doc_ids)
    kept = []
    for key, items in seen.items():
        support = len(items) / k
        if support <= threshold:
            continue
        first = items[0][1]
        citations = sorted({c for _, ins in items for c in (ins.get("citations") or []) if c in valid_ids})
        kept.append({"key": key, "text": first["text"], "support": support, "runs": len(items), "k": k,
                     "citations": citations, "status": "supported" if citations else "hypothesis",
                     "unverified_numbers": number_provenance(first["text"], allowed_numbers)})
    kept.sort(key=lambda x: (-x["support"], x["key"]))
    dropped = sorted(({"key": key, "support": len(items) / k} for key, items in seen.items() if len(items) / k <= threshold),
                     key=lambda x: -x["support"])
    return {"insights": kept[:max_insights], "dropped": dropped, "k": k, "threshold": threshold}
