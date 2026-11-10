"""Validate the corpus against the ledger and the gold set."""
import sys, os, json, glob, re
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from common import *

errors, checks = [], 0
def check(cond, msg):
    global checks
    checks += 1
    if not cond: errors.append(msg)

files = sorted(glob.glob(f"{CORPUS}/**/*.md", recursive=True))
check(len(files) == 500, f"file count {len(files)}")
ids, texts = [], {}
for p in files:
    t = open(p, encoding="utf-8").read()
    m = re.search(r"(?m)^doc_id: (.+)$", t)
    did = m.group(1).strip('"'); ids.append(did); texts[did] = t
    check(t.startswith("---\n") and t.count("---\n") >= 2, f"front matter {p}")
    check("Global Data Science" not in t and "gdsai" not in t.lower(), f"old company name in {p}")
    body = t.split("---\n", 2)[2]
    check(not re.search(r"\[(?:amount|name|company|City|number|list|x)\b", body), f"placeholder in {p}")
dups = [k for k, v in Counter(ids).items() if v > 1]
check(not dups, f"duplicate doc ids {dups}")
words = sum(wc(t.split("---\n", 2)[2]) for t in texts.values())
check(words >= 1_500_000, f"word count {words}")

# policy values in at-a-glance tables match the ledger
ADD = {c: 38 + i for i, c in enumerate(ADDENDUM_ORDER)}
for v in ["v1.0", "v2.0", "v3.0"]:
    k = 38 if v != "v1.0" else 36
    for c in ADDENDUM_ORDER:
        if c not in VERSION_COUNTRIES[v]: continue
        did = f"POL-{v}-CH{k}"; k += 1
        t = texts[did]
        check(CNAME[c] in t.split("\n", 15)[4] or CNAME[c] in t[:600], f"{did} country mismatch")
        for attr, label in ATTR_LABEL.items():
            val = POLICY[attr][c][v]
            row = [l for l in t.splitlines() if l.startswith(f"| {label[0].upper()+label[1:]} |")]
            check(row, f"{did} missing row {attr}")
            if row and not (c == "NL" and attr == "paid_sick_days") and not (c == "AE" and attr in ("employer_retirement_contribution_pct", "annual_leave_days")) \
               and not (c == "IN" and attr == "partner_leave_weeks_full_pay") and not (c == "AU" and attr == "annual_leave_days"):
                check(f"| {val:g} |" in row[0], f"{did} {attr} expected {val} got {row[0]}")

# version-specific global values in chapter text
for v in ["v1.0", "v2.0", "v3.0"]:
    check(f"**{GLOBAL['hybrid_office_days'][v]} days a week**" in texts[f"POL-{v}-CH09"], f"hybrid days {v}")
    check(f"| Night | ₹{indian(GLOBAL['night_shift_allowance_inr'][v])} |" in texts[f"POL-{v}-CH12"], f"night allowance {v}")
    check(f"| L1–L3 | ₹{indian(GLOBAL['learning_budget_l1_l3_inr'][v])} |" in texts[f"POL-{v}-CH24"], f"learning budget {v}")
check("may not work from a country other than" in texts["POL-v1.0-CH10"], "v1 abroad rule")
check("**10 working days in a calendar year**" in texts["POL-v2.0-CH10"], "v2 abroad rule")
for did in [d for d in ids if d.startswith("POL-v1.0")]:
    body = texts[did].split("---\n", 2)[2]
    check(not re.search(r"\b202[5-9]\b", body), f"anachronistic year in {did}")

# planted conflicts are present
check("| 2 days a week, averaged" in texts["FAQ-HYBRID"] and "3 days a week" not in texts["FAQ-HYBRID"], "CF-07 stale hybrid FAQ")
check("**7 working days**" in texts["FAQ-IN-COUNTRY"], "CF-06 stale paternity FAQ")
check("receive 23 days of paid annual leave" in texts["HB-LON"], "CF-08 stale London handbook")
check("₹500 per night" in texts["HB-PNQ"], "CF-09 stale Pune handbook")
check("| Annual leave | 16 working days |" in texts["BEN-SG"], "CF-10 stale SG benefits")
check("| Sick leave (SL) | 8 |" in texts["POL-v3.0-CH15"], "CF-01 India sick 8 in v3")
check("| Paid sick leave | 10 working days a year" in texts["POL-v3.0-CH37"], "CF-01 global min 10")
check("**Until 1 January 2027" in texts["HR-CIR-2026-14"] or "Until 1 January 2027" in texts["HR-CIR-2026-14"], "CF-02 future circular wording")

# record files agree with ledgers
L = lambda n: json.load(open(os.path.join(LEDGER, n), encoding="utf-8"))
T, G, X, S = L("tickets.json"), L("grievances.json"), L("exit_notes.json"), L("survey_comments.json")
for t in T[::97]:
    did = f"TKT-{t['country']}-{t['year']}{t['month']:02d}"
    check(f"### Ticket {t['id']} — " in texts[did], f"ticket {t['id']} missing")
for g in G[::53]:
    did = f"GRV-{g['country']}-{g['year']}Q{g['quarter']}"
    check(f"### Case {g['id']} — " in texts[did] and f"**Days to resolve:** {g['days_to_resolve']}" in texts[did], f"grievance {g['id']}")
for x in X[::31]:
    did = f"EXIT-{x['country']}-{x['year']}Q{x['quarter']}"
    check(f"### Exit interview {x['id']}" in texts[did], f"exit {x['id']}")
for s in S[::71]:
    check(f"**{s['id']}**" in texts[f"PULSE26-{s['country']}"], f"survey {s['id']}")
# record_count metadata equals headings in file
for did, t in texts.items():
    m = re.search(r"(?m)^record_count: (\d+)$", t)
    if m:
        n = len(re.findall(r"(?m)^### (?:Ticket|Case|Exit interview) ", t)) or len(re.findall(r"(?m)^\*\*PULSE26-", t))
        check(n == int(m.group(1)), f"{did} record_count {m.group(1)} vs {n}")

# gold answers that are counts over files can be re-derived from text
for q in [json.loads(l) for l in open(f"{GOLD}/questions.jsonl", encoding="utf-8")]:
    if q["type"] == "count" and q["question"].startswith("How many HR helpdesk tickets were opened in"):
        did = q["evidence_docs"][0]
        n = len(re.findall(r"(?m)^### Ticket ", texts[did]))
        check(n == q["answer"], f"{q['qid']} text count {n} vs gold {q['answer']}")
    for e in q["evidence_docs"]:
        if "*" not in e:
            check(e in texts, f"{q['qid']} evidence {e} not found")

print(f"{checks} checks, {len(errors)} errors, {len(files)} files, {words:,} words")
for e in errors[:40]: print(" -", e)
