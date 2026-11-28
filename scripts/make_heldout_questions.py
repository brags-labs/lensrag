"""Generate the held-out H2 question set: new slots, gold computed from the corpus ledger.

The 89 development questions (gold/questions.jsonl) were used while building LensRAG's fast
profile. This set tests the frozen code (git tag `heldout-frozen`) on questions it has not seen:

* the same question types in roughly the development mix (40 questions, no conflict type: the
  planted conflicts are all used by the development set and by the H3 scan);
* slots the development set does not use (other attributes, countries, months, quarters,
  categories, thresholds), drawn with a fixed seed from pools defined below;
* several phrasings per type, chosen with the same seed;
* gold answers computed by code from the corpus's own ledger and data modules, never typed in.

Only fields the corpus documents show are asked about (ticket sentiment, for example, exists only
in the ledger and is not used).

    python scripts/make_heldout_questions.py [--corpus data/extracted/bragslabs_corpus] [--seed 20261128]
"""
import argparse, json, os, random, sys
from collections import Counter
from datetime import date

ap = argparse.ArgumentParser()
ap.add_argument("--corpus", default="data/extracted/bragslabs_corpus")
ap.add_argument("--seed", type=int, default=20261128)
ap.add_argument("--out", default="data/heldout/questions_heldout.jsonl")
a = ap.parse_args()

sys.path.insert(0, os.path.join(a.corpus, "generator"))
from common import POLICY, ATTR_LABEL, COUNTRIES, CNAME, OFFICES, VERSION_COUNTRIES  # noqa: E402
from events import CIRCULARS  # noqa: E402
from records import TCATS, GCATS, EREASONS, ST_LABEL  # noqa: E402

R = random.Random(a.seed)
L = lambda n: json.load(open(os.path.join(a.corpus, "ledger", n), encoding="utf-8"))
T, G, X, S = L("tickets.json"), L("grievances.json"), L("exit_notes.json"), L("survey_comments.json")
dev = [json.loads(x) for x in open(os.path.join(a.corpus, "gold", "questions.jsonl"), encoding="utf-8") if x.strip()]
DEV_TEXT = {q["question"].lower() for q in dev}
ADD_DOC = {c: f"POL-v3.0-CH{38 + i}" for i, c in enumerate(["US", "IN", "UK", "DE", "NL", "IE", "SG", "AE", "CA", "AU"])}
ALL_ADD = [ADD_DOC[c] for c in COUNTRIES]
Q = []


def add(qtype, question, answer, evidence, tier, notes=None, answer_format="value"):
    assert question.lower() not in DEV_TEXT, question
    Q.append({"qid": f"H{len(Q) + 1:03d}", "type": qtype, "question": question, "answer": answer,
              "answer_format": answer_format, "evidence_docs": evidence, "min_tier": tier, "notes": notes})


def pick(pool, k):
    return R.sample(pool, k)


V3 = lambda attr: {c: POLICY[attr][c]["v3.0"] for c in COUNTRIES}
NL_SICK = "Netherlands sick pay is salary continuation for up to 104 weeks, not a day count; it is excluded."
SHORT = {"annual_leave_days": ("paid annual leave", "working days"), "paid_sick_days": ("paid sick leave at full pay", "working days"),
         "birth_parent_leave_weeks_full_pay": ("birth-parent leave at full pay", "weeks"),
         "partner_leave_weeks_full_pay": ("partner leave at full pay", "weeks"),
         "notice_period_senior_days": ("notice period for L4 and above employees", "calendar days"),
         "standard_weekly_hours": ("standard working week", "hours"),
         "employer_retirement_contribution_pct": ("employer retirement contribution", "% of pay"),
         "public_holidays": ("number of paid public holidays", "days"),
         "life_cover_multiple": ("life cover", "times annual base salary")}


def values(attr):
    v = V3(attr)
    return {c: x for c, x in v.items() if not (attr == "paid_sick_days" and c == "NL")}


def note(attr):
    return NL_SICK if attr == "paid_sick_days" else None


def month(y, m):
    return date(y, m, 1).strftime("%B %Y")


# ---------------- local lookups (8): country–attribute pairs and office facts the dev set does not ask
dev_local = {("DE", "annual_leave_days"), ("IN", "annual_leave_days"), ("UK", "paid_sick_days"), ("US", "partner_leave_weeks_full_pay"),
             ("IE", "standard_weekly_hours"), ("AU", "partner_leave_weeks_full_pay"), ("SG", "notice_period_senior_days"),
             ("CA", "partner_leave_weeks_full_pay"), ("NL", "employer_retirement_contribution_pct"), ("AE", "paid_sick_days"),
             ("UK", "life_cover_multiple"), ("US", "public_holidays")}
pairs = [(c, attr) for attr in POLICY for c in COUNTRIES if (c, attr) not in dev_local and not (c == "NL" and attr == "paid_sick_days")]
LOCAL_T = ["Under policy version 3.0, what is the {label} for employees in {country}?",
           "What {short} do employees in {country} get under the current policy (version 3.0)?",
           "In {country}, what is the {label} according to policy version 3.0?"]
for c, attr in pick(pairs, 6):
    t = R.choice(LOCAL_T)
    add("local", t.format(label=ATTR_LABEL[attr], short=SHORT[attr][0], country=CNAME[c]), POLICY[attr][c]["v3.0"], [ADD_DOC[c]], "S")
for o, (field, i) in zip(pick(OFFICES, 2), pick([("floors", 5), ("parking spaces", 6)], 2)):
    add("local", f"How many {field} does the BragsLabs {o[1]} office have?", o[i], [f"HB-{o[0]}"], "M")

# ---------------- counts (7)
cmp_ops = {"more than": lambda x, t: x > t, "at least": lambda x, t: x >= t, "fewer than": lambda x, t: x < t}
count_pool = []
for attr in ["birth_parent_leave_weeks_full_pay", "partner_leave_weeks_full_pay", "employer_retirement_contribution_pct",
             "public_holidays", "notice_period_senior_days", "life_cover_multiple", "paid_sick_days"]:
    vs = sorted(set(values(attr).values()))
    for op in cmp_ops:
        for t in vs[1:-1]:
            count_pool.append((attr, op, t))
for attr, op, t in pick(count_pool, 2):
    n = sum(cmp_ops[op](x, t) for x in values(attr).values())
    unit = SHORT[attr][1]
    uae = "The United Arab Emirates has an end-of-service gratuity instead of a pension (0%)." if attr == "employer_retirement_contribution_pct" else None
    add("count", f"In how many countries is the {SHORT[attr][0]} {op} {t:g} {unit} under policy version 3.0?", n, ALL_ADD, "S", note(attr) or uae)
off_count = [("How many BragsLabs offices have a crèche?", sum(o[8] for o in OFFICES)),
             ("How many BragsLabs offices opened before 2018?", sum(o[3] < 2018 for o in OFFICES)),
             ("How many BragsLabs offices have more than 3 floors?", sum(o[5] > 3 for o in OFFICES))]
qtext, n = R.choice(off_count)
add("count", qtext, n, ["HB-*"], "M")
dev_tm = {("IN", 2026, 4), ("UK", 2026, 4), ("US", 2026, 5)}
months = sorted({(t["year"], t["month"]) for t in T})
c, (y, m) = R.choice([(c, ym) for c in COUNTRIES for ym in months if (c, *ym) not in dev_tm])
add("count", f"How many HR helpdesk tickets were opened in {CNAME[c]} in {month(y, m)}?",
    sum(t["country"] == c and (t["year"], t["month"]) == (y, m) for t in T), [f"TKT-{c}-{y}{m:02d}"], "L")
cat = R.choice([k for k in TCATS if k not in ("shift_allowance", "hybrid_attendance", "reimbursement")])
c = R.choice(COUNTRIES)
add("count", f"How many {TCATS[cat][0].lower()} tickets were raised in {CNAME[c]} between November 2025 and October 2026?",
    sum(t["country"] == c and t["category"] == cat for t in T), [f"TKT-{c}-*"], "L")
quarters = sorted({(g["year"], g["quarter"]) for g in G})
gc = R.choice([k for k in GCATS if k not in ("transport_safety", "posh_referral", "hybrid_policy")])
c, (y, q) = R.choice([(c, yq) for c in COUNTRIES for yq in quarters])
add("count", f"How many grievances about {GCATS[gc].lower()} were filed in {CNAME[c]} in Q{q} {y}?",
    sum(g["country"] == c and g["category"] == gc and (g["year"], g["quarter"]) == (y, q) for g in G), [f"GRV-{c}-{y}Q{q}"], "L")
xq = R.choice([yq for yq in sorted({(x["year"], x["quarter"]) for x in X}) if yq != (2026, 3)])
add("count", f"How many exit interviews were recorded across all countries in Q{xq[1]} {xq[0]}?",
    sum((x["year"], x["quarter"]) == xq for x in X), [f"EXIT-*-{xq[0]}Q{xq[1]}"], "L")

# ---------------- extrema (5)
def extremum(attr, hi):
    vs = values(attr)
    best = max(vs.values()) if hi else min(vs.values())
    who = sorted(CNAME[c] for c, v in vs.items() if v == best)
    return ([who[0], best], "tuple") if len(who) == 1 else (who, "set")

ext_pool = [(attr, hi) for attr in ["paid_sick_days", "birth_parent_leave_weeks_full_pay", "standard_weekly_hours",
                                     "employer_retirement_contribution_pct", "life_cover_multiple", "public_holidays"] for hi in (True, False)
            if (attr, hi) != ("public_holidays", True)]
for attr, hi in pick(ext_pool, 2):
    ans, fmt = extremum(attr, hi)
    word = "highest" if hi else "lowest"
    tail = ", and what is it?" if fmt == "tuple" else "?"
    add("extremum", f"Which country has the {word} {SHORT[attr][0]} under policy version 3.0{tail}", ans, ALL_ADD, "S",
        (note(attr) or "") + (" Ties: all tied countries." if fmt == "set" else "") or None, fmt)
field, i, word = R.choice([("floors", 5, "the most floors"), ("parking spaces", 6, "the most parking spaces"), ("headcount", 4, "the smallest headcount")])
o = (min if word == "the smallest headcount" else max)(OFFICES, key=lambda o: o[i])
add("extremum", f"Which BragsLabs office has {word}, and how many?", [o[1], o[i]], ["HB-*"], "M", answer_format="tuple")
c, (y, m) = R.choice([(c, ym) for c in COUNTRIES for ym in months if (c, *ym) not in dev_tm])
ts = Counter(t["category"] for t in T if t["country"] == c and (t["year"], t["month"]) == (y, m)).most_common()
while ts and len(ts) > 1 and ts[0][1] == ts[1][1]:          # redraw until the top category is unique
    c, (y, m) = R.choice([(c, ym) for c in COUNTRIES for ym in months if (c, *ym) not in dev_tm])
    ts = Counter(t["category"] for t in T if t["country"] == c and (t["year"], t["month"]) == (y, m)).most_common()
add("extremum", f"Which helpdesk ticket category was most common in {CNAME[c]} in {month(y, m)}, and how many tickets did it have?",
    [TCATS[ts[0][0]][0], ts[0][1]], [f"TKT-{c}-{y}{m:02d}"], "L", answer_format="tuple")
en = {c: [s["enps_score"] for s in S if s["country"] == c] for c in COUNTRIES}
enps = lambda xs: round(100 * (sum(v >= 9 for v in xs) - sum(v <= 6 for v in xs)) / len(xs), 1)
worst = min(en, key=lambda c: enps(en[c]))
add("extremum", "Which country had the lowest eNPS in the 2026 Pulse survey (promoters 9–10 minus detractors 0–6), and what was it?",
    [CNAME[worst], enps(en[worst])], ["PULSE26-*"], "L", answer_format="tuple")

# ---------------- ranks (3)
def top3(scores):
    """The top three, only when their order is unambiguous (no tie among them or with the fourth)."""
    s = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    vals = [v for _, v in s[:4]]
    return s[:3] if len(s) >= 3 and len(set(vals)) == len(vals) else None

rank_pool = [attr for attr in ["birth_parent_leave_weeks_full_pay", "partner_leave_weeks_full_pay", "public_holidays", "annual_leave_days", "paid_sick_days"]
             if top3(values(attr))]
attr = R.choice(rank_pool)
add("rank", f"Which three countries have the most {SHORT[attr][0]} under policy version 3.0? Rank them.",
    [[CNAME[c], v] for c, v in top3(values(attr))], ALL_ADD, "S", note(attr), "ranked_list")
add("rank", "Rank the three largest BragsLabs offices by headcount.", [[o[1], o[4]] for o in sorted(OFFICES, key=lambda o: -o[4])[:3]], ["HB-*"], "M",
    answer_format="ranked_list")
cats = [k for k in TCATS if top3(Counter(t["country"] for t in T if t["category"] == k))]
cat = R.choice(cats)
add("rank", f"Which three countries raised the most {TCATS[cat][0].lower()} tickets between November 2025 and October 2026?",
    [[CNAME[c], n] for c, n in top3(Counter(t["country"] for t in T if t["category"] == cat))], ["TKT-*"], "L", answer_format="ranked_list")

# ---------------- filters (3)
fil_pool = [(attr, op, t) for attr, op, t in count_pool if attr not in ("partner_leave_weeks_full_pay", "birth_parent_leave_weeks_full_pay", "life_cover_multiple")]
attr, op, t = R.choice(fil_pool)
add("filter", f"Which countries have {SHORT[attr][0]} {op} {t:g} {SHORT[attr][1]} under version 3.0?",
    sorted(CNAME[c] for c, x in values(attr).items() if cmp_ops[op](x, t)), ALL_ADD, "S", note(attr), "set")
qtext, ans = R.choice([("Which BragsLabs offices have an on-site gym but no crèche?", sorted(o[1] for o in OFFICES if o[7] and not o[8])),
                       ("Which BragsLabs offices opened after 2019?", sorted(o[1] for o in OFFICES if o[3] > 2019))])
add("filter", qtext, ans, ["HB-*"], "M", answer_format="set")
al, ph = values("annual_leave_days"), values("public_holidays")
add("filter", "Which countries give at least 20 working days of paid annual leave and at least 10 paid public holidays under version 3.0?",
    sorted(CNAME[c] for c in COUNTRIES if al[c] >= 20 and ph[c] >= 10), ALL_ADD, "S", answer_format="set")

# ---------------- aggregates (3)
avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
agg_pool = []
for c in [c for c in COUNTRIES if c not in ("IN", "DE")]:
    cs = [t["csat"] for t in T if t["country"] == c and t["csat"]]
    agg_pool.append((f"What was the average CSAT score of HR helpdesk tickets in {CNAME[c]} between November 2025 and October 2026?",
                     round(sum(cs) / len(cs), 2), [f"TKT-{c}-*"], "Unrated tickets excluded.", "value"))
for c in [c for c in COUNTRIES if c != "UK"]:
    gs = [g for g in G if g["country"] == c]
    if gs:
        agg_pool.append((f"What share of grievances in {CNAME[c]} were upheld or partially upheld?",
                         round(sum(g["outcome"] in ("Upheld", "Partially upheld") for g in gs) / len(gs), 3), [f"GRV-{c}-*"], None, "ratio"))
for k in [k for k in TCATS if k != "reimbursement"]:
    hs = [t["resolution_hours"] for t in T if t["category"] == k]
    agg_pool.append((f"What was the average resolution time, in working hours, of {TCATS[k][0].lower()} tickets across all countries?",
                     avg(hs), ["TKT-*"], None, "value"))
agg_pool.append(("What share of exits were regretted losses?", round(sum(x["regretted"] for x in X) / len(X), 3), ["EXIT-*"], None, "ratio"))
for qtext, ans, ev, nt, fmt in pick(agg_pool, 3):
    add("aggregate", qtext, ans, ev, "L", nt, fmt)

# ---------------- themes (3)
def top3_named(counter, names):
    t = top3(counter)
    return [[names[k], n] for k, n in t] if t else None

yq = R.choice([yq for yq in quarters if yq not in ((2026, 2), (2025, 4)) and top3(Counter(g["category"] for g in G if (g["year"], g["quarter"]) == yq))])
add("theme", f"What were the three most common grievance categories across all countries in Q{yq[1]} {yq[0]}?",
    top3_named(Counter(g["category"] for g in G if (g["year"], g["quarter"]) == yq), GCATS), [f"GRV-*-{yq[0]}Q{yq[1]}"], "L", answer_format="ranked_list")
c = R.choice([c for c in COUNTRIES if c not in ("IN", "UK") and top3(Counter(x["primary_reason"] for x in X if x["country"] == c))])
add("theme", f"What were the three most common primary exit reasons in {CNAME[c]} between Q4 2025 and Q3 2026?",
    top3_named(Counter(x["primary_reason"] for x in X if x["country"] == c), EREASONS), [f"EXIT-{c}-*"], "L", answer_format="ranked_list")
c = R.choice([c for c in COUNTRIES if c not in ("IN", "US") and top3(Counter(s["theme"] for s in S if s["country"] == c))])
add("theme", f"Which three topics did respondents in {CNAME[c]} tag most often in the 2026 Pulse survey?",
    top3_named(Counter(s["theme"] for s in S if s["country"] == c), ST_LABEL), [f"PULSE26-{c}"], "L", answer_format="ranked_list")

# ---------------- version differences (3)
attr = R.choice([a_ for a_ in POLICY if any(POLICY[a_][c]["v1.0"] != POLICY[a_][c]["v2.0"] for c in VERSION_COUNTRIES["v1.0"])])
add("version_diff", f"For which countries did the {ATTR_LABEL[attr]} change between policy version 1.0 and version 2.0?",
    sorted(CNAME[c] for c in VERSION_COUNTRIES["v1.0"] if POLICY[attr][c]["v1.0"] != POLICY[attr][c]["v2.0"]), ["POL-v1.0-*", "POL-v2.0-*"], "M",
    answer_format="set")
add("version_diff", "Which countries were added to the policy manual in version 2.0?",
    sorted(CNAME[c] for c in VERSION_COUNTRIES["v2.0"] if c not in VERSION_COUNTRIES["v1.0"]), ["POL-v1.0-CH01", "POL-v2.0-CH01"], "M", answer_format="set")
c, attr = R.choice([(c, a_) for a_ in POLICY for c in VERSION_COUNTRIES["v2.0"] if POLICY[a_][c]["v2.0"] != POLICY[a_][c]["v3.0"]])
add("version_diff", f"What was the {ATTR_LABEL[attr]} for employees in {CNAME[c]} under policy version 2.0?", POLICY[attr][c]["v2.0"],
    [f"POL-v2.0-*"], "M")

# ---------------- temporal (2): a dated question on either side of a circular's effective date
PHR = {"annual_leave_days": ("How many days of annual leave", ""), "employer_retirement_contribution_pct": ("What employer retirement contribution", "%"),
       "paid_sick_days": ("How many paid sick days", ""), "partner_leave_weeks_full_pay": ("How many weeks of partner leave at full pay", "")}
dev_circ = {"HR-CIR-2026-14", "HR-CIR-2026-15", "HR-CIR-2026-04", "HR-CIR-2026-05"}
temp_pool = [c for c in CIRCULARS if c[5] in PHR and c[3] != ["ALL"] and c[0] not in dev_circ and c[6] is not None]
for circ in pick(temp_pool, 2):
    eff = date.fromisoformat(circ[2])
    before = R.random() < 0.5
    when = date(eff.year if eff.month > 1 else eff.year - 1, eff.month - 1 if eff.month > 1 else 12, 15) if before else date(eff.year, eff.month, 15)
    c = circ[3][0]
    what, unit = PHR[circ[5]]
    ans = circ[6] if before else circ[7]
    add("temporal", f"{what} applied to employees in {CNAME[c]} on {when.day} {when.strftime('%B %Y')}?",
        f"{ans:g}{unit}" if unit else ans, [circ[0]], "M", f"{circ[0]} changes it from {circ[6]:g} to {circ[7]:g} from {circ[2]}.")

# ---------------- comparisons (2) and sentiment shift (1)
k = R.choice([k for k in TCATS if k != "reimbursement"])
ks = [t for t in T if t["category"] == k]
add("comparison", f"What was the average resolution time (working hours) of {TCATS[k][0].lower()} tickets in May–October 2026 compared with November 2025–April 2026?",
    [avg([t["resolution_hours"] for t in ks if (t["year"], t["month"]) >= (2026, 5)]), avg([t["resolution_hours"] for t in ks if (t["year"], t["month"]) < (2026, 5)])],
    ["TKT-*"], "L", answer_format="tuple")
gc = R.choice([k for k in GCATS if k != "hybrid_policy"])
n = Counter((g["year"], g["quarter"]) for g in G if g["category"] == gc)
add("comparison", f"How did the number of grievances about {GCATS[gc].lower()} change from Q4 2025 to Q1 2026?", [n[(2025, 4)], n[(2026, 1)]],
    ["GRV-*-2025Q4", "GRV-*-2026Q1"], "L", answer_format="tuple")
pre = [x for x in X if (x["year"], x["quarter"]) < (2026, 2)]
post = [x for x in X if (x["year"], x["quarter"]) >= (2026, 2)]
r = R.choice([k for k in EREASONS if k != "office_mandate"])
share = lambda xs: round(sum(x["primary_reason"] == r for x in xs) / len(xs), 3)
add("sentiment_shift", f"How did the share of exits whose primary reason was '{EREASONS[r]}' change after the three-day hybrid rule took effect on 1 April 2026?",
    [share(pre), share(post)], ["EXIT-*"], "L", "Before = Q4 2025–Q1 2026; after = Q2–Q3 2026.", "tuple")

os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, "w", encoding="utf-8") as f:
    for q in Q:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")
print(len(Q), "questions", dict(Counter(q["type"] for q in Q)), "->", a.out)
