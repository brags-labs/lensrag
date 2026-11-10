"""Generate circulars, FAQs, office handbooks, benefit summaries, change log and annual HR reports."""
import sys, os, json, glob
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from events import CIRCULARS, CONFLICTS

rng = random.Random(SEED + 7)
D = lambda s: date.fromisoformat(s)
fmt = lambda s: D(s).strftime("%d %B %Y").lstrip("0")

def load(name):
    return json.load(open(os.path.join(LEDGER, name), encoding="utf-8"))

ATTR_CHAPTER = {"annual_leave_days": None, "paid_sick_days": "15", "birth_parent_leave_weeks_full_pay": "16", "partner_leave_weeks_full_pay": "16",
                "employer_retirement_contribution_pct": None, "hybrid_office_days": "9", "work_from_abroad_days": "10.6 and 36", "night_shift_allowance_inr": "12.3",
                "learning_budget_l1_l3_inr": "24.1", "global_min_birth_parent_weeks": "37.1", "wellbeing_allowance_inr": "19.7", "remote_internet_allowance_inr": "14.1",
                "health_sum_insured_inr": "19.1", "india_paternity_working_days": "16.4", "global_min_sick_days": "37.1", "remote_cap_pct": "10.1"}
ADD_CH = {c: 38 + i for i, c in enumerate(ADDENDUM_ORDER)}

def chap_for(attr, countries):
    ch = ATTR_CHAPTER.get(attr)
    if ch: return ch
    c = countries[0]
    return str(ADD_CH.get(c, 37)) if c != "ALL" else "37"

SUBJECT = {"annual_leave_days": "paid annual leave entitlement", "paid_sick_days": "paid sick leave entitlement", "hybrid_office_days": "minimum number of office days for hybrid employees",
           "work_from_abroad_days": "number of working days employees may work from another country", "night_shift_allowance_inr": "night shift allowance",
           "learning_budget_l1_l3_inr": "annual learning budget for L1–L3 employees", "global_min_birth_parent_weeks": "global minimum birth-parent leave at full pay",
           "global_min_sick_days": "global minimum paid sick leave", "wellbeing_allowance_inr": "annual wellbeing allowance", "remote_internet_allowance_inr": "monthly internet allowance for remote employees",
           "health_sum_insured_inr": "group health insurance sum insured", "india_paternity_working_days": "paid paternity leave", "remote_cap_pct": "cap on remote roles per business unit",
           "employer_retirement_contribution_pct": "employer retirement contribution", "partner_leave_weeks_full_pay": "partner / non-birth-parent leave at full pay"}
EXTRA_SECTIONS = [
 ("Impact on related policies", ["Related allowances, balances and approvals in the HRMS are updated automatically; no new form is needed.", "Payroll will show the change as a separate line on the first payslip after the effective date.", "Country addenda that state a more favourable local rule continue to apply.", "The change does not alter notice periods, probation terms or performance ratings."]),
 ("Communication plan", ["Country HR leads will brief people managers in the next monthly managers' call.", "An intranet article and a short video explainer will be published within a week.", "HRBPs will hold two 30-minute drop-in sessions in each region.", "The HR helpdesk has been briefed and will tag related tickets with this circular number."]),
 ("Monitoring and review", ["HR will review adoption, helpdesk volumes and feedback after three months.", "Any unintended effect on particular groups (for example caregivers or employees with disabilities) will be reported to the CHRO.", "Results will be shared in the next Pulse survey read-out."]),
]
def fmt_val(attr, v, c=None):
    if v is None: return "—"
    if attr.endswith("_inr"): return "₹" + indian(v) + (" per night" if "shift" in attr else "")
    if attr.endswith("_pct"): return f"{v:g}%"
    if "weeks" in attr: return f"{v:g} weeks"
    if attr in ("hybrid_office_days",): return f"{v} office days a week"
    if attr == "work_from_abroad_days": return "not permitted" if v == 0 else f"{v} working days a year"
    if attr == "india_paternity_working_days": return f"{v} working days"
    return f"{v:g} days"

SIGN = {"ALL": ("Anita Desai", "Chief Human Resources Officer"), **{c: (HR_LEAD[c], f"HR Lead, {CNAME[c]}") for c in COUNTRIES}}

REASONS = [
 "The change follows the annual benchmarking of our benefits against the {market} market and feedback from the {year} employee survey.",
 "Leadership reviewed the cost and impact of this change with Finance and the country HR leads before approving it.",
 "This change brings our policy in line with peer employers in the data and AI sector and supports retention of experienced staff.",
 "Several employees raised this topic through the HR helpdesk and the Pulse survey; this circular responds to that feedback.",
 "The change also reflects updates in local law and in the guidance issued by the relevant authorities.",
]
TRANSITION = [
 "Requests already approved before the effective date are honoured on their original terms.",
 "Where an entitlement accrues monthly, the new rate applies from the first full month after the effective date and is pro-rated for the year.",
 "Any arrears arising from this change are paid in the first payroll run after the effective date.",
 "Employees on notice, on long leave or on international assignment are covered from the effective date in the same way as other employees.",
 "Managers should not change approved plans because of this circular without discussing them with the employee and the HRBP.",
]
EMP_ACTIONS = ["Read this circular and the updated policy chapter on the intranet.", "Check your balances or allowances in the HRMS after the effective date.",
               "Raise any question through the HR helpdesk, quoting the circular number.", "Update your plans with your manager where the change affects you."]
MGR_ACTIONS = ["Brief your team within two weeks of this circular.", "Apply the new rule consistently and record any exception in the HRMS.",
               "Consult your HRBP before declining a request made under this circular.", "Watch for workload or wellbeing effects and raise them early."]
HR_ACTIONS = ["Payroll and HR Operations configure the HRMS before the effective date.", "HRBPs hold drop-in sessions for questions.",
              "The policy team incorporates the change into the next version of the Global HR Policy Manual.", "Country HR leads report adoption and issues in the monthly HR review."]
FAQ_GENERIC = [
 ("Does this change apply to fixed-term employees and probationers?", "Yes. It applies to all employees of the entities listed above, pro rata for fixed-term and part-time employees, unless the circular says otherwise."),
 ("What if my appointment letter gives me a better benefit?", "Your appointment letter prevails where it is more favourable (Chapter 1.4)."),
 ("Where can I find the updated policy text?", "On the HR intranet and in the HRMS policy library. The next version of the manual will include this change."),
 ("Who do I contact with questions?", "Your HRBP, or the HR helpdesk at hr@bragslabs.com, quoting the circular number."),
 ("Can my manager refuse to apply this change?", "No. Managers apply Company policy consistently; exceptions need HR approval and are recorded in the HRMS."),
 ("Will this affect my performance rating?", "No. Using an entitlement under Company policy never affects performance ratings."),
]

CUSTOM = {
 "HR-CIR-2022-03": ["During red or orange weather alerts issued by the local authority, employees whose roles can be performed remotely work from home for the duration of the alert.",
                    "Facilities will announce office closures by SMS, email and the HRMS app by 6:00 am on the affected day.",
                    "On-site employees whose roles cannot be performed remotely are granted special paid leave if the office is closed.",
                    "Employees must not travel to the office or client sites when public transport is suspended or roads are flooded."],
 "HR-CIR-2023-02": ["BragsLabs Ireland Ltd begins operations from 4 Grand Canal Quay, Dublin 2, with an initial team of 40 employees and a target of 180 by 2026.",
                    "Irish employees will receive 23 days' annual leave, 10 public holidays, 5 days' Company sick pay and an occupational pension with a 5% employer contribution.",
                    "The Irish addendum will be added to the next version of the Global HR Policy Manual."],
 "HR-CIR-2023-05": ["BragsLabs Canada Inc. opens its Toronto office at 330 Bay Street, Suite 1800, with an initial team of 35 employees.",
                    "Canadian employees will receive 3 weeks' vacation, 11 public holidays, 7 paid sick and personal days, extended health and dental benefits and a group RRSP with a 4% match.",
                    "Employment terms follow the Ontario Employment Standards Act; employees in other provinces follow their province's rules."],
 "HR-CIR-2025-01": ["BragsLabs FZ-LLC opens in Dubai Internet City with an initial team of 30 employees and a target of 150.",
                    "UAE employees will receive 30 calendar days' annual leave, mandatory health insurance, end-of-service gratuity and an annual air ticket for L5 and above.",
                    "Employment contracts are registered with the free-zone authority in Arabic and English."],
 "HR-CIR-2025-02": ["BragsLabs Pty Ltd opens its Sydney office at Level 14, 100 Harbour Street, with an initial team of 25 employees and a target of 160.",
                    "Australian employees will receive 4 weeks' annual leave plus 3 Company days between Christmas and New Year, 12 days' personal leave, and superannuation at the guarantee rate.",
                    "The Company paid parental leave of 16 weeks is paid in addition to the government Paid Parental Leave scheme."],
 "HR-CIR-2024-01": ["Managers should not send non-urgent messages outside an employee's working hours, and should use scheduled send where possible.",
                    "Meetings across time zones must rotate so that the same team members are not always meeting late at night.",
                    "No employee will face adverse treatment for not responding outside working hours, except when on-call or during a declared emergency.",
                    "Where local law gives a stronger right to disconnect (for example in Australia, Ireland or Ontario), local law applies."],
 "HR-CIR-2024-03": ["UK employees may make a flexible working request from their first day of employment, up to two requests in any 12 months.",
                    "The Company will respond within 2 months, consult the employee and refuse only on one of the statutory business grounds."],
 "HR-CIR-2024-06": ["All employees will receive at least two simulated phishing emails between August and October.",
                    "Employees who click a simulated link are assigned a 15-minute refresher module; repeated clicks are discussed with the manager.",
                    "Report suspicious emails with the Report Phishing button; real incidents must be reported to security@bragslabs.com within 1 hour."],
 "HR-CIR-2025-09": ["From 1 November 2025, employee transport for late and night shifts in Bengaluru is provided by the new vendor, CityRide Mobility Services.",
                    "Pick-up and drop schedules will be published in the transport app 24 hours in advance; women employees on night shifts continue to receive escorted, GPS-tracked cabs.",
                    "Employees should report delays of more than 15 minutes or unsafe drop points through the app or the Bengaluru transport desk (transport.blr@bragslabs.com)."],
 "HR-CIR-2026-03": ["From 6 April 2026, Statutory Sick Pay is payable in the UK from the first day of sickness absence and the lower earnings limit is removed.",
                    "Paternity leave and unpaid parental leave become day-one rights; 26 weeks' service is still needed for statutory paternity pay, but BragsLabs pays 2 weeks at full pay from day one.",
                    "Company sick pay (10 days at full pay in the first year, 20 days after 2 years) continues to include SSP."],
 "HR-CIR-2026-05": ["Teams must update their team working agreements with three office days, including two anchor days, by 15 April 2026.",
                    "During April 2026, shortfalls of up to two office days in the month will not be followed up, to allow time for transport and care arrangements.",
                    "Employees with caregiving responsibilities, disabilities, pregnancy or long commutes (over 90 minutes each way) may request a temporary exception through the HRBP.",
                    "Desk booking capacity in Bengaluru, Hyderabad, London and Boston is being increased by 15% on anchor days."],
 "HR-CIR-2026-06": ["From 11 May 2026, all expense claims are submitted in the new HRMS expense module; the legacy expense tool becomes read-only.",
                    "Claims submitted in the legacy tool before 8 May 2026 will be processed there; later claims must be resubmitted in the new module.",
                    "Finance will accept claims up to 15 days late during May and June 2026 where the delay was caused by the migration.",
                    "The maximum attachment size is 2 MB until 1 June 2026 and 5 MB afterwards."],
 "HR-CIR-2026-08": ["From 1 July 2026, government Paid Parental Leave in Australia rises to 26 weeks for children born or adopted on or after that date, with 4 weeks reserved for each parent.",
                    "Superannuation is paid by the government on Parental Leave Pay.",
                    "The BragsLabs paid parental leave of 16 weeks (birth parent or primary carer) and 4 weeks (partner) is paid in addition to the government scheme."],
 "HR-CIR-2026-18": ["From 1 January 2027, the annual air ticket to the home country is extended from L5 and above to L4 employees of BragsLabs FZ-LLC.",
                    "Until then, the ticket remains available only to L5 and above, as stated in Chapter 45 of manual version 3.0."],
}

def holiday_list(c, year):
    H = {"US": ["New Year's Day", "Martin Luther King Jr. Day", "Presidents' Day", "Memorial Day", "Juneteenth", "Independence Day", "Labor Day", "Thanksgiving Day", "Day after Thanksgiving", "Christmas Day", "Floating holiday"],
         "IN": ["Republic Day", "Holi", "Ugadi / Gudi Padwa", "May Day", "Independence Day", "Ganesh Chaturthi", "Gandhi Jayanti", "Dussehra", "Diwali", "Christmas"],
         "UK": ["New Year's Day", "Good Friday", "Easter Monday", "Early May bank holiday", "Spring bank holiday", "Summer bank holiday", "Christmas Day", "Boxing Day"],
         "DE": ["Neujahr", "Internationaler Frauentag (Berlin)", "Karfreitag", "Ostermontag", "Tag der Arbeit", "Christi Himmelfahrt", "Pfingstmontag", "Tag der Deutschen Einheit", "1. Weihnachtstag", "2. Weihnachtstag"],
         "NL": ["New Year's Day", "Easter Monday", "King's Day", "Liberation Day", "Ascension Day", "Whit Monday", "Christmas Day", "Boxing Day"],
         "IE": ["New Year's Day", "St Brigid's Day", "St Patrick's Day", "Easter Monday", "May bank holiday", "June bank holiday", "August bank holiday", "October bank holiday", "Christmas Day", "St Stephen's Day"],
         "SG": ["New Year's Day", "Chinese New Year (2 days)", "Hari Raya Puasa", "Good Friday", "Labour Day", "Vesak Day", "Hari Raya Haji", "National Day", "Deepavali", "Christmas Day"],
         "AE": ["New Year's Day", "Eid al-Fitr (3 days)", "Arafat Day", "Eid al-Adha (3 days)", "Islamic New Year", "Prophet's Birthday", "Commemoration Day", "National Day (2 days)"],
         "CA": ["New Year's Day", "Family Day", "Good Friday", "Easter Monday", "Victoria Day", "Canada Day", "Civic Holiday", "Labour Day", "Thanksgiving", "Christmas Day", "Boxing Day"],
         "AU": ["New Year's Day", "Australia Day", "Good Friday", "Easter Saturday", "Easter Monday", "Anzac Day", "King's Birthday", "Labour Day (NSW)", "Christmas Day", "Boxing Day"]}
    return H[c]

def circular_body(cid, issued, eff, countries, topic, attr, old, new, kind):
    cs = COUNTRIES if countries == ["ALL"] else countries
    scope = "all BragsLabs entities worldwide" if countries == ["ALL"] else ", ".join(ENTITY[c] for c in cs)
    signer, title = SIGN["ALL" if countries == ["ALL"] else countries[0]]
    ch = chap_for(attr, countries) if attr else None
    y = D(issued).year
    out = [f"# {cid}: {topic}", "",
           f"| Field | Detail |", "| --- | --- |",
           f"| Circular number | {cid} |", f"| Issued | {fmt(issued)} |", f"| Effective from | {fmt(eff)} |",
           f"| Applies to | {scope} |", f"| Issued by | {signer}, {title} |", f"| Status | {'Announced — not yet in force' if kind=='future' else ('Correction' if kind=='correction' else 'In force from the effective date')} |",
           f"| Policy reference | {'Chapter ' + ch if ch else 'Global HR Policy Manual'} |", ""]
    # 1. summary
    out.append("## 1. Summary")
    if attr and old is not None:
        where = CNAME[cs[0]] if len(cs) == 1 and countries != ["ALL"] else "all countries"
        out.append(f"This circular changes the {SUBJECT.get(attr, attr.replace('_',' '))} for employees in {where}. "
                   f"From {fmt(eff)}, it changes from **{fmt_val(attr, old)}** to **{fmt_val(attr, new)}**.")
    elif attr:
        out.append(f"This circular sets the {topic.lower()} at **{fmt_val(attr, new)}** from {fmt(eff)}.")
    else:
        out.append(f"This circular informs employees of {scope} about: {topic}. It takes effect on {fmt(eff)}.")
    if kind == "future":
        out.append(f"**Until {fmt(eff)}, the current Global HR Policy Manual (version 3.0, effective 1 November 2026) continues to apply unchanged.** This circular is issued early so that employees and managers can plan.")
    if kind == "correction":
        out.append("Chapter 15.1 of manual version 3.0 lists 8 days of paid sick leave for India, which is below the global minimum of 10 working days in Chapter 37.1. Under the global-floor rule in Chapter 1.9, **employees of BragsLabs India Pvt. Ltd. are entitled to 10 paid sick days a year from 1 September 2026**, and the HRMS has been updated. The manual text will be corrected in the next revision.")
    out.append("")
    # 2. background
    out.append("## 2. Background")
    out.append(" ".join([pick(rng, REASONS).format(market=CNAME[cs[0]] if len(cs) == 1 else "global", year=y - 1), pick(rng, REASONS).format(market="local", year=y - 1)]))
    if cid in CUSTOM:
        out.append("")
        out += [f"- {x}" for x in CUSTOM[cid]]
    if "Launch of Global HR Policy Manual" in topic:
        v = {"HR-CIR-2022-01": "v1.0", "HR-CIR-2023-10": "v2.0", "HR-CIR-2026-17": "v3.0"}[cid]
        out.append("")
        out.append(f"Version {v[1:]} covers {len(VERSION_COUNTRIES[v])} countries: {', '.join(CNAME[c] for c in VERSION_COUNTRIES[v])}. The main changes are:")
        prev = {"v1.0": None, "v2.0": "v1.0", "v3.0": "v2.0"}[v]
        if prev:
            for k, vals in GLOBAL.items():
                if vals[prev] != vals[v]:
                    out.append(f"- {k.replace('_inr','').replace('_',' ').capitalize()}: {fmt_val(k, vals[prev])} → {fmt_val(k, vals[v])}")
            for c in VERSION_COUNTRIES[v]:
                if c not in VERSION_COUNTRIES[prev]:
                    out.append(f"- New country addendum: {CNAME[c]} ({ENTITY[c]})")
            for a in ("annual_leave_days", "paid_sick_days", "birth_parent_leave_weeks_full_pay"):
                for c in VERSION_COUNTRIES[prev]:
                    if POLICY[a][c][prev] != POLICY[a][c][v]:
                        out.append(f"- {CNAME[c]}: {ATTR_LABEL[a]} {POLICY[a][c][prev]:g} → {POLICY[a][c][v]:g}")
        else:
            out.append("- First consolidated global manual, replacing separate country handbooks.")
            out.append("- Introduces the four work modes (on-site, hybrid, remote, off-site) and a two-day hybrid office requirement.")
    if "Public holiday calendars" in topic:
        yr = y + 1
        out.append("")
        out.append(f"The {yr} public holiday calendars are below. Remote employees follow the calendar of their base location.")
        for c in cs:
            if (c == "AE" and yr < 2025) or (c == "AU" and yr < 2025) or (c in ("IE", "CA") and yr < 2023):
                continue
            hl = holiday_list(c, yr)
            out.append(f"- **{CNAME[c]}** ({len(hl)} days): {', '.join(hl)}")
    if "benefits enrolment" in topic.lower():
        out.append("")
        out.append(f"The enrolment window runs from {fmt(eff)} to {fmt((D(eff)+timedelta(days=21)).isoformat())}. During the window employees can add or remove dependants, buy voluntary top-up cover, change flexible-benefit choices and update nominations. Outside the window, changes are allowed only for life events such as marriage, birth or adoption, within 30 days of the event.")
    out.append("")
    # 3. what changes
    if attr and old is not None:
        out += ["## 3. What changes", "", "| Item | Before | From " + fmt(eff) + " |", "| --- | --- | --- |"]
        for c in cs[:10]:
            out.append(f"| {CNAME[c] if countries != ['ALL'] else 'All countries'} — {topic.split(' to ')[0].split(' raised')[0]} | {fmt_val(attr, old)} | {fmt_val(attr, new)} |")
            if countries == ["ALL"]: break
        out.append("")
        out.append("## 4. Worked examples")
        if attr == "hybrid_office_days":
            out.append(f"- In a month with 20 working days, a hybrid employee now attends the office on {new*4} days (previously {old*4}).")
            out.append(f"- In a week with one public holiday the requirement reduces pro rata to {new-1} office days.")
            out.append("- An employee on approved leave for a full week has no office-day requirement for that week.")
        elif attr in ("work_from_abroad_days", "remote_cap_pct"):
            out.append(f"- Before {fmt(eff)} the limit was {fmt_val(attr, old)}; from {fmt(eff)} it is {fmt_val(attr, new)}.")
            out.append("- Requests already approved under the old limit remain valid for the approved dates.")
        elif attr.endswith("_days") or "leave" in attr:
            out.append(f"- An employee who joins on 1 July in the year of the change receives the new entitlement pro rata: half of {fmt_val(attr, new)} for that year, rounded to the nearest half day.")
            out.append(f"- An employee who had already planned leave under the old rule keeps the approved dates; any additional entitlement is credited to the balance on the effective date.")
        elif attr.endswith("_inr"):
            out.append(f"- An employee who works 12 nights in the month after the effective date receives 12 × {fmt_val(attr, new).replace(' per night','')} = ₹{indian(12*new)}." if "shift" in attr else f"- An eligible employee receives {fmt_val(attr, new)} instead of {fmt_val(attr, old)} for claims or payments falling on or after the effective date.")
            out.append(f"- Claims or shifts before {fmt(eff)} are paid at {fmt_val(attr, old)}.")
        else:
            out.append(f"- From {fmt(eff)}, the new value of {fmt_val(attr, new)} applies to all eligible employees.")
            out.append(f"- Before {fmt(eff)}, the previous value of {fmt_val(attr, old)} applies.")
        out.append("")
    # transition, actions, faq
    out += ["## 5. Transition rules", ""] + [f"- {x}" for x in rng.sample(TRANSITION, 3)] + [""]
    out += ["## 6. What you need to do", "", "**Employees**", ""] + [f"- {x}" for x in rng.sample(EMP_ACTIONS, 3)] + ["", "**Managers**", ""] + [f"- {x}" for x in rng.sample(MGR_ACTIONS, 3)] + ["", "**HR and Payroll**", ""] + [f"- {x}" for x in rng.sample(HR_ACTIONS, 3)] + [""]
    for title, items in EXTRA_SECTIONS:
        out += [f"## {title}", ""] + [f"- {x}" for x in rng.sample(items, min(3, len(items)))] + [""]
    out += ["## 7. Frequently asked questions", ""]
    for q, a in rng.sample(FAQ_GENERIC, 6):
        out += [f"**{q}**", "", a, ""]
    if kind == "future":
        out += [f"**Does the new value apply now?**", "", f"No. It applies only from {fmt(eff)}. Until then, use the value in the current manual.", ""]
    out += ["## 8. Relationship to the Global HR Policy Manual", ""]
    cur = "v1.0" if D(issued) < D("2024-01-01") else ("v2.0" if D(issued) < D("2026-11-01") else "v3.0")
    nxt = {"v1.0": "2.0", "v2.0": "3.0", "v3.0": "4.0"}[cur]
    if kind == "future":
        out.append(f"This circular announces a change to manual version 3.0 that takes effect on {fmt(eff)}. It will be incorporated into version 4.0.")
    elif kind == "correction":
        out.append("This circular corrects an inconsistency in manual version 3.0 and prevails over Chapter 15.1 until the text is corrected.")
    else:
        out.append(f"This circular amends manual version {cur[1:]} from the effective date and will be incorporated into version {nxt}. Where this circular and the manual differ, this circular prevails from its effective date.")
    out += ["", "## 9. Contacts", "", f"- HR helpdesk: hr@{DOMAIN}", f"- Policy owner: {signer}, {title}"]
    for c in cs[:3]:
        out.append(f"- {CNAME[c]} HR lead: {HR_LEAD[c]}")
    return "\n".join(out)

def build_circulars():
    for (cid, issued, eff, countries, topic, attr, old, new, kind) in CIRCULARS:
        body = circular_body(cid, issued, eff, countries, topic, attr, old, new, kind)
        write_doc(f"circulars/{cid}.md", {"doc_id": cid, "doc_type": "hr_circular", "company": COMPANY, "title": topic, "issued": issued, "effective_date": eff,
                  "country": countries[0] if len(countries) == 1 else countries, "circular_kind": kind, "status": "announced" if kind == "future" else "in force"}, body)


# ---------------------------------------------------------------- add-on sections (volume and detail)
ROOM_NAMES = ["Turing", "Lovelace", "Hopper", "Noether", "Ramanujan", "Shannon", "Bayes", "Gauss", "Fisher", "Tukey", "Knuth", "Codd", "Hinton", "Curie", "Raman", "Bose", "Kalam", "Euler"]
def handbook_extra(code, city, c, floors, hc, parking):
    r = random.Random(code)
    out = ["## Floor directory", "", "| Floor | Teams | Desks | Bookable desks | Meeting rooms |", "| --- | --- | --- | --- | --- |"]
    teams = ["Data Engineering", "Machine Learning", "Analytics Consulting", "Platform Engineering", "Client Delivery", "Product Management", "Cloud Operations", "Quality Engineering", "Finance", "People & HR", "Sales", "Design", "Facilities and IT"]
    per = max(40, hc // max(1, floors))
    for f in range(1, floors + 1):
        d = int(per * 0.7); b = int(d * 0.75)
        out.append(f"| {f} | {', '.join(r.sample(teams, 3))} | {d} | {b} | {r.randint(4, 12)} |")
    out += ["", "## Meeting rooms", "", "| Room | Floor | Seats | Video conferencing | Notes |", "| --- | --- | --- | --- | --- |"]
    for nm in r.sample(ROOM_NAMES, min(12, 4 + floors)):
        out.append(f"| {nm} | {r.randint(1, floors)} | {r.choice([4, 6, 8, 10, 12, 16, 24])} | {r.choice(['Yes', 'Yes', 'Yes', 'No'])} | {r.choice(['Whiteboard wall', 'Client-facing', 'Quiet room nearby', 'Hybrid-meeting kit', 'Wheelchair accessible', 'Projector'])} |")
    out += ["", "Book rooms in the calendar; release a booking if plans change. Rooms not checked in within 10 minutes are released automatically.", ""]
    if c == "IN":
        out += ["## Shuttle routes (general shift)", "", "| Route | Areas covered | Morning pick-up starts | Evening departure |", "| --- | --- | --- | --- |"]
        areas = {"BLR": ["Whitefield", "Marathahalli", "HSR Layout", "Electronic City", "Hebbal", "Banashankari", "Indiranagar", "Yelahanka"],
                 "HYD": ["Kukatpally", "Gachibowli", "Secunderabad", "LB Nagar", "Miyapur", "Kondapur"],
                 "PNQ": ["Hinjewadi", "Viman Nagar", "Hadapsar", "Wakad", "Baner"], "MAA": ["Velachery", "Tambaram", "Anna Nagar", "Porur"]}[code]
        for i, a in enumerate(areas):
            out.append(f"| R{i+1:02d} | {a} and nearby | {r.choice(['7:10 am', '7:25 am', '7:40 am', '7:55 am'])} | {r.choice(['6:40 pm', '6:50 pm', '7:05 pm'])} |")
        out += ["", "Shuttle seats are booked in the transport app by 9:00 pm the previous day. Unused bookings three times in a month suspend booking for a week.", ""]
    out += ["## Lockers, printing and stationery", "", f"Lockers are available on every floor ({r.randint(60, 300)} in total); request one through the facilities app. Printing uses secure release: send the job, then tap your ID card at any printer. Confidential documents must not be left on printers. Basic stationery is in the supply room on floor {r.randint(1, floors)}.", "",
            "## Office events calendar 2026", "", "| Month | Event |", "| --- | --- |"]
    ev = ["New year town hall", "Women in Data panel", "Hackathon", "Wellbeing week", "Family day", "Pride month talk", "Hybrid team-agreement workshops", "Volunteering day", "Benefits fair", "Festive celebrations", "Long-service awards", "Year-end party"]
    for m, e in zip(["January", "March", "April", "May", "June", "June", "April", "August", "October", "November", "September", "December"], ev):
        out.append(f"| {m} | {e} |")
    out += ["", "## Nearby amenities", ""] + [f"- {x}" for x in r.sample(["A pharmacy two minutes' walk from the main entrance.", "Several cafés and restaurants within 500 metres.", "An ATM in the building lobby.", "A park suitable for walking meetings.", "A partner gym offering corporate rates.", "A post office for personal parcels.", "A clinic offering walk-in consultations.", "EV charging points in the basement car park."], 5)] + [""]
    out += ["## Office FAQ", ""]
    for q, a in [("Can I bring a guest for lunch?", "Yes, register them as a visitor; guests are escorted and pay for meals."),
                 ("What if I feel unwell at work?", "Contact a first-aider or reception; the wellness room is available and reception can arrange transport home."),
                 ("Where do I collect deliveries?", "Personal deliveries are not accepted at reception; business parcels are logged by the mailroom."),
                 ("Can I work late?", "Yes; inform security if you will stay after 9:00 pm, and use Company transport where applicable."),
                 ("How do I report a facilities issue?", "Raise a ticket in the facilities app; urgent issues go to reception.")]:
        out += [f"**{q}** {a}", ""]
    return out

def benefits_extra(c, al_override=None):
    r = random.Random("ben" + c)
    cur = CURRENCY[c]
    out = ["## Schedule of medical benefits", "", "| Benefit | Limit / rule | Co-pay |", "| --- | --- | --- |"]
    items = ["Hospital room", "Intensive care", "Surgeon and anaesthetist fees", "Diagnostic tests", "Day-care procedures", "Pre-hospitalisation (30 days)", "Post-hospitalisation (60 days)",
             "Ambulance", "Maternity – normal delivery", "Maternity – caesarean", "Newborn cover", "Vaccinations for newborn", "Mental health inpatient", "Mental health outpatient", "Physiotherapy",
             "AYUSH / alternative treatment", "Cataract surgery", "Organ donor expenses", "Home care treatment", "Second medical opinion", "Dental emergency", "Spectacles", "Annual health check-up", "Telemedicine"]
    for it in items:
        lim = r.choice(["Covered in full", "Up to the sum insured", f"Up to {money(c, r.choice([500, 1000, 2500, 5000]) * (80 if cur == 'INR' else 1))} a year", "Up to 20 sessions a year", "Once a year", "Network providers only"])
        out.append(f"| {it} | {lim} | {r.choice(['None', 'None', '10%', '20% outside network'])} |")
    pct = POLICY["employer_retirement_contribution_pct"][c]["v3.0"]
    out += ["", "## Retirement contribution examples", "", "| Annual base salary | Employee contribution | Employer contribution |", "| --- | --- | --- |"]
    for sal in ([600000, 1200000, 2400000] if cur == "INR" else [40000, 75000, 120000]):
        out.append(f"| {money(c, sal)} | {money(c, int(sal * 0.05))} | {money(c, int(sal * pct / 100))} |" if c != "AE" else f"| {money(c, sal)} | — | Gratuity accrues at 21 days' basic pay per year |")
    out += ["", "## Leave entitlements summary", "", "| Leave | Entitlement | Notes |", "| --- | --- | --- |"]
    v = {a: POLICY[a][c]["v3.0"] for a in POLICY}
    if al_override: v['annual_leave_days'] = al_override
    for lt, ent, note in [("Annual leave", f"{v['annual_leave_days']} working days", "Accrues monthly; carry-forward as per addendum"),
                          ("Sick leave", f"{v['paid_sick_days']} days at full pay" if c != "NL" else "100% year 1, 70% year 2", "Medical certificate rules per addendum"),
                          ("Birth-parent leave", f"{v['birth_parent_leave_weeks_full_pay']} weeks at full pay", "Company tops up statutory pay"),
                          ("Partner leave", f"{v['partner_leave_weeks_full_pay']:g} weeks at full pay", "Within 6 months of birth or adoption"),
                          ("Bereavement", "5 working days (immediate family)", "Global minimum"), ("Caregiver leave", "5 working days", "Global minimum"),
                          ("Domestic violence leave", "10 working days", "Confidential"), ("Public holidays", f"{v['public_holidays']} days", "Office calendar")]:
        out.append(f"| {lt} | {ent} | {note} |")
    out += ["", "## Network providers (selection)", ""]
    for i in range(8):
        out.append(f"- {r.choice(['City', 'Metro', 'Harbour', 'Lakeside', 'Sunrise', 'Greenfield', 'Unity', 'Riverbank'])} {r.choice(['Hospital', 'Medical Centre', 'Clinic', 'Diagnostics', 'Specialty Hospital'])} — {r.choice(['cashless', 'cashless', 'reimbursement only'])}, {r.randint(1, 25)} km from the nearest office")
    out += ["", "## Claim examples", ""]
    for i in range(4):
        amt = r.choice([1200, 3400, 8800, 15000]) * (60 if cur == "INR" else 1)
        out.append(f"- An employee was admitted for {r.choice(['appendix surgery', 'a fracture', 'dengue fever', 'a planned knee procedure'])}; the bill of {money(c, amt)} was settled {r.choice(['cashless at discharge', 'by reimbursement within 12 working days'])}, with {r.choice(['no co-pay', 'a 10% co-pay for non-network charges'])}.")
    out += ["", "## Dependants", "", "You may cover your spouse or partner (including same-sex and unmarried partners), children up to age 25, and, where the plan allows, parents or parents-in-law. Add dependants within 30 days of a life event; proof of relationship may be requested.", ""]
    return out

# ---------------------------------------------------------------- FAQs
def sections(path):
    t = open(path, encoding="utf-8").read().split("---\n", 2)[2]
    secs = re.split(r"(?m)^### ", t)[1:]
    out = []
    for s in secs:
        title, _, body = s.partition("\n")
        out.append((title.strip(), body.strip()))
    return out

def youify(text):
    reps = [("The Company", "BragsLabs"), ("the Company", "BragsLabs"), ("Employees must", "You must"), ("employees must", "you must"),
            ("Employees may", "You may"), ("employees may", "you may"), ("An employee", "You"), ("the employee's", "your"), ("The employee", "You")]
    for a, b in reps: text = text.replace(a, b)
    return text

def condense(body, n=4):
    lines = [l for l in body.split("\n") if l.strip()]
    keep, words = [], 0
    for l in lines:
        keep.append(l); words += len(l.split())
        if words > 400: break
    out = []
    for i, l in enumerate(keep):
        if i and not (l.startswith("|") and keep[i-1].startswith("|")) and not (l.lstrip().startswith(("-", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")) and keep[i-1].lstrip().startswith(("-", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8."))):
            out.append("")
        out.append(l)
    return "\n".join(out)

FAQ_TOPICS = {
 "FAQ-WORK-MODES": ("Work modes", [2]), "FAQ-HYBRID": ("Hybrid working", [9]), "FAQ-REMOTE": ("Remote working", [10]),
 "FAQ-OFFSITE": ("Client sites, field work and assignments", [11]), "FAQ-HOURS-SHIFTS": ("Working hours and shifts", [12]),
 "FAQ-ATTENDANCE": ("Attendance and timesheets", [13]), "FAQ-HOME-OFFICE": ("Home office and allowances", [14]), "FAQ-LEAVE": ("Leave", [15]),
 "FAQ-FAMILY": ("Holidays and family leave", [16]), "FAQ-PAY": ("Pay and payroll", [17]), "FAQ-BENEFITS": ("Insurance and wellbeing", [19]),
 "FAQ-TRAVEL": ("Travel and relocation", [20]), "FAQ-EXPENSES": ("Expenses", [21]), "FAQ-PERFORMANCE": ("Performance and promotions", [22, 23]),
 "FAQ-LEARNING": ("Learning and recognition", [24, 25]), "FAQ-CONDUCT": ("Conduct, gifts and outside work", [26, 27]),
 "FAQ-RESPECT": ("Harassment, grievances and whistleblowing", [28, 29]), "FAQ-SECURITY": ("IT security and privacy", [30, 31]),
 "FAQ-SEPARATION": ("Discipline, resignation and exit", [33, 34]), "FAQ-MOBILITY": ("Working across countries", [36]),
}
QSTEMS = ["What does the policy say about {t}?", "How does {t} work at BragsLabs?", "Can you explain the rules on {t}?", "What should I know about {t}?", "Where can I find guidance on {t}?"]

def chapter_path(version, no):
    return glob.glob(f"{CORPUS}/policy/{version}/ch{no:02d}_*.md")[0]

def build_faqs():
    reviewed = {}
    for fid, (topic, chs) in FAQ_TOPICS.items():
        rev = "2025-11-30" if fid == "FAQ-HYBRID" else pick(rng, ["2026-09-15", "2026-10-06", "2026-10-20", "2026-11-03"])
        reviewed[fid] = rev
        out = [f"# Employee FAQ: {topic}", "", f"*Maintained by the HR Policy Office. Last reviewed {fmt(rev)}. If this FAQ and the Global HR Policy Manual differ, the manual and any later HR circular prevail.*", ""]
        n = 0
        for ch in chs:
            for title, body in sections(chapter_path("v3.0", ch)):
                tclean = re.sub(r"^\d+\.\d+\s+", "", title)
                q = pick(rng, QSTEMS).format(t=tclean[0].lower() + tclean[1:])
                ans = youify(condense(body))
                if fid == "FAQ-HYBRID":
                    ans = ans.replace("**3 days a week**", "**2 days a week**").replace("| 3 days a week, averaged over each calendar month (12 days", "| 2 days a week, averaged over each calendar month (8 days")
                n += 1
                out += [f"## Q{n}. {q}", "", ans, "", f"*Policy reference: Section {title.split(' ')[0]}.*", ""]
        # country notes
        out += ["## Country notes", ""]
        for c in COUNTRIES:
            out.append(f"- **{CNAME[c]}:** {pick(rng, ['Local rules are in the', 'See also the', 'Check the'])} {CNAME[c]} addendum (Chapter {ADD_CH[c]}); HR lead {HR_LEAD[c]}.")
        write_doc(f"faqs/{fid.lower()}.md", {"doc_id": fid, "doc_type": "faq", "company": COMPANY, "title": f"Employee FAQ: {topic}", "country": "GLOBAL",
                  "last_reviewed": rev, "based_on_version": "2.0" if fid == "FAQ-HYBRID" else "3.0"}, "\n".join(out))
    # country FAQs
    for c in COUNTRIES:
        fid = f"FAQ-{c}-COUNTRY"
        rev = pick(rng, ["2026-08-18", "2026-09-29", "2026-10-13"])
        out = [f"# Employee FAQ: working at BragsLabs in {CNAME[c]}", "", f"*For employees of {ENTITY[c]}. Last reviewed {fmt(rev)}. The {CNAME[c]} addendum (Chapter {ADD_CH[c]} of manual version 3.0) prevails if this FAQ differs.*", ""]
        n = 0
        for attr, label in ATTR_LABEL.items():
            v = POLICY[attr][c]["v3.0"]
            if c == "IN" and attr == "partner_leave_weeks_full_pay":
                ans = "Partners receive **7 working days** of paid paternity leave, to be taken within 6 months of the birth or adoption."   # stale (CF-06)
            else:
                ans = f"Under manual version 3.0, employees of {ENTITY[c]} receive **{v:g}** — {label}. {pick(rng, ['This is a Company entitlement and may be more generous than local law.', 'Where local law gives more, local law applies.', 'Part-time employees receive a pro-rata amount.'])}"
            n += 1
            out += [f"## Q{n}. What is my {label.split(' (')[0]}?", "", ans, ""]
        for title, body in sections(chapter_path("v3.0", ADD_CH[c])):
            tclean = re.sub(r"^\d+\.\d+\s+", "", title)
            if "at a glance" in tclean: continue
            n += 1
            ans = youify(condense(body, 5))
            if c == "IN": ans = ans.replace("paternity leave (10 working days)", "paternity leave (7 working days)")
            out += [f"## Q{n}. {pick(rng, QSTEMS).format(t=tclean[0].lower()+tclean[1:])}", "", ans, ""]
        offs = OFFICE_BY_COUNTRY[c]
        n += 1
        out += [f"## Q{n}. Where are the BragsLabs offices in {CNAME[c]}?", "", "; ".join(f"{o[1]} ({o[9]}), opened {o[3]}, about {o[4]} employees" for o in offs) + ".", ""]
        n += 1
        out += [f"## Q{n}. Who is my country HR lead?", "", f"{HR_LEAD[c]}. You can also use the HR helpdesk at hr@{DOMAIN}.", ""]
        fname = f"faqs/faq_{c.lower()}_country.md"
        write_doc(fname, {"doc_id": f"FAQ-{c}-COUNTRY" if c != "IN" else "FAQ-IN-COUNTRY", "doc_type": "faq", "company": COMPANY, "title": f"Employee FAQ: {CNAME[c]}",
                  "country": c, "last_reviewed": rev, "based_on_version": "3.0"}, "\n".join(out))

# ---------------------------------------------------------------- Office handbooks
def build_handbooks():
    for code, city, c, opened, hc, floors, parking, gym, creche, addr in OFFICES:
        stale_al = 23 if code == "LON" else POLICY["annual_leave_days"][c]["v3.0"]
        rev = "2025-03-14" if code in ("LON", "PNQ") else pick(rng, ["2026-06-30", "2026-08-31", "2026-10-15"])
        fw = max(2, floors * 2)
        out = [f"# {city} office handbook", "", f"*{ENTITY[c]} · {addr} · last reviewed {fmt(rev)}.*", "",
               "## Welcome", "", f"Welcome to the BragsLabs {city} office. The office opened in {opened} and is home to about {hc} employees across {floors} floor{'s' if floors>1 else ''}. "
               f"It serves teams in {', '.join(rng.sample(['Data Engineering','Machine Learning','Analytics Consulting','Platform Engineering','Client Delivery','Product Management','Cloud Operations','Finance','People & HR'], 4))}. This handbook covers practical information for working here; HR policies are in the Global HR Policy Manual.", "",
               "## Office at a glance", "", "| Item | Detail |", "| --- | --- |",
               f"| Address | {addr} |", f"| Opened | {opened} |", f"| Employees (approx.) | {hc} |", f"| Floors | {floors} |", f"| Parking spaces | {parking} |",
               f"| Gym | {'Yes, on site' if gym else 'No; discounted membership at a nearby gym'} |", f"| Crèche | {'Yes, on site or partner crèche within 1 km' if creche else 'No; childcare allowance available'} |",
               f"| Trained fire wardens | {fw} |", f"| Country HR lead | {HR_LEAD[c]} |", f"| Office manager | {pick(rng, ['Priyanka Das','Noah Miller','Grace Okafor','Lukas Schmidt','Emma de Jong','Sean Byrne','Wei Jie Lim','Hassan Ali','Sophie Martin','Ella Wilson'])} |", "",
               "## Opening hours and access", "", f"The office is open from 7:00 am to 11:00 pm on working days; 24x7 support teams have access around the clock. Security is staffed at reception at all times. Wear your ID card visibly, never tailgate, and report a lost card within 2 hours; a replacement fee of {money(c, {'INR':300}.get(CURRENCY[c], 10))} applies after the first loss.", "",
               "## Hybrid working in this office", "", f"Hybrid employees attend the office {GLOBAL['hybrid_office_days']['v3.0'] if rev >= '2026-04-01' else 2} days a week, including their team's anchor days. Book desks in the desk-booking app at least one working day ahead; bookings not checked in by 11:00 am are released. "
               f"Team neighbourhoods are allocated on {pick(rng, ['the north side of each floor','floors 2 and 3','the east wing'])}. Quiet zones are marked in green; phone booths are available on every floor.", "",
               "## Leave reminders for this office", "", f"Employees based here receive {stale_al} days of paid annual leave under Company policy and {POLICY['public_holidays'][c]['v3.0']} public holidays.", ""]
        if c == "IN":
            night = 500 if code == "PNQ" else 600
            out += ["## Shifts and transport", "", f"Late and night shifts receive door-to-door cabs booked through the transport app. The night shift allowance is ₹{night} per night worked. Women employees on shifts ending after 8:00 pm receive escorted, GPS-tracked cabs and a check-in call after drop-off. "
                    f"Shuttles run on {rng.randint(6,14)} fixed routes for the general shift, leaving the office at 6:45 pm and 7:30 pm.", ""]
        else:
            out += ["## Getting here", "", f"The office is a {rng.randint(3,12)}-minute walk from the nearest {pick(rng, ['metro','train','tram','bus'])} station. Cycle parking and showers are available. Parking is allocated by Admin, with priority for persons with disabilities, pregnant employees and late-shift staff.", ""]
        out += ["## Food and facilities", "", f"The {pick(rng, ['cafeteria','kitchen and café','canteen'])} serves breakfast from 8:00 to 10:00 am and lunch from 12:30 to 2:30 pm. Meals are subsidised on office days. Wellness rooms can be booked in 30-minute slots for rest, nursing or medical needs.",
                "", f"{'The on-site gym is open from 6:00 am to 10:00 pm; book through the facilities app.' if gym else 'There is no gym on site; employees get a corporate discount at a partner gym nearby.'} {'The crèche takes children from 6 months to 6 years; places are allocated by date of request.' if creche else 'Parents may claim the childcare allowance described in Chapter 16.9.'}", "",
                "## IT support", "", f"The IT service desk is on floor {rng.randint(1, floors)} and open from 8:30 am to 7:00 pm. Report lost or stolen devices within 2 hours to security@{DOMAIN}. Guest Wi-Fi is available; Company devices must use the corporate network or VPN.", "",
                "## Health, safety and emergencies", "", f"There are {fw} trained fire wardens and at least one first-aider on every floor. Fire drills take place every 6 months. The assembly point is {pick(rng, ['the front car park','the plaza opposite the main entrance','the open ground behind the building'])}. "
                f"The nearest hospital is {pick(rng, ['CityCare Hospital','Sunrise Multispecialty Hospital','St. Brendan\'s Clinic','Harbourview Medical Centre','Lakeside General'])}, about {rng.randint(2,9)} km away. In an emergency call the local emergency number and then the Company emergency helpline (+1 617 555 0100).", "",
                "## Visitors and accessibility", "", "Register visitors in the visitor system one working day ahead; visitors are escorted at all times and may not enter secure areas without approval. The office has step-free access, accessible washrooms on every floor and lifts with audio and Braille.", "",
                "## Local holidays", "", ", ".join(holiday_list(c, 2026)) + ".", "",
                "## Community and sustainability", "", f"Employee resource groups meet monthly in this office. The office runs a {pick(rng, ['zero single-use plastic','paperless printing','e-waste collection'])} programme, and a green team organises volunteering days twice a year.", ""]
        out += handbook_extra(code, city, c, floors, hc, parking)
        write_doc(f"handbooks/{code.lower()}_{city.lower()}_office_handbook.md", {"doc_id": f"HB-{code}", "doc_type": "office_handbook", "company": COMPANY, "title": f"{city} office handbook",
                  "country": c, "office": city, "last_reviewed": rev}, "\n".join(out))

# ---------------------------------------------------------------- Benefits summaries
INSURER = {"US": "Northstar Health Plans", "IN": "Bharat Assure General Insurance", "UK": "Albion Private Health", "DE": "Rhein Krankenversicherung AG",
           "NL": "Delta Zorgverzekering", "IE": "Liffey Health Insurance DAC", "SG": "Lion City Assurance", "AE": "Gulf Shield Insurance",
           "CA": "Maple Benefits Mutual", "AU": "Southern Cross Health Fund"}
SUM_INSURED = {"US": "USD 2,000,000 lifetime maximum", "IN": "₹5,00,000 per family per year (floater)", "UK": "Comprehensive cover, no annual limit", "DE": "Supplementary cover up to €10,000 a year",
               "NL": "Supplementary cover up to €3,500 a year", "IE": "€1,000,000 a year", "SG": "SGD 150,000 a year", "AE": "AED 750,000 a year", "CA": "CAD 1,000,000 lifetime", "AU": "Top hospital cover"}
EAP = "BrightPath Employee Assistance"

def build_benefits():
    for c in COUNTRIES:
        al = 16 if c == "SG" else POLICY["annual_leave_days"][c]["v3.0"]
        v = {a: POLICY[a][c]["v3.0"] for a in POLICY}
        out = [f"# Benefits summary {2026}: {CNAME[c]}", "", f"*For employees of {ENTITY[c]}. Plan year 1 January – 31 December 2026. Last updated {fmt('2026-02-10' if c=='SG' else '2026-10-01')}. This summary does not replace the plan documents or the Global HR Policy Manual.*", "",
               "## Your benefits at a glance", "", "| Benefit | What you get |", "| --- | --- |",
               f"| Medical insurance | {INSURER[c]}; {SUM_INSURED[c]} |", f"| Life cover | {v['life_cover_multiple']:g}× annual base salary |",
               f"| Accident cover | {max(2, v['life_cover_multiple']):g}× annual base salary |", f"| Retirement | {'Employer contribution ' + str(v['employer_retirement_contribution_pct']) + '%' if c!='AE' else 'End-of-service gratuity (21 days per year for the first 5 years, 30 days after)'} |",
               f"| Annual leave | {al} working days |", f"| Paid sick leave | {v['paid_sick_days'] if c!='NL' else '100% of salary in year 1, 70% in year 2'} |",
               f"| Birth-parent leave | {v['birth_parent_leave_weeks_full_pay']} weeks at full pay |", f"| Partner leave | {v['partner_leave_weeks_full_pay']:g} weeks at full pay |",
               f"| Public holidays | {v['public_holidays']} |", f"| Employee Assistance Programme | {EAP}, 24x7, free and confidential |", ""]
        sections_txt = [
         ("Medical insurance", f"Medical cover is provided by {INSURER[c]}. It covers the employee from day one, with no waiting period for pre-existing conditions. You can cover your spouse or partner and children; {'parents or parents-in-law may also be covered, with the premium shared 50:50' if c=='IN' else 'dependants are covered at the Company rate set out in the plan'}. "
          f"Cashless treatment is available at network hospitals and clinics. Mental health, maternity, day-care procedures and gender affirmation treatment are covered as per the plan terms. Claims for non-network treatment must be submitted within 30 days of discharge with itemised bills, prescriptions and discharge summaries."),
         ("Dental and vision", f"{'Dental and vision plans are offered with the Company paying 90% of the employee premium and 70% for dependants.' if c=='US' else 'Routine dental check-ups and an annual eye test are covered up to the plan limits; spectacles are reimbursed once every two years.'} Orthodontic treatment for children is covered at 50%."),
         ("Life and accident cover", f"Life cover of {v['life_cover_multiple']:g}× annual base salary is paid to your nominees if you die during employment, from any cause, anywhere in the world. Accident cover pays for accidental death and permanent disability, with weekly compensation for temporary disability. Keep your nominations up to date in the HRMS."),
         ("Retirement", f"{'Your employer contributes ' + str(v['employer_retirement_contribution_pct']) + '% of eligible pay to the Company retirement plan. ' if c!='AE' else 'Expatriate employees receive end-of-service gratuity instead of a pension; UAE nationals are enrolled in GPSSA. '}"
          f"{ {'US':'The 401(k) match vests immediately.','IN':'Employee and employer each contribute 12% of wages to EPF; gratuity is payable after 5 years of service.','UK':'You are auto-enrolled into the Company scheme; salary sacrifice is available.','DE':'The Company subsidises deferred compensation in the company pension (bAV).','NL':'The Company operates a defined-contribution pension scheme.','IE':'Employees not in the Company scheme are enrolled in the State auto-enrolment system.','SG':'CPF contributions follow the statutory rates for your age band.','AE':'Gratuity is paid within 14 days of the last working day.','CA':'The group RRSP match is up to 5% of base salary.','AU':'Superannuation is paid at the guarantee rate of 12% to your chosen fund.'}[c] }"),
         ("Leave", f"You receive {al} working days of paid annual leave, {v['public_holidays']} public holidays, paid sick leave and family leave as set out in the {CNAME[c]} addendum. Birth parents receive {v['birth_parent_leave_weeks_full_pay']} weeks at full pay and partners {v['partner_leave_weeks_full_pay']:g} weeks at full pay, in addition to any statutory scheme."),
         ("Wellbeing", f"{EAP} offers up to 8 counselling sessions per issue a year for you and your family, by phone, chat, video or in person. You can also claim a wellbeing allowance for gym, yoga, sports or wellness apps, and join monthly wellbeing sessions. Employees aged 30 and above receive a free annual health check-up."),
         ("Enrolment and changes", "You are enrolled automatically on joining. Each year there is an enrolment window in October when you can add or remove dependants, buy voluntary top-up cover and change flexible-benefit choices. Outside the window, changes are allowed only for life events, within 30 days."),
         ("How to make a claim", "1. Check whether the provider is in the network. 2. For cashless treatment, show your insurance card and ID. 3. For reimbursement, upload itemised bills, prescriptions and reports in the insurer's app within 30 days. 4. Track the claim in the app; contact the benefits helpdesk if it takes more than 15 working days."),
         ("Leaving BragsLabs", "Medical cover ends on your last working day unless local law provides continuation (for example COBRA in the US). Life cover ends on the last working day. Retirement savings remain yours under the plan rules."),
        ]
        for title, txt in sections_txt:
            out += [f"## {title}", "", txt, ""]
        out += ["## Frequently asked questions", ""]
        qa = [("Can I add my newborn to the plan?", "Yes. Add the child in the HRMS within 30 days of birth; cover starts from the date of birth."),
              ("Is mental health covered?", "Yes, both inpatient and outpatient mental health treatment are covered as per the plan, and the EAP is free."),
              ("Does cover continue during unpaid leave?", "Medical cover continues during approved unpaid leave only if you pay the premium for that period."),
              ("Are fertility treatments covered?", "Consultations are covered; treatment cover depends on the plan. You may take up to 5 days of paid leave a year for appointments."),
              ("Who do I contact about benefits?", f"The benefits helpdesk via hr@{DOMAIN}, or your HR lead {HR_LEAD[c]}.")]
        for q, a in qa:
            out += [f"**{q}**", "", a, ""]
        for i in range(6):
            out += [f"## Plan detail {i+1}: {pick(rng, ['room rent and hospital class','pre- and post-hospitalisation','day-care procedures','maternity benefits','newborn cover','ambulance and evacuation','second medical opinion','alternative treatments','chronic disease management','international emergency cover'])}", "",
                    pick(rng, ["Covered in full up to the plan limit, subject to the treating doctor's advice and the insurer's reasonable and customary charges.",
                               "Covered for 30 days before and 60 days after hospitalisation, for expenses related to the same condition.",
                               "Covered when the procedure is listed in the insurer's schedule; no minimum hospital stay is required.",
                               "Covered from day one with no waiting period; claims need the discharge summary and itemised bills.",
                               "Emergency treatment outside the country of employment is covered during business travel; leisure travel needs separate travel insurance."]) + " " +
                    pick(rng, ["Pre-authorisation is required for planned treatment.", "Co-payment does not apply.", "A deductible applies as set out in the plan document.", "Network providers bill the insurer directly."]), ""]
        out = out[:out.index("## Frequently asked questions")] + benefits_extra(c, al) + out[out.index("## Frequently asked questions"):]
        write_doc(f"benefits/benefits_summary_2026_{c.lower()}.md", {"doc_id": f"BEN-{c}", "doc_type": "benefits_summary", "company": COMPANY, "title": f"Benefits summary 2026: {CNAME[c]}",
                  "country": c, "plan_year": 2026, "last_updated": "2026-02-10" if c == "SG" else "2026-10-01"}, "\n".join(out))

# ---------------------------------------------------------------- Change log and annual reports
def build_reports():
    out = ["# Global HR Policy Manual — change log, version 1.0 to version 3.0", "", "*Prepared by the HR Policy Office for auditors, HR business partners and employee representatives. It records every value that changed between manual versions and the circular that introduced it.*", "",
           "## Versions", "", "| Version | Effective | Countries | Chapters |", "| --- | --- | --- | --- |"]
    for v in ["v1.0", "v2.0", "v3.0"]:
        out.append(f"| {v[1:]} | {fmt(VERSION_DATE[v])} | {len(VERSION_COUNTRIES[v])}: {', '.join(VERSION_COUNTRIES[v])} | {35 + (0 if v=='v1.0' else 2) + len(VERSION_COUNTRIES[v])} |")
    out += ["", "## Global values", "", "| Item | v1.0 | v2.0 | v3.0 |", "| --- | --- | --- | --- |"]
    for k, vals in GLOBAL.items():
        out.append(f"| {k.replace('_',' ')} | {fmt_val(k, vals['v1.0'])} | {fmt_val(k, vals['v2.0'])} | {fmt_val(k, vals['v3.0'])} |")
    for a, label in ATTR_LABEL.items():
        out += ["", f"## {label[0].upper()+label[1:]}", "", "| Country | v1.0 | v2.0 | v3.0 |", "| --- | --- | --- | --- |"]
        for c in COUNTRIES:
            vv = POLICY[a][c]
            out.append(f"| {CNAME[c]} | {vv.get('v1.0', 'not covered')} | {vv.get('v2.0', 'not covered')} | {vv.get('v3.0')} |")
        out.append("")
        out.append(f"Narrative: " + " ".join(f"In {CNAME[c]}, the value moved from {vv.get('v1.0', vv.get('v2.0'))} to {vv['v3.0']}." for c in COUNTRIES for vv in [POLICY[a][c]] if len(set(vv.values())) > 1) or "No changes.")
    out += ["", "## Circulars that changed policy values", "", "| Circular | Issued | Effective | Scope | Change |", "| --- | --- | --- | --- | --- |"]
    for (cid, issued, eff, countries, topic, attr, old, new, kind) in CIRCULARS:
        if attr and kind in ("change", "interim", "future", "correction"):
            out.append(f"| {cid} | {issued} | {eff} | {', '.join(countries)} | {topic}: {fmt_val(attr, old)} → {fmt_val(attr, new)} ({kind}) |")
    import difflib
    out += ["", "## Chapter-by-chapter changes (v2.0 → v3.0)", ""]
    for p3 in sorted(glob.glob(f"{CORPUS}/policy/v3.0/ch*.md")):
        no = int(os.path.basename(p3)[2:4])
        if no > 37: continue
        p2s = glob.glob(f"{CORPUS}/policy/v2.0/ch{no:02d}_*.md")
        if not p2s: continue
        a = open(p2s[0]).read().split("---\n", 2)[2].splitlines(); b = open(p3).read().split("---\n", 2)[2].splitlines()
        diff = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if l[:1] in "+-" and not l.startswith(("+++", "---")) and "version" not in l.lower()]
        if not diff: continue
        title = b[2].lstrip("# ") if len(b) > 2 else f"Chapter {no}"
        out += [f"### {title}", ""]
        for l in diff[:16]:
            out.append(("- Removed: " if l[0] == "-" else "- Added: ") + l[1:].strip()[:400])
        out.append("")
    out += ["", "## Known inconsistencies and how they are resolved", ""]
    for cf in CONFLICTS:
        out.append(f"- **{cf['id']} ({cf['kind'].replace('_',' ')})**: {cf['description']} Resolution: {cf['resolution']}.")
    write_doc("reports/policy_change_log_v1_to_v3.md", {"doc_id": "RPT-CHANGELOG", "doc_type": "policy_change_log", "company": COMPANY, "title": "Policy change log v1.0 to v3.0",
              "country": "GLOBAL", "issued": "2026-10-30", "retrieval_exclude": True}, "\n".join(out))
    T, G, X = load("tickets.json"), load("grievances.json"), load("exit_notes.json")
    for yr, label, start, end in [(2025, "FY2025 (January–December 2025)", "2025-01-01", "2025-12-31"), (2026, "2026 to date (January–October 2026)", "2026-01-01", "2026-10-31")]:
        out = [f"# Annual HR compliance and people report — {label}", "", "*Prepared for the Board People Committee. Figures are drawn from the HRMS helpdesk, grievance registers and exit interviews. Ticket figures before November 2025 are not included in this corpus.*", ""]
        for c in COUNTRIES:
            ts = [t for t in T if t["country"] == c and start <= t["created"] <= end]
            gs = [g for g in G if g["country"] == c and start <= g["filed"] <= end]
            xs = [x for x in X if x["country"] == c and start <= x["exit_date"] <= end]
            out += [f"## {CNAME[c]} ({ENTITY[c]})", "", f"Headcount at period end: about {HEADCOUNT[c]} employees across {len(OFFICE_BY_COUNTRY[c])} office(s). HR lead: {HR_LEAD[c]}.", "",
                    f"**Helpdesk.** {len(ts)} tickets." + (f" Top categories: " + ", ".join(f"{k.replace('_',' ')} ({v})" for k, v in Counter(t['category'] for t in ts).most_common(5)) + "." if ts else ""),
                    "", f"**Grievances.** {len(gs)} cases." + (" By category: " + ", ".join(f"{k.replace('_',' ')} ({v})" for k, v in Counter(g['category'] for g in gs).most_common()) + "." if gs else ""),
                    "", f"**Exits interviewed.** {len(xs)}." + (" Primary reasons: " + ", ".join(f"{k.replace('_',' ')} ({v})" for k, v in Counter(x['primary_reason'] for x in xs).most_common()) + "." if xs else ""), ""]
            if ts:
                cats = [k for k, _ in Counter(t['category'] for t in ts).most_common(8)]
                mons = sorted({t['created'][:7] for t in ts})
                out += ["| Month | " + " | ".join(k.replace('_', ' ') for k in cats) + " | Total | Avg CSAT |", "| --- " * (len(cats) + 3) + "|"]
                for mo in mons:
                    mt = [t for t in ts if t['created'][:7] == mo]
                    cs_ = [t['csat'] for t in mt if t['csat']]
                    out.append(f"| {mo} | " + " | ".join(str(sum(1 for t in mt if t['category'] == k)) for k in cats) + f" | {len(mt)} | {sum(cs_)/len(cs_):.2f} |")
                out.append("")
            if gs:
                out += ["| Category | Cases | Upheld | Partially upheld | Not upheld | Avg days to resolve |", "| --- | --- | --- | --- | --- | --- |"]
                for k, n in Counter(g['category'] for g in gs).most_common():
                    gg = [g for g in gs if g['category'] == k]
                    out.append(f"| {k.replace('_',' ')} | {n} | {sum(g['outcome']=='Upheld' for g in gg)} | {sum(g['outcome']=='Partially upheld' for g in gg)} | {sum(g['outcome']=='Not upheld' for g in gg)} | {sum(g['days_to_resolve'] for g in gg)/n:.1f} |")
                out.append("")
            posh = sum(1 for g in gs if g["category"] == "posh_referral")
            out += [f"**Harassment complaints referred to committee:** {posh}. **Statutory filings:** completed on time.", ""]
        write_doc(f"reports/annual_hr_report_{yr}.md", {"doc_id": f"RPT-HR-{yr}", "doc_type": "annual_hr_report", "company": COMPANY, "title": f"Annual HR report {yr}",
                  "country": "GLOBAL", "period": str(yr), "retrieval_exclude": True}, "\n".join(out))

if __name__ == "__main__":
    build_circulars(); build_faqs(); build_handbooks(); build_benefits(); build_reports()
    print("docs done")
