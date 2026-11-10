"""Generate record ledgers (tickets, grievances, exit notes, survey comments) and render them as files."""
import sys, os, math, calendar
sys.path.insert(0, os.path.dirname(__file__))
from common import *

rng = random.Random(SEED)
D = lambda s: date.fromisoformat(s)

DEPTS = ["Data Engineering", "Machine Learning", "Analytics Consulting", "Platform Engineering", "Product Management",
         "Cloud Operations", "Client Delivery", "Quality Engineering", "Finance", "People & HR", "Sales", "Design"]
LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
LEVEL_W = [10, 22, 24, 18, 12, 8, 6]
MODES = ["hybrid", "on-site", "remote", "off-site"]
MODE_W = [58, 22, 12, 8]
AGENTS = {c: [f"{n} (HR Helpdesk, {CNAME[c]})" for n in names] for c, names in {
    "US": ["Megan Ross", "Carlos Rivera", "Dana Whitaker"], "IN": ["Sneha Kulkarni", "Vikram Iyer", "Pooja Reddy", "Arvind Nair", "Meera Joshi"],
    "UK": ["Laura Bennett", "Tom Hughes"], "DE": ["Jana Müller", "Felix Wagner"], "NL": ["Lotte Visser", "Daan Bakker"],
    "IE": ["Aoife Kelly", "Ciarán Walsh"], "SG": ["Nur Aisyah", "Daniel Tan"], "AE": ["Layla Haddad", "Imran Siddiqui"],
    "CA": ["Chloé Gagnon", "Ryan Patel"], "AU": ["Jess Taylor", "Mitch Cooper"]}.items()}

def emp_id(c):
    return f"BL-{c}-{rng.randint(10000, 99999)}"

def office_for(c):
    offs = OFFICE_BY_COUNTRY[c]
    return rng.choices(offs, weights=[o[4] for o in offs])[0]

def rand_date(d0, d1):
    return d0 + timedelta(days=rng.randrange((d1 - d0).days + 1))

def months(y0, m0, n):
    out = []
    for i in range(n):
        y, m = y0 + (m0 - 1 + i) // 12, (m0 - 1 + i) % 12 + 1
        out.append((y, m))
    return out

def quarter_bounds(y, q):
    s = date(y, 3 * (q - 1) + 1, 1)
    e = date(y, 3 * q, calendar.monthrange(y, 3 * q)[1])
    return s, e

VOLUME_W = {c: HEADCOUNT[c] ** 0.6 for c in COUNTRIES}
VW_SUM = sum(VOLUME_W.values())

def sentiment_label(score):
    return "negative" if score < -0.2 else ("positive" if score > 0.25 else "neutral")

# ======================================================================
# TICKETS
# ======================================================================
TCATS = {
 "leave_balance": ("Leave balance and leave application", "15"),
 "payroll_query": ("Payroll and payslip query", "17"),
 "reimbursement": ("Expense reimbursement", "21"),
 "hybrid_attendance": ("Hybrid attendance and work mode", "9"),
 "shift_allowance": ("Shift allowance", "12"),
 "insurance_claim": ("Health insurance claim", "19"),
 "letters_documents": ("Letters and documents", "5"),
 "tax_declaration": ("Tax declaration and withholding", "17"),
 "onboarding": ("Onboarding and joining formalities", "6"),
 "exit_settlement": ("Exit and full and final settlement", "34"),
 "travel_relocation": ("Travel and relocation", "20"),
 "visa_immigration": ("Visa and cross-border work", "36"),
 "parental_leave": ("Parental leave", "16"),
 "home_office": ("Home office equipment and allowances", "14"),
 "policy_clarification": ("Policy clarification", "1"),
}
TCAT_W = {"leave_balance": 14, "payroll_query": 12, "reimbursement": 11, "hybrid_attendance": 6, "shift_allowance": 2,
          "insurance_claim": 8, "letters_documents": 8, "tax_declaration": 6, "onboarding": 5, "exit_settlement": 5,
          "travel_relocation": 5, "visa_immigration": 3, "parental_leave": 4, "home_office": 6, "policy_clarification": 5}

def ticket_weights(c, y, m):
    w = dict(TCAT_W)
    if c != "IN":
        w["shift_allowance"] = 0.4
    else:
        w["shift_allowance"] = 7
        if (y, m) in [(2026, 1), (2026, 2)]:
            w["shift_allowance"] = 22   # arrears after HR-CIR-2025-10
    if (y, m) in [(2026, 3), (2026, 4), (2026, 5)]:
        w["hybrid_attendance"] = 22 if (y, m) != (2026, 5) else 14   # HR-CIR-2026-04
    if (y, m) in [(2026, 5), (2026, 6)]:
        w["reimbursement"] = 26     # HRMS expense module migration
    if c == "UK" and (y, m) == (2026, 4):
        w["leave_balance"] = 22
    if c == "AU" and (y, m) in [(2026, 7), (2026, 8)]:
        w["parental_leave"] = 16
    if m in (1, 2, 3) and c == "IN":
        w["tax_declaration"] = 14
    return w

T_ISSUE = {
 "leave_balance": [
  "My leave balance in the HRMS shows {n} days of {lt} but by my calculation I should have {n2}. I joined on {jd} and have not taken any {lt} since {pm}.",
  "I applied for {n} days of {lt} from {d1} but the request is stuck in pending and my manager says it never reached them.",
  "Can you confirm how many days of {lt} I can carry forward into next year? The HRMS shows a carry-forward of {n} days, which looks too low.",
  "My {lt} was rejected automatically because the system says I have a negative balance. I took {n} days last month that were approved.",
  "I am moving to part-time hours next month and would like to understand how my {lt} will be pro-rated.",
  "The sandwich rule seems to have been applied to my leave over the weekend of {d1} and I have been charged {n2} days instead of {n}.",
  "I need to take {n} days of {lt} at short notice for a family matter. Is there a minimum notice period I must follow?",
 ],
 "payroll_query": [
  "My salary for {pm} was credited on {d1}, later than the usual date, and the payslip shows a deduction of {amt} that I do not recognise.",
  "My payslip for {pm} is missing the {allw} that was approved by my manager.",
  "There is a difference of {amt} between my net pay this month and last month although nothing changed in my compensation.",
  "I was promoted with effect from 1 April but the revised salary has not been reflected in my {pm} payslip.",
  "My bank account details changed and I want to make sure my next salary goes to the new account.",
  "The variable pay credited in June seems lower than the rating multiplier I was told about in my review.",
 ],
 "reimbursement": [
  "I submitted an expense claim of {amt} for {exp} on {d1} and it has not been paid yet.",
  "My claim for {exp} was rejected because the bill was not itemised, but the vendor only gives this format.",
  "After the move to the new expense module I cannot see my old claims, including one for {amt}.",
  "The new expense tool will not let me attach a GST invoice larger than 2 MB and my claim for {exp} keeps failing.",
  "I was asked to resubmit my claim for {exp} in the new module and I am worried it will now be outside the 30-day window.",
  "My manager approved my claim for {amt} two weeks ago but finance has still not processed it.",
 ],
 "hybrid_attendance": [
  "My attendance report shows I missed the office-day requirement in {pm}, but I was on approved leave for {n} days.",
  "With the change to three office days a week, I would like to request an exception because of a long commute from {place}.",
  "I am a caregiver for a parent and three office days a week is not workable for me. How do I request an accommodation?",
  "My access-card swipes for {d1} were not recorded and the HRMS marked me absent for an office day.",
  "Our team anchor days changed after the new hybrid rules and the desk booking app shows no desks available on those days.",
  "Does a client visit count towards the office-day requirement? I spent {n} days at the client site in {pm}.",
  "I received a reminder that I have fallen short of the monthly office days. Is this going to affect my performance review?",
 ],
 "shift_allowance": [
  "I worked {n} night shifts in {pm} but the payslip shows the allowance at the old rate.",
  "The night shift allowance increase from January has not been paid. When will the arrears be credited?",
  "My late-shift allowance for {pm} is missing for the days I worked from home.",
  "I was on the on-call rota for {n} weekend days but the standby allowance has not been paid.",
  "Can you confirm the current night shift allowance per night? My payslip and the policy portal show different figures.",
 ],
 "insurance_claim": [
  "My cashless claim at {hosp} was rejected at discharge and I had to pay {amt} myself.",
  "I want to add my newborn to the group health policy. The child was born on {d1}.",
  "The reimbursement for my parent's hospitalisation of {amt} is still pending with the insurer after {n} weeks.",
  "Is the cost of physiotherapy covered under our health insurance? I have been advised {n} sessions.",
  "I would like to buy a voluntary top-up for my parents. When is the enrolment window?",
 ],
 "letters_documents": [
  "I need an employment verification letter for a visa application by {d1}.",
  "Please issue an address proof letter for my bank account. I moved recently.",
  "My experience letter from my previous stint shows the wrong designation.",
  "I need a salary certificate for a home loan application.",
  "Can I get a letter confirming my work mode for my landlord? They want proof that I work remotely.",
 ],
 "tax_declaration": [
  "I missed the investment proof deadline. Can I still submit my rent receipts?",
  "My tax deduction increased sharply in {pm}. Did the regime change I selected take effect?",
  "I need a corrected Form 16 because my previous employer's income was not included.",
  "How are relocation benefits taxed? I received a relocation allowance of {amt}.",
  "My withholding looks wrong after I moved states/provinces. Who can review it?",
 ],
 "onboarding": [
  "I joined on {d1} and my laptop has still not been delivered to my home address.",
  "My background verification is showing as pending although I submitted all documents.",
  "I have not been added to the payroll yet and my first salary is due next week.",
  "I cannot access the mandatory induction modules on the learning platform.",
  "My buddy has not been assigned and my manager is on leave this week.",
 ],
 "exit_settlement": [
  "My last working day was {d1} and my full and final settlement has not been paid yet.",
  "The leave encashment in my settlement statement looks short by {n} days.",
  "I have returned my laptop by courier but the asset clearance is still showing as pending.",
  "Can I adjust my notice period shortfall against my earned leave balance?",
  "My relieving letter has not been issued even though all clearances are complete.",
 ],
 "travel_relocation": [
  "My travel request for a client visit to {place} has been pending approval for {n} days.",
  "The hotel limit for {place} is too low for the dates of my trip because of a conference.",
  "I am relocating to the {office} office at the Company's request. What support am I entitled to?",
  "My per diem for the trip to {place} was paid at the wrong grade.",
  "Can I extend my business trip to {place} with personal days at my own cost?",
 ],
 "visa_immigration": [
  "I would like to work from {place} for {n} working days to visit family. Is this within the allowance?",
  "My work permit expires on {d1}. Has the renewal been started?",
  "I have been asked to travel to {place} for a workshop. Do I need a business visa?",
  "I am on an international assignment and my dependants' visas are due for renewal.",
 ],
 "parental_leave": [
  "I am expecting a baby in {pm}. How many weeks of paid parental leave am I entitled to?",
  "How does the Company top-up work alongside the government parental leave payment?",
  "Can I split my partner leave into two blocks?",
  "I would like to return to work part-time after parental leave. What is the process?",
  "My parental leave pay for {pm} was lower than expected.",
 ],
 "home_office": [
  "My home office setup allowance claim of {amt} was rejected because I claimed it within 3 years of the last one.",
  "My monthly internet allowance has not been paid since {pm}.",
  "My monitor stopped working and I need a replacement shipped to my home.",
  "I moved house. Do I need to submit a new home workplace self-declaration?",
  "Can I use the co-working space budget for days when my power is out?",
 ],
 "policy_clarification": [
  "Can I take up a weekend teaching job? I want to check the moonlighting rules.",
  "What gifts can I accept from a client during the festive season?",
  "Is there a policy on using AI tools for client work?",
  "How many days can I work from another city in the country of employment?",
  "Who should I contact about a conflict of interest with a vendor?",
 ],
}
T_RES = [
 "Checked the record in the HRMS and corrected it; the employee was informed and confirmed the fix.",
 "Explained the relevant policy section and shared the link to the guidance; no further action needed.",
 "Escalated to {team} with the supporting documents; {team} resolved it within the service level.",
 "Raised a correction for the next payroll run; the difference will appear on the next payslip.",
 "Asked the employee to resubmit with the missing documents; resolved after resubmission.",
 "Coordinated with the manager to approve the pending request; the status now shows approved.",
 "Confirmed the entitlement under the current policy and updated the employee's balance.",
 "Logged the issue as part of a known problem; a fix was deployed and the ticket was closed.",
 "Approved as an exception by the HRBP, recorded in the HRMS with reasons.",
 "Declined because the request falls outside policy; the employee was told how to appeal.",
]
TEAMS = ["Payroll", "Finance", "IT Service Desk", "Benefits", "Global Mobility", "Admin", "Learning & Development", "HR Operations"]
TONE = {
 "negative": ["This is the second time I am raising this and it is getting frustrating.", "I am quite upset that nobody has replied so far.",
              "This is causing real financial stress for my family.", "Honestly the new process is confusing and slow.",
              "I have wasted a lot of time on this already.", "I am disappointed with how long this is taking."],
 "neutral": ["Please let me know what I need to do.", "Could you check and advise?", "Thanks in advance.", "Happy to share more details if needed.", ""],
 "positive": ["Thanks, the helpdesk has always been quick with me.", "Appreciate the help as always!", "No rush, just want to confirm.", "Thank you for the quick support last time."],
}
CSAT_BY_SENT = {"negative": [1, 2, 2, 3], "neutral": [3, 4, 4, 5], "positive": [4, 5, 5, 5]}
LEAVE_TYPES = ["earned leave", "casual leave", "sick leave", "annual leave", "floating holiday"]
EXPENSES = ["a client dinner", "airport cabs", "a certification exam fee", "hotel stay", "conference registration", "a team lunch", "local conveyance"]
ALLOWANCES = ["night shift allowance", "internet allowance", "on-call allowance", "conveyance allowance", "home office allowance"]
HOSPITALS = ["Sunrise Multispecialty Hospital", "CityCare Hospital", "St. Brendan's Clinic", "Harbourview Medical Centre", "Lakeside General"]
PLACES = ["Mumbai", "Delhi", "Kochi", "Manchester", "Munich", "Rotterdam", "Cork", "Johor Bahru", "Abu Dhabi", "Vancouver", "Melbourne", "New York", "Lisbon", "Bali"]

CAT_TEAM = {"payroll_query": "Payroll", "reimbursement": "Finance", "shift_allowance": "Payroll", "insurance_claim": "Benefits", "tax_declaration": "Payroll",
            "onboarding": "HR Operations", "exit_settlement": "HR Operations", "travel_relocation": "Global Mobility", "visa_immigration": "Global Mobility",
            "home_office": "IT Service Desk", "hybrid_attendance": "HR Operations", "letters_documents": "HR Operations", "parental_leave": "Benefits"}
def FACTS(c, d):
    v = "v3.0" if d >= date(2026, 11, 1) else "v2.0"
    night = 600 if d >= date(2026, 1, 1) else 500
    office_days = 3 if d >= date(2026, 4, 1) else 2
    return {"night": "₹" + str(night), "odays": office_days, "al": POLICY["annual_leave_days"][c].get("v3.0"),
            "sick": POLICY["paid_sick_days"][c].get("v3.0"), "bpl": POLICY["birth_parent_leave_weeks_full_pay"][c]["v3.0"],
            "ppl": POLICY["partner_leave_weeks_full_pay"][c]["v3.0"], "abroad": 20, "cname": CNAME[c]}
T_CONTEXT = ["I checked the policy portal but could not find a clear answer.", "My manager suggested I raise a ticket.", "This affects my plans for next month.",
             "A colleague in my team has the same problem.", "I have attached a screenshot from the HRMS.", "I raised this on chat earlier but did not get a reference number.",
             "I am working from home this week if a call is easier.", "I would appreciate an update by the end of the week.", "", ""]
T_REPLY = ["Thanks for raising this. I have checked your record and will update you within two working days.",
           "Under the current policy, hybrid employees attend the office {odays} days a week averaged over the month; approved leave and holidays reduce the requirement pro rata.",
           "The current night shift allowance is {night} per night worked (Chapter 12.3). Arrears are paid in the next payroll run after the timesheet is approved.",
           "Employees of the {cname} entity receive {al} working days of paid annual leave under the current manual.",
           "The Company provides {bpl} weeks of birth-parent leave at full pay and {ppl} weeks of partner leave at full pay in {cname}.",
           "You can work from another country for up to {abroad} working days a year with prior approval from your manager, HRBP, Legal and Information Security.",
           "Please submit the request in the HRMS with the supporting documents so the approver can see it.",
           "I have raised this with the team that owns the process and asked them to prioritise it.",
           "Claims must be submitted within 30 days of the expense with itemised bills; the new expense module accepts files up to 5 MB from June.",
           "Your manager needs to approve the request first; I have sent them a reminder."]
T_FOLLOW = {"negative": ["I still have not received the payment.", "This is not acceptable, it has been weeks.", "That does not answer my question.", "Please escalate this."],
            "neutral": ["Okay, I will wait for the update.", "Thanks, I have submitted the documents.", "Noted, thank you.", "Understood."],
            "positive": ["Thank you, that was quick!", "Great, that solves it.", "Thanks a lot for the clear answer.", "Perfect, appreciate it."]}
T_RES_CAT = {
 "shift_allowance": ["Confirmed the night shift allowance of {night} per night under Chapter 12.3; Payroll processed the missing amount as arrears in the next payroll run.",
                     "Verified the approved roster with the manager; the allowance was missing because the timesheet was not approved in time. Payroll will correct it next month.",
                     "Explained that the allowance applies in every work mode, including remote work; the missing days were added."],
 "hybrid_attendance": ["Regularised the missed swipes in the HRMS; the employee now meets the {odays}-day requirement for the month.",
                       "Explained that the requirement reduces pro rata for leave and holidays; no shortfall was recorded.",
                       "Routed the exception request to the HRBP under Chapter 3 (reasonable accommodation); a three-month exception was approved.",
                       "Confirmed that client-site days count as office days for attendance purposes; the report was corrected.",
                       "Declined the exception because the reason does not meet the accommodation criteria; the employee was told how to request a skip-level review."],
 "reimbursement": ["Finance located the claim in the legacy tool and migrated it to the new expense module; it will be paid in the next payroll.",
                   "The claim was paid after the employee attached an itemised GST invoice.", "Finance approved a late submission because the delay was caused by the module migration.",
                   "Reset the claim status after a known defect in the new expense module; payment released."],
 "leave_balance": ["Recalculated the balance from the joining date and corrected the accrual; the HRMS now shows the right figure.",
                   "Confirmed the carry-forward limit under Chapter 15 and explained the year-end lapse rule.", "The pending request was re-routed to the correct approver and approved the same day.",
                   "Reversed the sandwich-rule deduction because the holidays fell between leave days and should not count."],
 "parental_leave": ["Confirmed {bpl} weeks of birth-parent leave at full pay and {ppl} weeks of partner leave in {cname}; shared the application form.",
                    "Explained how the Company tops up the statutory payment to full pay during the Company leave period.", "Approved the split of partner leave into two blocks within six months."],
}
def amt_for(c):
    base = {"INR": rng.choice([1850, 2400, 3600, 4999, 7200, 12500, 18400, 26000]), "USD": rng.choice([45, 120, 260, 480, 900]),
            "GBP": rng.choice([38, 95, 210, 360]), "EUR": rng.choice([42, 110, 230, 410]), "SGD": rng.choice([60, 140, 320, 650]),
            "AED": rng.choice([150, 420, 900, 1600]), "CAD": rng.choice([55, 130, 300, 600]), "AUD": rng.choice([60, 150, 340, 700])}
    return money(c, base[CURRENCY[c]])

def ticket_text(t):
    c = t["country"]
    tpl = pick(rng, T_ISSUE[t["category"]])
    d = D(t["created"])
    msg = tpl.format(n=rng.randint(1, 6), n2=rng.randint(7, 12), lt=pick(rng, LEAVE_TYPES), jd=(d - timedelta(days=rng.randint(200, 1500))).strftime("%d %b %Y"),
                     pm=(d.replace(day=1) - timedelta(days=1)).strftime("%B"), d1=(d + timedelta(days=rng.randint(-20, 25))).strftime("%d %b %Y"),
                     amt=amt_for(c), exp=pick(rng, EXPENSES), allw=pick(rng, ALLOWANCES), hosp=pick(rng, HOSPITALS),
                     place=pick(rng, PLACES), office=pick(rng, [o[1] for o in OFFICES if o[1] != t["office"]]))
    tone = pick(rng, TONE[t["sentiment"]])
    res = pick(rng, T_RES_CAT.get(t["category"], T_RES)).format(team=CAT_TEAM.get(t["category"], pick(rng, TEAMS)), **FACTS(c, d))
    thread = ""
    if rng.random() < 0.55:
        thread = f"\n**Agent reply:** {pick(rng, T_REPLY).format(**FACTS(c, d))}\n**Employee follow-up:** {pick(rng, T_FOLLOW[t['sentiment']])}\n"
    cat_label, chap = TCATS[t["category"]]
    lines = [f"### Ticket {t['id']} — {cat_label}",
             f"**Opened:** {d.strftime('%d %B %Y')} · **Country:** {CNAME[c]} · **Office:** {t['office']} · **Work mode:** {t['work_mode']} · **Level:** {t['level']}",
             f"**Employee:** {t['employee']} · **Department:** {t['dept']} · **Channel:** {t['channel']} · **Priority:** {t['priority']}",
             f"**Policy reference:** Chapter {chap} · **Assigned to:** {t['agent']}",
             "", f"**Employee message:** {msg} {pick(rng, T_CONTEXT)} {tone}".strip(), thread,
             f"**Resolution note:** {res}",
             f"**Status:** {t['status']} · **Resolved in:** {t['resolution_hours']} working hours · **CSAT:** {t['csat'] if t['csat'] else 'not rated'}/5", ""]
    return "\n".join(lines)

def gen_tickets(target=6050):
    out = []
    mlist = months(2025, 11, 12)
    total_w = 0
    per = {}
    for c in COUNTRIES:
        for (y, m) in mlist:
            mult = 1.0 + (0.35 if (y, m) in [(2026, 3), (2026, 4), (2026, 5), (2026, 6)] else 0)
            per[(c, y, m)] = VOLUME_W[c] * mult
    tw = sum(per.values())
    seq = 0
    for (c, y, m), w in per.items():
        n = max(6, round(target * w / tw))
        if c == "AE" and (y, m) < (2026, 1): n = max(6, n // 2)
        wts = ticket_weights(c, y, m)
        cats = list(wts)
        for i in range(n):
            seq += 1
            cat = rng.choices(cats, weights=[wts[k] for k in cats])[0]
            off = office_for(c)
            d0 = date(y, m, 1)
            dd = rand_date(d0, date(y, m, calendar.monthrange(y, m)[1]))
            neg_p = 0.30
            if cat in ("hybrid_attendance",) and (y, m) >= (2026, 3): neg_p = 0.62
            if cat == "reimbursement" and (y, m) in [(2026, 5), (2026, 6)]: neg_p = 0.58
            if cat == "shift_allowance" and (y, m) in [(2026, 1), (2026, 2)]: neg_p = 0.55
            r = rng.random()
            sent = "negative" if r < neg_p else ("positive" if r > 1 - 0.22 else "neutral")
            base_h = {"reimbursement": 30, "insurance_claim": 40, "exit_settlement": 26, "visa_immigration": 36}.get(cat, 14)
            if cat == "reimbursement" and (y, m) in [(2026, 5), (2026, 6)]: base_h = 62
            hrs = max(1, int(rng.gammavariate(2.0, base_h / 2)))
            status = rng.choices(["Resolved", "Closed", "Resolved", "Escalated – resolved"], weights=[55, 25, 10, 10])[0]
            csat = pick(rng, CSAT_BY_SENT[sent]) if rng.random() > 0.18 else None
            out.append({"id": f"HD-{c}-{y}{m:02d}-{i+1:04d}", "country": c, "office": off[1], "created": dd.isoformat(),
                        "year": y, "month": m, "category": cat, "work_mode": rng.choices(MODES, weights=MODE_W)[0],
                        "level": rng.choices(LEVELS, weights=LEVEL_W)[0], "dept": pick(rng, DEPTS), "employee": emp_id(c),
                        "channel": rng.choice(["HRMS portal", "HRMS portal", "email", "chat", "phone"]),
                        "priority": rng.choices(["Low", "Medium", "High"], weights=[35, 50, 15])[0],
                        "agent": pick(rng, AGENTS[c]), "sentiment": sent, "resolution_hours": hrs, "status": status, "csat": csat})
    return out

# ======================================================================
# GRIEVANCES
# ======================================================================
GCATS = {
 "workload": "Workload and working hours", "manager_conduct": "Manager behaviour", "pay_discrepancy": "Pay and allowances",
 "hybrid_policy": "Hybrid and work-mode decisions", "promotion_fairness": "Promotion and rating fairness", "bullying": "Bullying and disrespect",
 "discrimination": "Discrimination", "transport_safety": "Transport and safety", "leave_denial": "Leave refusal", "facilities": "Office facilities",
 "posh_referral": "Sexual harassment (referred to Internal Committee / Respect at Work Committee)", "retaliation": "Retaliation",
}
GCAT_W = {"workload": 16, "manager_conduct": 13, "pay_discrepancy": 11, "hybrid_policy": 6, "promotion_fairness": 12, "bullying": 7,
          "discrimination": 4, "transport_safety": 4, "leave_denial": 8, "facilities": 7, "posh_referral": 3, "retaliation": 2}
THEMES = {
 "workload": ["unrealistic deadlines", "after-hours messages", "understaffing", "weekend work"],
 "manager_conduct": ["public criticism", "favouritism", "lack of one-to-ones", "micro-management"],
 "pay_discrepancy": ["missing allowance", "incorrect increment", "delayed arrears", "overtime not paid"],
 "hybrid_policy": ["office-day mandate", "commute cost", "caregiving conflict", "desk shortage"],
 "promotion_fairness": ["proximity bias", "calibration opacity", "rating downgrade", "skipped promotion"],
 "bullying": ["exclusion from meetings", "demeaning remarks", "hostile chat messages"],
 "discrimination": ["age", "gender", "disability accommodation", "religion"],
 "transport_safety": ["late cab pickup", "unsafe drop point", "route changes", "driver conduct"],
 "leave_denial": ["planned leave refused", "short-notice cancellation", "school holiday clash"],
 "facilities": ["air conditioning", "cafeteria quality", "noise", "parking"],
 "posh_referral": ["unwelcome comments", "inappropriate messages"],
 "retaliation": ["removed from project after complaint", "rating dropped after complaint"],
}
G_SUMMARY = {
 "workload": ["The employee states that the team has carried two vacant positions for {n} months and that they have regularly worked past {hr} pm to meet client deadlines.",
              "The employee reports being asked to join calls with the {tz} client every evening, outside agreed core hours, without a rotation.",
              "The complaint describes repeated weekend deployments over the last quarter without compensatory off being approved."],
 "manager_conduct": ["The employee alleges that their manager criticises them in team meetings in front of the client and does not hold regular one-to-ones.",
                     "The employee feels that work allocation favours a small group close to the manager, leaving them with routine tasks only.",
                     "The employee reports that the manager asks for hourly status updates on chat, which they find excessive."],
 "pay_discrepancy": ["The employee says their {allw} for {pm} was not paid despite approved timesheets.",
                     "The employee disputes the increment applied in April, which was lower than the rating band in the compensation guide.",
                     "The employee reports that overtime approved by the manager was not processed in payroll for {n} weeks."],
 "hybrid_policy": ["Following the move to three office days a week, the employee says the commute of {km} km each way makes the requirement unreasonable and asks for an exception.",
                   "The employee, a primary caregiver, says the new office-day requirement conflicts with care arrangements and their accommodation request was declined.",
                   "The employee complains that the team's anchor days were changed without consultation and desks are not available on those days."],
 "promotion_fairness": ["The employee believes their promotion case was not presented at calibration although they met the criteria.",
                        "The employee, who works remotely, believes office-based colleagues receive more visible assignments and better ratings.",
                        "The employee disputes a rating downgrade at calibration that was not explained to them."],
 "bullying": ["The employee reports being repeatedly left out of project meetings and chat channels by two colleagues.",
              "The employee describes demeaning remarks about their accent made by a senior colleague during stand-ups."],
 "discrimination": ["The employee believes they were passed over for an onsite assignment because of their age.",
                    "The employee says their request for an ergonomic accommodation was ignored for {n} weeks."],
 "transport_safety": ["The employee reports that the late-shift cab arrived {n} minutes late on several nights and dropped them away from home.",
                      "Since the new transport vendor started, the employee says route changes have doubled the commute time."],
 "leave_denial": ["The employee's planned leave during school holidays was refused at short notice citing a client release.",
                  "The employee says approved leave was cancelled two days before travel."],
 "facilities": ["The employee complains that the air conditioning on floor {n} has been faulty for weeks.",
                "The employee raises concerns about noise in the open area near the collaboration zone and the lack of phone booths."],
 "posh_referral": ["A complaint involving unwelcome comments of a sexual nature was received and referred to the committee under the harassment policy; details are held by the committee.",
                   "A complaint about inappropriate messages from a colleague was referred to the committee; the case summary is confidential."],
 "retaliation": ["The employee believes they were removed from a project after acting as a witness in an earlier inquiry.",
                 "The employee says their rating dropped after they raised a grievance last year."],
}
G_STAGES = ["Stage 1 (manager)", "Stage 2 (HRBP)", "Stage 3 (Grievance Redressal Committee)", "Internal Committee", "Respect at Work Committee"]
G_OUTCOMES = ["Upheld", "Partially upheld", "Not upheld", "Withdrawn", "Resolved informally"]
G_ACTIONS = ["manager coaching arranged", "pay correction processed", "work-mode exception approved for three months", "team working agreement revised",
             "rotation introduced for evening calls", "transport route reviewed with the vendor", "facilities repair completed",
             "rating reviewed by skip-level manager", "accommodation granted", "no action required", "written warning issued to respondent",
             "mediation session held", "workload rebalanced with an additional contractor"]

def g_weights(c, y, q):
    w = dict(GCAT_W)
    if (y, q) in [(2026, 2), (2026, 3)]:
        w["hybrid_policy"] = 24 if (y, q) == (2026, 2) else 15
    if c == "IN" and (y, q) in [(2025, 4), (2026, 1)]:
        w["transport_safety"] = 16
    if c not in ("IN",):
        w["transport_safety"] = 1
    return w

def gen_grievances(target=1720):
    out = []
    qs = [(2024, 4), (2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2), (2026, 3)]
    per = {(c, y, q): VOLUME_W[c] * (1.25 if (y, q) == (2026, 2) else 1.0) for c in COUNTRIES for (y, q) in qs}
    tw = sum(per.values())
    for (c, y, q), w in per.items():
        n = max(5, round(target * w / tw))
        if c in ("AE", "AU") and (y, q) < (2025, 2): n = max(3, n // 3)
        s, e = quarter_bounds(y, q)
        wts = g_weights(c, y, q)
        cats = list(wts)
        for i in range(n):
            cat = rng.choices(cats, weights=[wts[k] for k in cats])[0]
            filed = rand_date(s, e)
            stage = "Internal Committee" if (cat == "posh_referral" and c == "IN") else ("Respect at Work Committee" if cat == "posh_referral" else rng.choices(G_STAGES[:3], weights=[45, 40, 15])[0])
            days = {"Stage 1 (manager)": 6, "Stage 2 (HRBP)": 14, "Stage 3 (Grievance Redressal Committee)": 26, "Internal Committee": 62, "Respect at Work Committee": 48}[stage]
            dres = max(1, int(rng.gauss(days, days * 0.35)))
            outcome = rng.choices(G_OUTCOMES, weights=[24, 26, 28, 8, 14])[0]
            th = rng.sample(THEMES[cat], k=min(2, len(THEMES[cat])))
            out.append({"id": f"GRV-{c}-{y}Q{q}-{i+1:03d}", "country": c, "office": office_for(c)[1], "filed": filed.isoformat(),
                        "year": y, "quarter": q, "category": cat, "themes": th, "stage": stage, "days_to_resolve": dres,
                        "outcome": outcome, "action": pick(rng, G_ACTIONS) if outcome in ("Upheld", "Partially upheld", "Resolved informally") else "no action required",
                        "work_mode": rng.choices(MODES, weights=MODE_W)[0], "level": rng.choices(LEVELS, weights=LEVEL_W)[0],
                        "dept": pick(rng, DEPTS), "employee": emp_id(c), "anonymous": rng.random() < 0.07})
    return out

G_BACKGROUND = ["The employee has been in the {team} team for {n} months and says the issue started after a change of project.",
                "The employee says the matter has continued for about {n} weeks and was first raised informally with the manager.",
                "Two other members of the {team} team have raised similar concerns informally, according to the HRBP.",
                "The employee had a rating of 3 in the last cycle and no prior grievances on record.",
                "The issue arose during a critical client release when the team was working extended hours.",
                "The employee asked for the matter to be handled confidentially and without involving the client."]
G_STEPS = ["Both parties were given the chance to respond in writing within 3 working days.", "The respondent manager was interviewed and accepted part of the account.",
           "HR checked the relevant policy chapter and the decision records in the HRMS.", "A support colleague attended the hearing with the employee.",
           "The hearing was held by secure video because the employee works remotely.", "The skip-level manager was consulted before the decision."]
G_FIND = {"Upheld": ["The evidence supports the employee's account and the policy was not applied correctly.", "The complaint was substantiated on the main points."],
          "Partially upheld": ["Part of the complaint was supported by evidence; the rest reflected a misunderstanding of the policy.", "The concern about process was valid, but the decision itself was within policy."],
          "Not upheld": ["The evidence did not support the complaint; the decision was within policy and properly documented.", "No breach of policy was found, although communication could have been clearer."],
          "Withdrawn": ["The employee withdrew the complaint after an informal discussion.", "The complaint was withdrawn before the hearing."],
          "Resolved informally": ["The parties agreed a practical solution at the first meeting.", "The manager and employee agreed changes without a formal hearing."]}
G_FOLLOW = ["A follow-up check-in is scheduled in {n} days.", "HR will review the situation again after {n} days.", "The employee was informed of the right to appeal to the CHRO within 7 working days.",
            "The case was closed and the employee confirmed they were satisfied with the outcome.", "The employee was told how to escalate if the issue recurs."]
def grievance_text(g):
    c = g["country"]
    s = pick(rng, G_SUMMARY[g["category"]]).format(n=rng.randint(2, 9), hr=rng.choice([9, 10, 11]), tz=rng.choice(["US East Coast", "Australian", "German"]),
            allw=pick(rng, ALLOWANCES), pm=pick(rng, ["January", "March", "May", "August", "October"]), km=rng.choice([24, 31, 38, 45]))
    quote_pool = {
        "negative": ["I have raised this informally twice and nothing changed.", "It feels like my concerns do not matter.", "This has affected my health and motivation.", "I am considering leaving if this continues."],
        "neutral": ["I would like a fair review of the facts.", "I am open to a discussion with my manager.", "I want clarity on how the policy applies to me."],
    }
    q = pick(rng, quote_pool["negative" if rng.random() < 0.7 else "neutral"])
    inv = pick(rng, ["The HRBP met the employee and the manager separately and reviewed chat records and timesheets.",
                     "The committee reviewed documents, interviewed two witnesses and heard both parties.",
                     "HR reviewed payroll records and the approved timesheets for the period.",
                     "The manager met the employee within 7 working days and documented the discussion."])
    if g["category"] == "posh_referral":
        q = "Details are confidential and held by the committee."
        inv = "The committee followed the confidential inquiry procedure; only the outcome category is recorded here."
    lines = [f"### Case {g['id']} — {GCATS[g['category']]}",
             f"**Filed:** {D(g['filed']).strftime('%d %B %Y')} · **Country:** {CNAME[c]} · **Office:** {g['office']} · **Work mode:** {g['work_mode']} · **Level:** {g['level']} · **Department:** {g['dept']}",
             f"**Complainant:** {'anonymous' if g['anonymous'] else g['employee']} · **Handled at:** {g['stage']} · **Days to resolve:** {g['days_to_resolve']}",
             f"**Themes:** {', '.join(g['themes'])}",
             "", f"**Summary.** {s} {pick(rng, G_BACKGROUND).format(n=rng.randint(2, 14), team=g['dept'])}", "", f"**Employee statement.** \"{q}\"", "", f"**Investigation.** {inv} {pick(rng, G_STEPS)}", "",
             f"**Findings.** {pick(rng, G_FIND[g['outcome']])}", "",
             f"**Outcome.** {g['outcome']}. Action: {g['action']}. {pick(rng, G_FOLLOW).format(n=rng.choice([30, 45, 60, 90]))}", ""]
    return "\n".join(lines)

# ======================================================================
# EXIT NOTES
# ======================================================================
EREASONS = {"compensation": "Better compensation elsewhere", "career_growth": "Career growth and promotion", "office_mandate": "Office attendance requirement",
            "manager": "Relationship with manager", "relocation": "Personal relocation", "workload": "Workload and burnout",
            "higher_studies": "Higher studies", "role_scope": "Role scope and interesting work", "family": "Family reasons", "remote_offer": "Fully remote offer elsewhere"}
ER_W = {"compensation": 20, "career_growth": 18, "office_mandate": 4, "manager": 9, "relocation": 9, "workload": 11, "higher_studies": 6, "role_scope": 10, "family": 7, "remote_offer": 6}
LIKED = ["supportive colleagues", "the learning budget and certifications", "flexible hours", "interesting client problems", "the buddy programme",
         "the health insurance cover", "the wellbeing sessions", "the inclusive culture", "the hackathons", "good onboarding"]
E_DRIVERS = {
 "compensation": ["The employee received an offer about {p}% higher than current fixed pay and felt the April increment did not reflect market rates.",
                  "They felt their pay had fallen behind peers in the market after two cycles of modest increments."],
 "career_growth": ["They were passed over for promotion in the last cycle and could not see a path to the next level within a year.",
                   "They want to move into a lead role and no suitable internal opening was available."],
 "office_mandate": ["The change to three office days a week from April added {h} hours of commuting a week and they could not make it work with their family routine.",
                    "They joined when the team worked two office days and felt the move to three days changed the deal they had signed up for.",
                    "With the new attendance requirement and a long commute, they accepted a role with more flexibility."],
 "manager": ["They described frequent changes in priorities and a lack of regular one-to-ones with their manager.",
             "They felt their contributions were not recognised by their manager."],
 "relocation": ["They are moving to {place} for family reasons and no Company office is available there.",
                "Their spouse has been transferred and they are relocating with the family."],
 "workload": ["They spoke about sustained late evenings on a client programme and feeling burnt out.",
              "They felt the team was understaffed for most of the year."],
 "higher_studies": ["They have been admitted to a full-time master's programme starting next term."],
 "role_scope": ["They wanted to work on more advanced machine learning problems than their current project allows.",
                "Their role had become repetitive maintenance work."],
 "family": ["They need to care for an elderly parent and are taking a break from work."],
 "remote_offer": ["They accepted a fully remote role with another employer.",
                  "A competitor offered fully remote work, which was the deciding factor."],
}
E_SUGG = ["Offer more flexibility on office days for long-distance commuters.", "Make promotion criteria more transparent.", "Review compensation bands against the market more often.",
          "Hire to fill vacancies faster so teams are not stretched.", "Hold regular one-to-ones in every team.", "Keep the learning budget; it is valuable.",
          "Communicate policy changes earlier and explain the reasons.", "Improve the new expense tool."]
E_QUOTE = {
 "negative": ["Honestly, the last few months have been draining.", "I didn't feel heard when I raised concerns.", "The new rules made it hard to stay.", "I felt the company changed the deal on us."],
 "neutral": ["It was a practical decision for me at this stage.", "Overall it was a fair place to work.", "It is mostly about the next step in my career."],
 "positive": ["I've learned a lot here and would happily come back.", "Great people, I'll miss the team.", "It was a tough decision; BragsLabs treated me well."],
}

def gen_exits(target=960):
    out = []
    qs = [(2025, 4), (2026, 1), (2026, 2), (2026, 3)]
    per = {(c, y, q): VOLUME_W[c] * (1.2 if (y, q) in [(2026, 2), (2026, 3)] else 1.0) for c in COUNTRIES for (y, q) in qs}
    tw = sum(per.values())
    for (c, y, q), w in per.items():
        n = max(5, round(target * w / tw))
        s, e = quarter_bounds(y, q)
        wts = dict(ER_W)
        post = (y, q) >= (2026, 2)
        if post:
            wts["office_mandate"] = 19; wts["remote_offer"] = 11
        for i in range(n):
            r = rng.choices(list(wts), weights=list(wts.values()))[0]
            r2 = rng.choice([k for k in ER_W if k != r])
            base = {"compensation": -0.05, "career_growth": -0.1, "office_mandate": -0.45, "manager": -0.5, "relocation": 0.35, "workload": -0.4,
                    "higher_studies": 0.45, "role_scope": 0.0, "family": 0.2, "remote_offer": -0.2}[r]
            score = max(-1, min(1, rng.gauss(base - (0.12 if post else 0), 0.3)))
            dd = rand_date(s, e)
            tenure = round(rng.uniform(0.4, 9.5), 1)
            out.append({"id": f"EXIT-{c}-{y}Q{q}-{i+1:03d}", "country": c, "office": office_for(c)[1], "exit_date": dd.isoformat(), "year": y, "quarter": q,
                        "primary_reason": r, "secondary_reason": r2, "sentiment_score": round(score, 2), "sentiment": sentiment_label(score),
                        "would_rejoin": "Yes" if score > 0.15 else ("Maybe" if score > -0.3 else "No"), "tenure_years": tenure,
                        "work_mode": rng.choices(MODES, weights=MODE_W)[0], "level": rng.choices(LEVELS, weights=LEVEL_W)[0],
                        "dept": pick(rng, DEPTS), "employee": emp_id(c), "regretted": rng.random() < 0.45})
    return out

E_CHANGE = {"compensation": ["A market correction of their salary during the year might have kept them.", "A retention offer was discussed but came too late."],
            "career_growth": ["A clear promotion timeline or an internal move to a lead role.", "Earlier visibility of internal openings at the next level."],
            "office_mandate": ["Keeping two office days, or a commute-based exception, would have changed the decision.", "A remote or flexible arrangement for long-distance commuters."],
            "manager": ["A change of reporting manager earlier in the year.", "Regular one-to-ones and clearer feedback."],
            "relocation": ["A remote option in the new city, which the role did not allow.", "Nothing; the move was for family reasons."],
            "workload": ["Filling the team's vacancies sooner.", "A rotation for evening client calls."],
            "higher_studies": ["Support for part-time study, although the programme is full-time.", "Nothing; they plan to return after the programme."],
            "role_scope": ["A move to a project with more advanced work.", "An internal rotation through the talent marketplace."],
            "family": ["A longer unpaid break or sabbatical, which they were not yet eligible for.", "Part-time work for a period."],
            "remote_offer": ["A fully remote arrangement, which the role was not eligible for.", "Fewer office days."]}
E_NOTICE = ["They served the full notice period and completed a documented handover.", "Part of the notice period was waived by the manager after handover was complete.",
            "The notice shortfall was adjusted against earned leave with HR approval.", "They were placed on garden leave for the last two weeks.",
            "Handover was completed early and the remaining notice was spent on documentation."]
E_SUGG2 = ["They also asked for faster settlement of final dues.", "They felt exit formalities were smooth.", "They mentioned the new expense module as a pain point.",
           "They would recommend BragsLabs to friends for early-career roles.", "They suggested better recognition for remote employees.", ""]
E_HRBP = {"negative": ["Avoidable loss; the underlying issue is shared by others in the team.", "Signals a retention risk in the same team that needs follow-up."],
          "neutral": ["Partly avoidable; the employee had a clear external opportunity.", "Typical career move at this level."],
          "positive": ["Unavoidable loss; good relationship maintained and a strong alumni candidate.", "Positive exit; the employee is likely to return in future."]}
def exit_text(x):
    c = x["country"]
    d1 = pick(rng, E_DRIVERS[x["primary_reason"]]).format(p=rng.choice([18, 22, 25, 30, 35]), h=rng.choice([4, 5, 6, 7]), place=pick(rng, PLACES))
    d2 = pick(rng, E_DRIVERS[x["secondary_reason"]]).format(p=rng.choice([15, 20, 28]), h=rng.choice([3, 4, 6]), place=pick(rng, PLACES))
    liked = ", ".join(rng.sample(LIKED, 2))
    sent = x["sentiment"]
    q = pick(rng, E_QUOTE[sent])
    tone = {"negative": "The conversation was tense at times and the employee was clearly frustrated.",
            "neutral": "The conversation was calm and matter-of-fact.",
            "positive": "The employee was warm and positive throughout the conversation."}[sent]
    lines = [f"### Exit interview {x['id']}",
             f"**Last working day:** {D(x['exit_date']).strftime('%d %B %Y')} · **Country:** {CNAME[c]} · **Office:** {x['office']} · **Work mode:** {x['work_mode']}",
             f"**Level:** {x['level']} · **Department:** {x['dept']} · **Tenure:** {x['tenure_years']} years · **Regretted loss:** {'Yes' if x['regretted'] else 'No'}",
             f"**Primary reason:** {EREASONS[x['primary_reason']]} · **Secondary reason:** {EREASONS[x['secondary_reason']]} · **Would rejoin:** {x['would_rejoin']}",
             "", f"**Interviewer notes.** {d1} {d2} They said they valued {liked}. {tone}", "",
             f"**What might have changed the decision.** {pick(rng, E_CHANGE[x['primary_reason']])}", "",
             f"**Notice and handover.** {pick(rng, E_NOTICE)}", "",
             f"**In their words.** \"{q}\"", "", f"**Suggestion for BragsLabs.** {pick(rng, E_SUGG)} {pick(rng, E_SUGG2)}", "",
             f"**HRBP assessment.** {pick(rng, E_HRBP[sent])} Eligible for rehire: {'No' if rng.random() < 0.04 else 'Yes'}.", ""]
    return "\n".join(lines)

# ======================================================================
# SURVEY COMMENTS (Pulse survey, June 2026)
# ======================================================================
STHEMES = ["hybrid_policy", "career_growth", "compensation", "manager_support", "workload", "learning", "tools_systems", "wellbeing", "inclusion", "recognition"]
ST_LABEL = {"hybrid_policy": "Hybrid and office days", "career_growth": "Career growth", "compensation": "Pay and benefits", "manager_support": "Manager support",
            "workload": "Workload", "learning": "Learning and development", "tools_systems": "Tools and systems", "wellbeing": "Wellbeing",
            "inclusion": "Inclusion and belonging", "recognition": "Recognition"}
S_TEXT = {
 ("hybrid_policy", "negative"): ["Three office days feels like a step backwards. My commute eats two hours and I get less deep work done in the office.",
                                 "The office-day increase was announced with little consultation. On anchor days there are not enough desks.",
                                 "I do not understand why the attendance rule changed when our results were fine with two days."],
 ("hybrid_policy", "neutral"): ["Three days is manageable for me, but the reason for the change could have been explained better.",
                                "Anchor days work when the whole team actually comes in; otherwise it is just a commute."],
 ("hybrid_policy", "positive"): ["I like seeing the team more often since the change. Planning sessions are better in person.",
                                 "Anchor days have improved collaboration in our team."],
 ("career_growth", "negative"): ["Promotion criteria are vague and it feels like visibility matters more than impact.", "I have been at the same level for three years with no clear path."],
 ("career_growth", "neutral"): ["Internal job postings are useful but there are few openings at my level."],
 ("career_growth", "positive"): ["My manager built a clear development plan with me and I got the stretch project I wanted."],
 ("compensation", "negative"): ["The increment this year did not keep up with inflation.", "Allowances are paid late and the payroll team is hard to reach."],
 ("compensation", "neutral"): ["Pay is fair for the market, but benefits information is hard to find."],
 ("compensation", "positive"): ["The health insurance and parental leave are genuinely good."],
 ("manager_support", "negative"): ["One-to-ones get cancelled all the time.", "My manager rarely gives feedback until review time."],
 ("manager_support", "neutral"): ["My manager is fine but very busy."],
 ("manager_support", "positive"): ["My manager is supportive and protects the team's time.", "I always feel I can raise concerns with my lead."],
 ("workload", "negative"): ["We are understaffed and evenings have become normal.", "Client calls outside core hours are wearing me down."],
 ("workload", "neutral"): ["Workload is high in release weeks but manageable otherwise."],
 ("workload", "positive"): ["The right to disconnect guidance actually changed behaviour in our team."],
 ("learning", "negative"): ["I never get time to use my learning budget."],
 ("learning", "neutral"): ["The learning platform has a lot of content but it is hard to find the right course."],
 ("learning", "positive"): ["The certification sponsorship helped me get my cloud certification.", "Learning budget is one of the best things here."],
 ("tools_systems", "negative"): ["The new expense module is painful; claims take twice as long.", "The HRMS is slow and leave balances are often wrong."],
 ("tools_systems", "neutral"): ["Tools are okay; desk booking could be simpler."],
 ("tools_systems", "positive"): ["IT support is quick and helpful."],
 ("wellbeing", "negative"): ["I feel burnt out and the wellbeing sessions do not address the cause."],
 ("wellbeing", "neutral"): ["Wellbeing allowance is nice but I rarely think to claim it."],
 ("wellbeing", "positive"): ["The EAP counselling helped me through a hard time."],
 ("inclusion", "negative"): ["Remote colleagues are often left out of decisions made in the office."],
 ("inclusion", "neutral"): ["ERGs are active but mostly in the larger offices."],
 ("inclusion", "positive"): ["I feel I can be myself at work here.", "The parents' network has been a great support."],
 ("recognition", "negative"): ["Recognition goes to the same few people who are always in the office."],
 ("recognition", "neutral"): ["Kudos points are fine but feel a bit transactional."],
 ("recognition", "positive"): ["Spot awards are given quickly and feel meaningful."],
}
S_EXTRA = {"negative": ["Please fix this.", "It is affecting morale.", "Several of us feel the same.", "I hope leadership reads this.", ""],
           "neutral": ["Just my view.", "Overall it is okay.", "", "Hope this helps."],
           "positive": ["Keep it up.", "Thank you.", "", "This makes me want to stay."]}

def gen_survey(target=3850):
    out = []
    tw = sum(VOLUME_W.values())
    for c in COUNTRIES:
        n = round(target * VOLUME_W[c] / tw)
        for i in range(n):
            th_w = {"hybrid_policy": 22, "career_growth": 13, "compensation": 13, "manager_support": 10, "workload": 11, "learning": 7,
                    "tools_systems": 10, "wellbeing": 6, "inclusion": 4, "recognition": 4}
            th = rng.choices(STHEMES, weights=[th_w[t] for t in STHEMES])[0]
            negp = {"hybrid_policy": 0.6, "tools_systems": 0.55, "workload": 0.5, "compensation": 0.45, "career_growth": 0.45}.get(th, 0.3)
            if c in ("AE", "AU", "SG") and th == "hybrid_policy": negp = 0.4
            r = rng.random()
            s = "negative" if r < negp else ("positive" if r > 1 - 0.3 else "neutral")
            enps = {"negative": rng.randint(0, 6), "neutral": rng.randint(5, 8), "positive": rng.randint(8, 10)}[s]
            out.append({"id": f"PULSE26-{c}-{i+1:04d}", "country": c, "office": office_for(c)[1], "theme": th, "sentiment": s, "enps_score": enps,
                        "work_mode": rng.choices(MODES, weights=MODE_W)[0], "level": rng.choices(LEVELS, weights=LEVEL_W)[0],
                        "dept": pick(rng, DEPTS), "tenure_band": rng.choice(["<1 year", "1–3 years", "3–5 years", "5+ years"])})
    return out

S_DETAIL = {"negative": ["In my team this has been raised in two retros without any change.", "Compared with last year, it feels worse.", "People are quietly looking at other options because of this.",
                          "The impact is biggest for those of us with caregiving responsibilities.", "It makes me less likely to recommend BragsLabs to friends."],
            "neutral": ["Some things have improved since last year, others not.", "It depends a lot on the manager and the client.", "I would like clearer communication on what is changing and why.",
                         "It is about the same as at my previous employer."],
            "positive": ["This is a big reason I stay.", "It has improved a lot over the past year.", "Colleagues in other offices say the same.", "It makes a real difference to my day-to-day work."]}
def survey_text(s):
    t = pick(rng, S_TEXT[(s["theme"], s["sentiment"])]) + " " + pick(rng, S_DETAIL[s["sentiment"]]) + " " + pick(rng, S_EXTRA[s["sentiment"]])
    return (f"**{s['id']}** · {s['office']} · {s['dept']} · {s['level']} · {s['work_mode']} · tenure {s['tenure_band']} · likelihood to recommend: {s['enps_score']}/10  \n"
            f"*Topic tagged by respondent:* {ST_LABEL[s['theme']]}  \n{t.strip()}\n")

# ======================================================================
# RENDER
# ======================================================================
def render():
    tickets, griev, exits, survey = gen_tickets(), gen_grievances(), gen_exits(), gen_survey()
    files = 0
    # tickets by country-month
    from collections import defaultdict
    g = defaultdict(list)
    for t in tickets: g[(t["country"], t["year"], t["month"])].append(t)
    for (c, y, m), ts in sorted(g.items()):
        ts.sort(key=lambda t: t["created"])
        for i, t in enumerate(ts): t["id"] = f"HD-{c}-{y}{m:02d}-{i+1:04d}"
        mname = date(y, m, 1).strftime("%B %Y")
        cats = defaultdict(int)
        for t in ts: cats[t["category"]] += 1
        body = [f"# HR helpdesk ticket log — {CNAME[c]}, {mname}", "",
                f"Export of HR helpdesk tickets opened by employees of {ENTITY[c]} in {mname}. Each entry records the request, the resolution and the employee's satisfaction rating (CSAT, 1–5). Employee identifiers are pseudonymised.", ""]
        body += [ticket_text(t) for t in ts]
        write_doc(f"tickets/{y}-{m:02d}_{c}.md", {"doc_id": f"TKT-{c}-{y}{m:02d}", "doc_type": "helpdesk_ticket_log", "company": COMPANY, "country": c,
                  "period": f"{y}-{m:02d}", "record_count": len(ts), "source_system": "BragsLabs HRMS Helpdesk"}, "\n".join(body)); files += 1
    g = defaultdict(list)
    for x in griev: g[(x["country"], x["year"], x["quarter"])].append(x)
    for (c, y, q), xs in sorted(g.items()):
        xs.sort(key=lambda x: x["filed"])
        for i, x in enumerate(xs): x["id"] = f"GRV-{c}-{y}Q{q}-{i+1:03d}"
        body = [f"# Grievance case register — {CNAME[c]}, Q{q} {y}", "",
                f"Confidential register of grievances filed by employees of {ENTITY[c]} between {quarter_bounds(y,q)[0].strftime('%d %B %Y')} and {quarter_bounds(y,q)[1].strftime('%d %B %Y')}, prepared by HR for the Grievance Redressal Committee. Harassment complaints are recorded only by outcome category; details are held by the relevant committee.", ""]
        body += [grievance_text(x) for x in xs]
        write_doc(f"grievances/{y}Q{q}_{c}.md", {"doc_id": f"GRV-{c}-{y}Q{q}", "doc_type": "grievance_register", "company": COMPANY, "country": c,
                  "period": f"{y}-Q{q}", "record_count": len(xs), "confidentiality": "HR confidential"}, "\n".join(body)); files += 1
    g = defaultdict(list)
    for x in exits: g[(x["country"], x["year"], x["quarter"])].append(x)
    for (c, y, q), xs in sorted(g.items()):
        xs.sort(key=lambda x: x["exit_date"])
        for i, x in enumerate(xs): x["id"] = f"EXIT-{c}-{y}Q{q}-{i+1:03d}"
        body = [f"# Exit interview notes — {CNAME[c]}, Q{q} {y}", "",
                f"Notes from exit interviews with employees of {ENTITY[c]} whose last working day fell in Q{q} {y}. Interviews were held by the HR business partner, in person or by video.", ""]
        body += [exit_text(x) for x in xs]
        write_doc(f"exit_notes/{y}Q{q}_{c}.md", {"doc_id": f"EXIT-{c}-{y}Q{q}", "doc_type": "exit_interview_notes", "company": COMPANY, "country": c,
                  "period": f"{y}-Q{q}", "record_count": len(xs)}, "\n".join(body)); files += 1
    g = defaultdict(list)
    for x in survey: g[x["country"]].append(x)
    for c, xs in g.items():
        body = [f"# Pulse survey 2026 — open comments, {CNAME[c]}", "",
                f"Verbatim open-text comments from the BragsLabs Pulse Survey run from 8 to 26 June 2026 for employees of {ENTITY[c]}. Respondents answered \"How likely are you to recommend BragsLabs as a place to work?\" (0–10) and could add a comment on a topic of their choice. Comments are unedited apart from removing names.", ""]
        body += [survey_text(x) for x in xs]
        write_doc(f"surveys/pulse2026_{c}.md", {"doc_id": f"PULSE26-{c}", "doc_type": "survey_comments", "company": COMPANY, "country": c,
                  "period": "2026-06", "record_count": len(xs), "survey": "Pulse Survey 2026"}, "\n".join(body)); files += 1
    save_ledger("tickets.json", tickets); save_ledger("grievances.json", griev); save_ledger("exit_notes.json", exits); save_ledger("survey_comments.json", survey)
    print("record files", files, "tickets", len(tickets), "grievances", len(griev), "exits", len(exits), "survey", len(survey))

if __name__ == "__main__":
    render()
