"""Split v3.0 manual into chapter files and derive v2.0 / v1.0 versions."""
import re, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *

SRC = "/home/claude/src/manual_v3.md"

def load_chapters():
    text = rename(open(SRC, encoding="utf-8").read())
    text = text.replace("Oct 31, 2026 · @Gautam Pandey", "Issued 31 October 2026 · HR Policy Office")
    parts = re.split(r"(?m)^(?=## Chapter \d+\. )", text)
    preamble, chapters = parts[0], parts[1:]
    out = []
    for ch in chapters:
        m = re.match(r"## Chapter (\d+)\. (.+)", ch)
        out.append((int(m.group(1)), m.group(2).strip(), ch))
    return preamble, out

ADD_CC = {38 + i: c for i, c in enumerate(ADDENDUM_ORDER)}

def at_a_glance(country, version):
    rows = ["| Entitlement (Company policy) | Value |", "| --- | --- |"]
    for attr, label in ATTR_LABEL.items():
        v = POLICY[attr].get(country, {}).get(version)
        if v is None:
            continue
        if attr == "paid_sick_days" and country == "NL":
            vs = "100% of salary in year 1, 70% in year 2 (up to 104 weeks)" if version != "v1.0" else "70% of salary for up to 104 weeks, topped up to 100% for the first 26 weeks"
        elif attr == "employer_retirement_contribution_pct" and country == "AE":
            vs = "no pension for expatriates; end-of-service gratuity instead (GPSSA for UAE nationals)"
        elif attr == "partner_leave_weeks_full_pay" and country == "IN":
            vs = f"{GLOBAL['india_paternity_working_days'][version]} working days"
        elif attr == "annual_leave_days" and country == "AE":
            vs = "30 calendar days (22 working days)"
        elif attr == "annual_leave_days" and country == "AU":
            vs = "20 working days (4 weeks), plus 3 Company days between Christmas and New Year"
        else:
            vs = f"{v:g}"
        rows.append(f"| {label[0].upper()+label[1:]} | {vs} |")
    return "\n".join(rows)

def older(text, version, chap_no, country=None):
    vy = VERSION_YEAR[version]
    g = {k: v[version] for k, v in GLOBAL.items()}
    R = []
    def r(a, b, regex=False):
        R.append((a, b, regex))
    # --- global value substitutions ---
    od = g["hybrid_office_days"]
    r("**3 days a week**", f"**{od} days a week**")
    r("| Hybrid | A mix of Company office and home workplace | 3 days a week", f"| Hybrid | A mix of Company office and home workplace | {od} days a week")
    r("| 3 days a week, averaged over each calendar month (12 days in a month with 20 working days)", f"| {od} days a week, averaged over each calendar month ({od*4} days in a month with 20 working days)")
    r("Each team fixes 2 anchor days a week", f"Each team fixes {g['anchor_days']} anchor day{'s' if g['anchor_days']>1 else ''} a week")
    r("for example, 2 days in a week with one holiday", f"for example, {od-1} day{'s' if od-1>1 else ''} in a week with one holiday")
    r("capped at 20% of each", f"capped at {g['remote_cap_pct']}% of each")
    if g["work_from_abroad_days"] == 0:
        r(r"- Remote and hybrid employees may work from a country other than their country of employment for up to \*\*20 working days in a calendar year\*\*[^\n]*",
          "- Remote and hybrid employees may not work from a country other than their country of employment, except during approved business travel.", True)
    else:
        r("for up to **20 working days in a calendar year**", f"for up to **{g['work_from_abroad_days']} working days in a calendar year**")
        r("Up to 20 working days a year", f"Up to {g['work_from_abroad_days']} working days a year")
    for key, v3 in [("afternoon_shift_allowance_inr", 250), ("late_shift_allowance_inr", 400), ("night_shift_allowance_inr", 600)]:
        name = key.split("_")[0].capitalize()
        r(f"| {name} | ₹{v3} |", f"| {name} | ₹{indian(g[key])} |")
    r("| One-time home office setup allowance | No | ₹10,000 | ₹25,000 | No |",
      f"| One-time home office setup allowance | No | ₹{indian(g['hybrid_setup_allowance_inr'])} | ₹{indian(g['remote_setup_allowance_inr'])} | No |")
    r("| Monthly internet and phone allowance | No | ₹1,000 | ₹1,500 |",
      f"| Monthly internet and phone allowance | No | ₹{indian(g['hybrid_internet_allowance_inr'])} | ₹{indian(g['remote_internet_allowance_inr'])} |")
    el = POLICY["annual_leave_days"]["IN"][version]
    r("| Earned / privilege leave (EL) | 18 | 1.5 days per month", f"| Earned / privilege leave (EL) | {el} | {el/12:g} days per month")
    sk = POLICY["paid_sick_days"]["IN"][version]
    r("| Sick leave (SL) | 8 |", f"| Sick leave (SL) | {sk} |")
    r("- **10 working days** of paid leave for the birth or adoption", f"- **{g['india_paternity_working_days']} working days** of paid leave for the birth or adoption")
    r("₹5,00,000 per family per year", f"₹{indian(g['health_sum_insured_inr'])} per family per year")
    r("Wellbeing allowance of ₹12,000", f"Wellbeing allowance of ₹{indian(g['wellbeing_allowance_inr'])}")
    r("| L1–L3 | ₹25,000 |", f"| L1–L3 | ₹{indian(g['learning_budget_l1_l3_inr'])} |")
    r("| L4–L6 | ₹40,000 |", f"| L4–L6 | ₹{indian(g['learning_budget_l4_l6_inr'])} |")
    r("| L7 and above | ₹75,000 |", f"| L7 and above | ₹{indian(g['learning_budget_l7_inr'])} |")
    r("a bonus of ₹25,000 to ₹60,000", f"a bonus of ₹{indian(g['referral_bonus_min_inr'])} to ₹{indian(g['referral_bonus_max_inr'])}")
    r("an annual budget of ₹30,000 for co-working", f"an annual budget of ₹{indian(g['coworking_budget_inr'])} for co-working")
    r("| Paid annual leave (vacation, PTO or earned leave) | 18 working days", f"| Paid annual leave (vacation, PTO or earned leave) | {g['global_min_annual_leave_days']} working days")
    r("| Paid sick leave | 10 working days a year", f"| Paid sick leave | {g['global_min_sick_days']} working days a year")
    r("| Paid birth-parent leave | 16 weeks at full pay", f"| Paid birth-parent leave | {g['global_min_birth_parent_weeks']} weeks at full pay")
    # --- country addendum prose values ---
    P = lambda a, c: POLICY[a][c][version]
    if country == "US":
        r("| Paid time off (vacation and personal) | 20 days a year", f"| Paid time off (vacation and personal) | {P('annual_leave_days','US')} days a year")
        r("| Paid sick leave | 10 days a year, usable", f"| Paid sick leave | {P('paid_sick_days','US')} days a year, usable")
        r("**16 weeks at full pay** for birth parents, and 8 weeks", f"**{P('birth_parent_leave_weeks_full_pay','US')} weeks at full pay** for birth parents, and {P('partner_leave_weeks_full_pay','US')} weeks")
        r("100% of the first 5%", f"100% of the first {P('employer_retirement_contribution_pct','US')}%")
        r("| Company holidays | 11 days:", f"| Company holidays | {P('public_holidays','US')} days:")
    if country == "UK":
        r("**25 days' paid annual leave", f"**{P('annual_leave_days','UK')} days' paid annual leave")
        r("10 days at full pay in the first year of service, rising to 20 days", f"{P('paid_sick_days','UK')} days at full pay in the first year of service, rising to {P('paid_sick_days','UK')+10} days")
        r("| 16 weeks at full pay, then statutory pay |", f"| {P('birth_parent_leave_weeks_full_pay','UK')} weeks at full pay, then statutory pay |")
        r("employer contribution of 5% of qualifying earnings", f"employer contribution of {P('employer_retirement_contribution_pct','UK')}% of qualifying earnings")
    if country == "DE":
        r("**28 working days' paid holiday**", f"**{P('annual_leave_days','DE')} working days' paid holiday**")
        r("employer subsidy of 20%", f"employer subsidy of {P('employer_retirement_contribution_pct','DE')}%")
    if country == "NL":
        r("employer contribution of 10%", f"employer contribution of {P('employer_retirement_contribution_pct','NL')}%")
    if country == "IE":
        r("**25 days' annual leave**", f"**{P('annual_leave_days','IE')} days' annual leave**")
        r("full pay for 10 days a year", f"full pay for {P('paid_sick_days','IE')} days a year")
        r("employer contribution of 6%", f"employer contribution of {P('employer_retirement_contribution_pct','IE')}%")
    if country == "SG":
        r("| 18 days, rising to 21 days after 5 years |", f"| {P('annual_leave_days','SG')} days, rising to {P('annual_leave_days','SG')+3} days after 5 years |")
    if country == "CA":
        r("| 3 weeks from joining, 4 weeks after 3 years, 5 weeks after 8 years |", "| 3 weeks from joining, 4 weeks after 5 years |")
        r("Non-birth parent: topped up to full salary for 6 weeks", f"Non-birth parent: topped up to full salary for {P('partner_leave_weeks_full_pay','CA'):g} weeks")
        r("10 paid sick and personal days", f"{P('paid_sick_days','CA')} paid sick and personal days")
        r("Company match of up to 5%", f"Company match of up to {P('employer_retirement_contribution_pct','CA')}%")
    # --- law names that post-date the version ---
    if version == "v1.0":
        r("Digital Personal Data Protection Act, 2023 (DPDP Act) and its rules", "Information Technology Act, 2000 and the Reasonable Security Practices Rules, 2011 (SPDI Rules)")
        r("Digital Personal Data Protection Act, 2023 and its rules", "Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011")
        r("DPDP Act", "SPDI Rules")
        r("Data Protection Board of India", "Grievance Officer escalation to the CHRO")
    for a, b, rx in R:
        text = re.sub(a, b, text) if rx else text.replace(a, b)
    # drop sentences that cite years after the version year (outside tables/headings)
    future = "|".join(str(y) for y in range(vy + 1, 2031))
    fre = re.compile(rf"\b({future})\b")
    lines = []
    for line in text.split("\n"):
        if fre.search(line):
            if line.startswith("|"):
                line = re.sub(rf"\s*[;,]?\s*\((?:from|since|for children born[^)]*?)[^)]*\b(?:{future})\b[^)]*\)", "", line)
                line = re.sub(rf"[;,]?\s*day-one right(?: to leave)? from \d+ \w+ (?:{future})", "", line)
                if fre.search(line):
                    continue
            elif line.startswith("#"):
                pass
            else:
                prefix = re.match(r"^(\s*(?:[-*]|\d+\.)\s+)?", line).group(0)
                body = line[len(prefix):]
                sents = re.split(r"(?<=[.;])\s+(?=[A-Z*])", body)
                keep = [s for s in sents if not fre.search(s)]
                if not keep:
                    continue
                line = prefix + " ".join(keep)
        lines.append(line)
    return "\n".join(lines)

def renumber(text, old, new):
    if old == new:
        return text
    text = re.sub(rf"(?m)^## Chapter {old}\.", f"## Chapter {new}.", text)
    return re.sub(rf"(?<![\d.]){old}\.(\d+)", lambda m: f"{new}.{m.group(1)}", text)

def fix_refs(text, version, add_range):
    a, b = add_range
    text = text.replace("Chapters 38–47", f"Chapters {a}–{b}")
    text = text.replace("(Chapters 38–47)", f"(Chapters {a}–{b})")
    n = len(VERSION_COUNTRIES[version])
    text = text.replace("in each of its 10 countries", f"in each of its {n} countries")
    text = text.replace("ten countries", f"{['zero','one','two','three','four','five','six','seven','eight','nine','ten'][n]} countries")
    names = [CNAME[c] for c in VERSION_COUNTRIES[version]]
    names = [("the " + x) if x in ("United Kingdom", "Netherlands", "United Arab Emirates", "United States") else x for x in names]
    country_list = ", ".join(names[:-1]) + " and " + names[-1]
    text = re.sub(r"\*\*United States, India, the United Kingdom.*?Australia\*\*", f"**{country_list}**", text)
    if version == "v1.0":
        text = text.replace("Chapters 1–35 set the Company's global standards, Chapter 36 covers cross-border work, Chapter 37 compares key entitlements, and ", "Chapters 1–35 set the Company's global standards, and ")
        text = re.sub(r"Chapters 11 and 36", "Chapter 11", text)
        text = re.sub(r" and Chapter 36", "", text)
        text = re.sub(r" ?\(Chapter 37\)", "", text)
        text = text.replace("in Chapter 37", "in Section 1.9")
    return text

def header_line(version):
    eff = {"v1.0": "1 April 2022", "v2.0": "1 January 2024", "v3.0": "1 November 2026"}[version]
    sup = {"v1.0": " Superseded by version 2.0 on 1 January 2024.", "v2.0": " Superseded by version 3.0 on 1 November 2026.", "v3.0": ""}[version]
    return eff, sup

def build():
    preamble, chapters = load_chapters()
    index = []
    for version in ["v3.0", "v2.0", "v1.0"]:
        vc = VERSION_COUNTRIES[version]
        eff, sup = header_line(version)
        # chapter plan
        plan = []
        for no, title, body in chapters:
            if no <= 35:
                plan.append((no, no, title, body, None))
        if version != "v1.0":
            plan.append((36, 36, chapters[35][1], chapters[35][2], None))
            plan.append((37, 37, chapters[36][1], chapters[36][2], None))
            start = 38
        else:
            start = 36
        k = start
        for no, title, body in chapters[37:]:
            cc = ADD_CC[no]
            if cc in vc:
                plan.append((no, k, title, body, cc)); k += 1
        add_range = (start, k - 1)
        for old, new, title, body, cc in plan:
            text = body
            if version != "v3.0":
                text = older(text, version, old, cc)
                text = renumber(text, old, new)
            if old == 37 and version != "v3.0":
                # drop comparison rows for countries not yet present
                keep = []
                for line in text.split("\n"):
                    if line.startswith("| ") and any(line.startswith(f"| {CNAME[c]} |") for c in COUNTRIES if c not in vc):
                        continue
                    keep.append(line)
                text = "\n".join(keep)
                text = re.sub(r"\n\*\*Sources \(selected changes verified\):\*\*.*", "", text)
                text = text.replace("Figures are as of Oct 31, 2026", f"Figures are as of {eff}")
            text = fix_refs(text, version, add_range)
            if cc:
                text = text.rstrip() + f"\n\n### {new}.{len(re.findall(rf'(?m)^### {new}\.', text))+1} Key entitlements at a glance\n\n" \
                       f"The table below summarises the main Company entitlements for employees of {ENTITY[cc]} under policy version {version[1:]}.\n\n" + at_a_glance(cc, version)
            intro = ""
            if new == 1:
                p = rename(preamble.split("\n", 3)[-1]) if True else ""
                p = fix_refs(p, version, add_range)
                p = p.replace("Policy version 3.0, effective 1 November 2026", f"Policy version {version[1:]}, effective {eff}")
                intro = f"# Global HR Policy Manual — {COMPANY}\n\n" + p.strip() + sup + "\n\n"
            vtag = f"*{COMPANY} Global HR Policy Manual · version {version[1:]} · effective {eff}.{sup}*\n\n"
            meta = {
                "doc_id": f"POL-{version}-CH{new:02d}",
                "doc_type": "policy_manual_chapter",
                "company": COMPANY,
                "title": f"Chapter {new}. {re.sub(r'^Chapter \d+\. ', '', title)}",
                "version": version[1:],
                "effective_date": VERSION_DATE[version],
                "status": "current" if version == "v3.0" else "superseded",
                "superseded_by": {"v1.0": "2.0", "v2.0": "3.0", "v3.0": None}[version],
                "chapter": new,
                "country": cc if cc else "GLOBAL",
                "retrieval_exclude": old == 37,
            }
            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
            rel = f"policy/{version}/ch{new:02d}_{slug}.md"
            write_doc(rel, meta, intro + vtag + text)
            index.append({"path": rel, **meta})
    save_ledger("policy_chapters_index.json", index)
    save_ledger("policy_values.json", {"POLICY": POLICY, "GLOBAL": GLOBAL, "VERSION_COUNTRIES": VERSION_COUNTRIES})
    print(len(index), "chapter files")

if __name__ == "__main__":
    build()
