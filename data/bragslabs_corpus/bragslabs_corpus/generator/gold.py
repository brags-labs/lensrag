"""Compute gold questions and answers from the ledgers (independent of any system under test)."""
import sys, os, json, glob
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from events import CIRCULARS, CONFLICTS
from records import TCATS, GCATS, EREASONS, ST_LABEL

L = lambda n: json.load(open(os.path.join(LEDGER, n), encoding="utf-8"))
T, G, X, S = L("tickets.json"), L("grievances.json"), L("exit_notes.json"), L("survey_comments.json")
ADD_DOC = {c: f"POL-v3.0-CH{38+i}" for i, c in enumerate(ADDENDUM_ORDER)}
Q = []

def add(qtype, question, answer, evidence, tier, notes=None, answer_format="value"):
    Q.append({"qid": f"Q{len(Q)+1:03d}", "type": qtype, "question": question, "answer": answer, "answer_format": answer_format,
              "evidence_docs": evidence, "min_tier": tier, "notes": notes})

V3 = lambda a: {c: POLICY[a][c]["v3.0"] for c in COUNTRIES}
UNIT = {"annual_leave_days": "working days", "paid_sick_days": "working days", "birth_parent_leave_weeks_full_pay": "weeks",
        "partner_leave_weeks_full_pay": "weeks", "notice_period_senior_days": "calendar days", "standard_weekly_hours": "hours",
        "employer_retirement_contribution_pct": "%", "public_holidays": "days", "life_cover_multiple": "× base salary"}
NL_SICK_NOTE = "Netherlands sick pay is salary continuation for up to 104 weeks, not a day count; exclude it from day-based comparisons."

# ---------------- local lookups
for c, a in [("DE", "annual_leave_days"), ("IN", "annual_leave_days"), ("UK", "paid_sick_days"), ("US", "partner_leave_weeks_full_pay"),
             ("IE", "standard_weekly_hours"), ("AU", "partner_leave_weeks_full_pay"), ("SG", "notice_period_senior_days"), ("CA", "partner_leave_weeks_full_pay"),
             ("NL", "employer_retirement_contribution_pct"), ("AE", "paid_sick_days"), ("UK", "life_cover_multiple"), ("US", "public_holidays")]:
    add("local", f"Under policy version 3.0, what is the {ATTR_LABEL[a]} for employees in {CNAME[c]}?", POLICY[a][c]["v3.0"], [ADD_DOC[c]], "S")
add("local", "How many working days of paid paternity leave do employees in India receive under policy version 3.0?", 10, ["POL-v3.0-CH16", "POL-v3.0-CH39"], "S",
    "FAQ-IN-COUNTRY gives a stale value of 7 (planted conflict CF-06).")
add("local", "What is the night shift allowance per night in India under policy version 3.0?", "₹600", ["POL-v3.0-CH12"], "S")
add("local", "How many office days a week must hybrid employees attend under policy version 3.0?", 3, ["POL-v3.0-CH09"], "S")
add("local", "How many working days a year may employees work from another country under policy version 3.0?", 20, ["POL-v3.0-CH10", "POL-v3.0-CH36"], "S")
add("local", "What is the annual learning budget for an L4–L6 employee in India under version 3.0?", "₹40,000", ["POL-v3.0-CH24"], "S")

# ---------------- counts, filters, extrema, ranks over country addenda
al = V3("annual_leave_days")
add("count", "How many countries give employees more than 20 working days of paid annual leave under policy version 3.0?",
    sum(v > 20 for v in al.values()), [ADD_DOC[c] for c in COUNTRIES], "S", "UAE counted as 22 working days (30 calendar days); Australia's 3 Company days are excluded.")
add("filter", "Which countries give at least 25 working days of paid annual leave under version 3.0?", sorted(CNAME[c] for c, v in al.items() if v >= 25), [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="set")
add("extremum", "Which country has the highest paid annual leave entitlement under version 3.0, and how many days is it?", [CNAME[max(al, key=al.get)], max(al.values())], [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="tuple")
add("extremum", "Which country has the lowest paid annual leave entitlement under version 3.0?", sorted(CNAME[c] for c, v in al.items() if v == min(al.values())), [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="set")
nt = V3("notice_period_senior_days")
top3 = sorted(nt.items(), key=lambda kv: -kv[1])
add("rank", "Which countries have the longest contractual notice period for L4 and above employees under version 3.0?", sorted(CNAME[c] for c, v in nt.items() if v == top3[0][1]),
    [ADD_DOC[c] for c in COUNTRIES], "S", f"Tied at {top3[0][1]} days.", "set")
add("extremum", "Which country has the shortest notice period for L4 and above employees, and why?", ["United States", 14], [ADD_DOC["US"]], "S", "At-will employment; the Company normally gives 2 weeks' notice.", "tuple")
hrs = V3("standard_weekly_hours")
add("rank", "Rank the countries by standard weekly working hours, from shortest to longest, under version 3.0.", [[CNAME[c], v] for c, v in sorted(hrs.items(), key=lambda kv: (kv[1], kv[0]))], [ADD_DOC[c] for c in COUNTRIES], "S", "Ties share a rank.", "ranked_list")
add("count", "In how many countries is the standard working week shorter than 40 hours?", sum(v < 40 for v in hrs.values()), [ADD_DOC[c] for c in COUNTRIES], "S")
rp = V3("employer_retirement_contribution_pct")
add("rank", "Which three countries have the highest employer retirement contribution percentage under version 3.0?", [[CNAME[c], v] for c, v in sorted(rp.items(), key=lambda kv: -kv[1])[:3]], [ADD_DOC[c] for c in COUNTRIES], "S", "UAE has gratuity instead of a pension.", "ranked_list")
pl = V3("partner_leave_weeks_full_pay")
add("filter", "In which countries do partners receive more than 2 weeks of partner leave at full pay under version 3.0?", sorted(CNAME[c] for c, v in pl.items() if v > 2), [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="set")
add("extremum", "Which country gives the most partner (non-birth-parent) leave at full pay, and how much?", [CNAME[max(pl, key=pl.get)], max(pl.values())], [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="tuple")
bp = V3("birth_parent_leave_weeks_full_pay")
add("filter", "Which countries give more than the 16-week global minimum of birth-parent leave at full pay?", sorted(CNAME[c] for c, v in bp.items() if v > 16), [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="set")
sk = {c: v for c, v in V3("paid_sick_days").items() if c != "NL"}
add("rank", "Excluding the Netherlands, rank the top three countries by paid sick days at full pay under version 3.0.", [[CNAME[c], v] for c, v in sorted(sk.items(), key=lambda kv: -kv[1])[:3]], [ADD_DOC[c] for c in COUNTRIES], "S", NL_SICK_NOTE, "ranked_list")
add("count", "How many countries give exactly 10 paid sick days under version 3.0?", sum(v == 10 for v in sk.values()), [ADD_DOC[c] for c in COUNTRIES], "S", NL_SICK_NOTE)
ph = V3("public_holidays")
add("extremum", "Which country has the most paid public holidays under version 3.0?", [CNAME[max(ph, key=ph.get)], max(ph.values())], [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="tuple")
lc = V3("life_cover_multiple")
add("filter", "In which countries is life cover 4 times annual base salary?", sorted(CNAME[c] for c, v in lc.items() if v == 4), [ADD_DOC[c] for c in COUNTRIES], "S", answer_format="set")
add("count", "How many country addenda are there in policy version 3.0?", 10, [ADD_DOC[c] for c in COUNTRIES], "S")

# ---------------- version questions (tier M)
for a in ["annual_leave_days", "paid_sick_days", "birth_parent_leave_weeks_full_pay"]:
    ch = sorted(CNAME[c] for c in VERSION_COUNTRIES["v2.0"] if POLICY[a][c]["v2.0"] != POLICY[a][c]["v3.0"])
    add("version_diff", f"For which countries did the {ATTR_LABEL[a]} change between policy version 2.0 and version 3.0?", ch, ["POL-v2.0-*", "POL-v3.0-*"], "M", answer_format="set")
add("version_diff", "Which countries were added to the policy manual in version 3.0?", ["Australia", "United Arab Emirates"], ["POL-v3.0-CH01", "HR-CIR-2026-17"], "M", answer_format="set")
add("version_diff", "Which countries were covered by policy version 1.0?", sorted(CNAME[c] for c in VERSION_COUNTRIES["v1.0"]), ["POL-v1.0-CH01"], "M", answer_format="set")
add("version_diff", "How did the US paid time off entitlement change across versions 1.0, 2.0 and 3.0?", [15, 18, 20], ["POL-v1.0-CH36", "POL-v2.0-CH38", "POL-v3.0-CH38"], "M", answer_format="list")
add("version_diff", "How many office days a week did hybrid employees attend under version 2.0?", 2, ["POL-v2.0-CH09"], "M")
add("version_diff", "What was the work-from-another-country allowance under version 1.0?", "Not permitted", ["POL-v1.0-CH10"], "M")
add("version_diff", "By how much did the India night shift allowance increase between version 1.0 and version 3.0?", "₹200 (from ₹400 to ₹600)", ["POL-v1.0-CH12", "POL-v3.0-CH12"], "M")

# ---------------- date reasoning with circulars (tier M)
add("temporal", "What night shift allowance applies in India to a night worked on 15 December 2026?", "₹600", ["POL-v3.0-CH12", "HR-CIR-2026-14"], "M", "HR-CIR-2026-14 raises it to ₹700 only from 1 January 2027.")
add("temporal", "What night shift allowance applies in India to a night worked on 15 January 2027?", "₹700", ["HR-CIR-2026-14"], "M")
add("temporal", "How many office days a week were hybrid employees required to attend in March 2026?", 2, ["HR-CIR-2026-04", "POL-v2.0-CH09"], "M", "The three-day rule took effect on 1 April 2026.")
add("temporal", "How many days of annual leave will UK employees receive in 2027?", 27, ["HR-CIR-2026-15"], "M")
add("temporal", "List all HR circulars that announce changes taking effect after policy version 3.0 came into force.", sorted(c[0] for c in CIRCULARS if c[8] == "future"), ["HR-CIR-*"], "M", answer_format="set")
add("count", "How many HR circulars were issued in 2025?", sum(c[1].startswith("2025") for c in CIRCULARS), ["HR-CIR-2025-*"], "M")
add("count", "How many HR circulars changed the annual leave entitlement of a country (including announced future changes)?", sum(1 for c in CIRCULARS if c[5] == "annual_leave_days"), ["HR-CIR-*"], "M")

# ---------------- conflicts
add("conflict", "Is there an inconsistency in policy version 3.0 about paid sick leave in India, and how is it resolved?", "Yes: Chapter 15.1 gives 8 days but the global minimum (Chapter 37.1) is 10; HR-CIR-2026-12 confirms 10 days from 1 September 2026.",
    ["POL-v3.0-CH15", "POL-v3.0-CH37", "HR-CIR-2026-12"], "M", "Chapter 37 is retrieval-excluded; the circular is the retrievable evidence.", "text")
add("conflict", "Does the Hybrid FAQ agree with the current policy on office days?", "No: the FAQ (last reviewed 30 Nov 2025) says 2 days; the current rule is 3 days from 1 April 2026.", ["FAQ-HYBRID", "HR-CIR-2026-04", "POL-v3.0-CH09"], "M", answer_format="text")
add("conflict", "Which documents state an outdated annual leave value for UK or Singapore employees?", ["BEN-SG", "HB-LON"], ["HB-LON", "BEN-SG"], "M", answer_format="set")
add("conflict", "Which office handbook gives an outdated night shift allowance?", "HB-PNQ (Pune): ₹500 instead of ₹600", ["HB-PNQ"], "M", answer_format="text")
add("conflict", "Is the difference in hybrid office days between version 2.0 and version 3.0 a conflict?", "No: it is a legitimate policy update (2 → 3 days, HR-CIR-2026-04).", ["POL-v2.0-CH09", "POL-v3.0-CH09"], "M", answer_format="text")

# ---------------- offices (tier M)
add("filter", "Which BragsLabs offices have both an on-site gym and a crèche?", sorted(o[1] for o in OFFICES if o[7] and o[8]), ["HB-*"], "M", answer_format="set")
add("count", "How many BragsLabs offices are there in India?", len(OFFICE_BY_COUNTRY["IN"]), ["HB-*", "POL-v3.0-CH36"], "M")
add("extremum", "Which office has the largest headcount?", [max(OFFICES, key=lambda o: o[4])[1], max(o[4] for o in OFFICES)], ["HB-*"], "M", answer_format="tuple")
add("rank", "Rank the three oldest BragsLabs offices by opening year.", [[o[1], o[3]] for o in sorted(OFFICES, key=lambda o: (o[3], o[1]))[:3]], ["HB-*"], "M", answer_format="ranked_list")
add("count", "How many offices opened in 2025?", sum(o[3] == 2025 for o in OFFICES), ["HB-*"], "M")

# ---------------- records (tier L)
def tlabel(k): return TCATS[k][0]
for c, y, m in [("IN", 2026, 4), ("UK", 2026, 4), ("US", 2026, 5)]:
    ts = [t for t in T if t["country"] == c and t["year"] == y and t["month"] == m]
    add("count", f"How many HR helpdesk tickets were opened in {CNAME[c]} in {date(y,m,1).strftime('%B %Y')}?", len(ts), [f"TKT-{c}-{y}{m:02d}"], "L")
    top = Counter(t["category"] for t in ts).most_common(1)[0]
    add("extremum", f"What was the most common helpdesk ticket category in {CNAME[c]} in {date(y,m,1).strftime('%B %Y')}?", [tlabel(top[0]), top[1]], [f"TKT-{c}-{y}{m:02d}"], "L", answer_format="tuple")
ha = [t for t in T if t["category"] == "hybrid_attendance"]
bym = Counter((t["year"], t["month"]) for t in ha)
peak = max(bym, key=bym.get)
add("extremum", "In which month were the most hybrid attendance tickets raised across all countries?", [date(*peak, 1).strftime("%B %Y"), bym[peak]], ["TKT-*"], "L", answer_format="tuple")
add("count", "How many shift allowance tickets were raised in India in January and February 2026 combined?", sum(1 for t in T if t["country"] == "IN" and t["category"] == "shift_allowance" and (t["year"], t["month"]) in [(2026, 1), (2026, 2)]), ["TKT-IN-202601", "TKT-IN-202602"], "L")
re_t = [t for t in T if t["category"] == "reimbursement"]
def avg(xs): return round(sum(xs) / len(xs), 1) if xs else None
add("comparison", "What was the average resolution time (working hours) for expense reimbursement tickets in May–June 2026 compared with November 2025–April 2026?",
    [avg([t["resolution_hours"] for t in re_t if (t["year"], t["month"]) in [(2026, 5), (2026, 6)]]), avg([t["resolution_hours"] for t in re_t if (t["year"], t["month"]) < (2026, 5)])], ["TKT-*"], "L", "Migration to the new expense module (HR-CIR-2026-06).", "tuple")
for c in ["IN", "DE"]:
    cs = [t["csat"] for t in T if t["country"] == c and t["csat"]]
    add("aggregate", f"What was the average CSAT score of HR helpdesk tickets in {CNAME[c]} between November 2025 and October 2026?", round(sum(cs) / len(cs), 2), [f"TKT-{c}-*"], "L", "Unrated tickets excluded.")
tot = Counter(t["country"] for t in T)
add("rank", "Which three countries raised the most HR helpdesk tickets between November 2025 and October 2026?", [[CNAME[c], n] for c, n in tot.most_common(3)], ["TKT-*"], "L", answer_format="ranked_list")
# grievances
for (y, q) in [(2026, 2), (2025, 4)]:
    gs = [g for g in G if g["year"] == y and g["quarter"] == q]
    add("theme", f"What were the three most common grievance categories across all countries in Q{q} {y}?", [[GCATS[k], n] for k, n in Counter(g["category"] for g in gs).most_common(3)], [f"GRV-*-{y}Q{q}"], "L", answer_format="ranked_list")
hy = Counter((g["year"], g["quarter"]) for g in G if g["category"] == "hybrid_policy")
add("comparison", "How did the number of hybrid-policy grievances change from Q1 2026 to Q2 2026?", [hy[(2026, 1)], hy[(2026, 2)]], ["GRV-*-2026Q1", "GRV-*-2026Q2"], "L", answer_format="tuple")
add("count", "How many transport and safety grievances were filed in India in Q4 2025 and Q1 2026 combined?", sum(1 for g in G if g["country"] == "IN" and g["category"] == "transport_safety" and (g["year"], g["quarter"]) in [(2025, 4), (2026, 1)]), ["GRV-IN-2025Q4", "GRV-IN-2026Q1"], "L")
posh = [g for g in G if g["category"] == "posh_referral"]
add("count", "How many harassment complaints were referred to a committee across all countries between Q4 2024 and Q3 2026?", len(posh), ["GRV-*"], "L")
ic = [g for g in G if g["stage"] == "Internal Committee"]
add("aggregate", "What was the average number of days to resolve cases handled by India's Internal Committee?", avg([g["days_to_resolve"] for g in ic]), ["GRV-IN-*"], "L")
up = [g for g in G if g["country"] == "UK"]
add("aggregate", "What share of UK grievances were upheld or partially upheld?", round(sum(g["outcome"] in ("Upheld", "Partially upheld") for g in up) / len(up), 3), ["GRV-UK-*"], "L", answer_format="ratio")
# exits
pre = [x for x in X if (x["year"], x["quarter"]) < (2026, 2)]
post = [x for x in X if (x["year"], x["quarter"]) >= (2026, 2)]
share = lambda xs, k: round(sum(x["primary_reason"] == k for x in xs) / len(xs), 3)
add("sentiment_shift", "How did the share of exits whose primary reason was the office attendance requirement change after the three-day hybrid rule took effect on 1 April 2026?",
    [share(pre, "office_mandate"), share(post, "office_mandate")], ["EXIT-*"], "L", "Before = Q4 2025–Q1 2026; after = Q2–Q3 2026.", "tuple")
neg = lambda xs: round(sum(x["sentiment"] == "negative" for x in xs) / len(xs), 3)
add("sentiment_shift", "Did exit-interview sentiment become more negative after the three-day hybrid rule? Give the share of negative exit conversations before and after 1 April 2026.",
    [neg(pre), neg(post)], ["EXIT-*"], "L", "Sentiment labels are ledger ground truth; text conveys tone through interviewer notes and quotes.", "tuple")
for c in ["IN", "UK"]:
    xs = [x for x in X if x["country"] == c]
    add("theme", f"What were the top three primary exit reasons in {CNAME[c]} between Q4 2025 and Q3 2026?", [[EREASONS[k], n] for k, n in Counter(x["primary_reason"] for x in xs).most_common(3)], [f"EXIT-{c}-*"], "L", answer_format="ranked_list")
add("count", "How many exit interviews were recorded in Q3 2026 across all countries?", sum(1 for x in X if (x["year"], x["quarter"]) == (2026, 3)), ["EXIT-*-2026Q3"], "L")
rj = [x for x in X if x["would_rejoin"] == "Yes"]
add("aggregate", "What share of exiting employees said they would rejoin BragsLabs?", round(len(rj) / len(X), 3), ["EXIT-*"], "L", answer_format="ratio")
# surveys
for c in ["IN", "US"]:
    ss = [s for s in S if s["country"] == c and s["sentiment"] == "negative"]
    add("theme", f"In the 2026 Pulse survey, which three topics attracted the most negative comments in {CNAME[c]}?", [[ST_LABEL[k], n] for k, n in Counter(s["theme"] for s in ss).most_common(3)], [f"PULSE26-{c}"], "L", "Sentiment of each comment is ledger ground truth.", "ranked_list")
for c in COUNTRIES[:0]:
    pass
en = {c: [s["enps_score"] for s in S if s["country"] == c] for c in COUNTRIES}
def enps(xs): return round(100 * (sum(v >= 9 for v in xs) - sum(v <= 6 for v in xs)) / len(xs), 1)
best = max(en, key=lambda c: enps(en[c]))
add("extremum", "Which country had the highest eNPS in the 2026 Pulse survey (promoters 9–10 minus detractors 0–6)?", [CNAME[best], enps(en[best])], ["PULSE26-*"], "L", answer_format="tuple")
add("count", "How many Pulse survey 2026 comments were tagged with the topic 'Hybrid and office days'?", sum(s["theme"] == "hybrid_policy" for s in S), ["PULSE26-*"], "L")

def tiers():
    idx = []
    for p in sorted(glob.glob(f"{CORPUS}/**/*.md", recursive=True)):
        rel = os.path.relpath(p, CORPUS)
        meta = {}
        for line in open(p, encoding="utf-8").read().split("---\n")[1].splitlines():
            if ": " in line:
                k, v = line.split(": ", 1); meta[k] = v.strip('"')
        excl = meta.get("retrieval_exclude") == "true"
        top = rel.split("/")[0]
        if top == "policy":
            tier = "S" if rel.startswith("policy/v3.0") else "M"
        elif top in ("circulars", "faqs", "handbooks", "benefits"):
            tier = "M"
        elif top == "reports":
            tier = "L"
        else:
            tier = "L"
        words = wc(open(p, encoding="utf-8").read().split("---\n", 2)[2])
        idx.append({"path": rel, "doc_id": meta.get("doc_id"), "doc_type": meta.get("doc_type"), "country": meta.get("country"), "tier": tier,
                    "retrieval_exclude": excl, "words": words})
    return idx

if __name__ == "__main__":
    os.makedirs(GOLD, exist_ok=True)
    with open(f"{GOLD}/questions.jsonl", "w", encoding="utf-8") as f:
        for q in Q: f.write(json.dumps(q, ensure_ascii=False) + "\n")
    idx = tiers()
    with open(f"{ROOT}/manifest.jsonl", "w", encoding="utf-8") as f:
        for r in idx: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summ = defaultdict(lambda: [0, 0])
    for r in idx:
        for t in ("S", "M", "L"):
            if "SML".index(r["tier"]) <= "SML".index(t) and not r["retrieval_exclude"]:
                summ[t][0] += 1; summ[t][1] += r["words"]
    print("questions", len(Q), Counter(q["type"] for q in Q))
    print({t: tuple(v) for t, v in summ.items()}, "excluded", sum(r["retrieval_exclude"] for r in idx), "total body words", sum(r["words"] for r in idx))
