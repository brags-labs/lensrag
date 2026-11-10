"""Timeline of policy events and circulars (2022-2026) — the ground truth for date reasoning."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *

# Each circular: id, issued, effective, countries, topic, attribute/key, old, new, summary, kind
# kind: change (incorporated into the next manual version), interim, future (effective after v3.0), reminder, correction
CIRCULARS = [
 # ---- 2022 (after v1.0) ----
 ("HR-CIR-2022-01", "2022-04-05", "2022-04-01", ["ALL"], "Launch of Global HR Policy Manual v1.0", None, None, None, "reminder"),
 ("HR-CIR-2022-02", "2022-05-16", "2022-06-01", ["IN"], "Hybrid pilot: two office days a week for Bengaluru and Hyderabad", "hybrid_office_days", None, 2, "change"),
 ("HR-CIR-2022-03", "2022-07-04", "2022-07-15", ["ALL"], "Monsoon and severe-weather work-from-home protocol", None, None, None, "reminder"),
 ("HR-CIR-2022-04", "2022-08-22", "2022-10-01", ["IN"], "Revised night shift allowance", "night_shift_allowance_inr", 400, 450, "interim"),
 ("HR-CIR-2022-05", "2022-09-12", "2022-10-01", ["ALL"], "Annual benefits enrolment window 2022", None, None, None, "reminder"),
 ("HR-CIR-2022-06", "2022-10-10", "2022-11-01", ["UK"], "UK pension employer contribution increase", "employer_retirement_contribution_pct", 4, 5, "change"),
 ("HR-CIR-2022-07", "2022-11-21", "2023-01-01", ["IN"], "Earned leave increase to 18 days", "annual_leave_days", 15, 18, "change"),
 ("HR-CIR-2022-08", "2022-12-05", "2023-01-01", ["ALL"], "Public holiday calendars for 2023", None, None, None, "reminder"),
 # ---- 2023 ----
 ("HR-CIR-2023-01", "2023-01-16", "2023-02-01", ["ALL"], "Work from another country: 10-day allowance introduced", "work_from_abroad_days", 0, 10, "change"),
 ("HR-CIR-2023-02", "2023-02-20", "2023-03-01", ["IE"], "Opening of the Dublin office and Irish entity terms", None, None, None, "reminder"),
 ("HR-CIR-2023-03", "2023-03-27", "2023-04-01", ["US"], "US PTO increase to 18 days", "annual_leave_days", 15, 18, "change"),
 ("HR-CIR-2023-04", "2023-05-08", "2023-06-01", ["ALL"], "Learning budget revision", "learning_budget_l1_l3_inr", 15000, 20000, "change"),
 ("HR-CIR-2023-05", "2023-06-19", "2023-07-01", ["CA"], "Opening of the Toronto office and Canadian entity terms", None, None, None, "reminder"),
 ("HR-CIR-2023-06", "2023-07-24", "2023-08-01", ["IN"], "Night shift allowance raised to ₹500", "night_shift_allowance_inr", 450, 500, "change"),
 ("HR-CIR-2023-07", "2023-08-28", "2023-09-01", ["SG"], "Singapore annual leave increase to 16 days", "annual_leave_days", 14, 16, "change"),
 ("HR-CIR-2023-08", "2023-09-18", "2023-10-01", ["ALL"], "Annual benefits enrolment window 2023", None, None, None, "reminder"),
 ("HR-CIR-2023-09", "2023-10-30", "2024-01-01", ["ALL"], "Global minimum birth-parent leave raised to 14 weeks", "global_min_birth_parent_weeks", 12, 14, "change"),
 ("HR-CIR-2023-10", "2023-12-11", "2024-01-01", ["ALL"], "Launch of Global HR Policy Manual v2.0", None, None, None, "reminder"),
 # ---- 2024 ----
 ("HR-CIR-2024-01", "2024-01-22", "2024-02-01", ["ALL"], "Right to disconnect guidance for managers", None, None, None, "reminder"),
 ("HR-CIR-2024-02", "2024-03-04", "2024-04-01", ["IN"], "Wellbeing allowance raised to ₹10,000", "wellbeing_allowance_inr", 8000, 10000, "interim"),
 ("HR-CIR-2024-03", "2024-04-15", "2024-05-01", ["UK"], "UK flexible working requests from day one", None, None, None, "reminder"),
 ("HR-CIR-2024-04", "2024-05-27", "2024-07-01", ["ALL"], "Remote internet allowance revision", "remote_internet_allowance_inr", 1200, 1500, "change"),
 ("HR-CIR-2024-05", "2024-06-24", "2024-07-01", ["DE"], "Germany holiday entitlement increase to 28 days", "annual_leave_days", 27, 28, "change"),
 ("HR-CIR-2024-06", "2024-07-29", "2024-08-01", ["ALL"], "Phishing simulation and security training cycle", None, None, None, "reminder"),
 ("HR-CIR-2024-07", "2024-08-19", "2024-09-01", ["IE"], "Ireland pension employer contribution to 6%", "employer_retirement_contribution_pct", 5, 6, "change"),
 ("HR-CIR-2024-08", "2024-09-16", "2024-10-01", ["ALL"], "Annual benefits enrolment window 2024", None, None, None, "reminder"),
 ("HR-CIR-2024-09", "2024-10-21", "2024-11-01", ["IN"], "Health insurance sum insured raised to ₹5,00,000", "health_sum_insured_inr", 400000, 500000, "change"),
 ("HR-CIR-2024-10", "2024-11-25", "2025-01-01", ["US"], "US PTO increase to 20 days and 401(k) match to 5%", "annual_leave_days", 18, 20, "change"),
 ("HR-CIR-2024-11", "2024-12-09", "2025-01-01", ["ALL"], "Public holiday calendars for 2025", None, None, None, "reminder"),
 # ---- 2025 ----
 ("HR-CIR-2025-01", "2025-01-13", "2025-02-01", ["AE"], "Opening of the Dubai office and UAE entity terms", None, None, None, "reminder"),
 ("HR-CIR-2025-02", "2025-02-24", "2025-03-01", ["AU"], "Opening of the Sydney office and Australian entity terms", None, None, None, "reminder"),
 ("HR-CIR-2025-03", "2025-03-31", "2025-04-01", ["ALL"], "Work from another country allowance raised to 20 days", "work_from_abroad_days", 10, 20, "change"),
 ("HR-CIR-2025-04", "2025-05-05", "2025-06-01", ["SG"], "Singapore annual leave increase to 18 days", "annual_leave_days", 16, 18, "change"),
 ("HR-CIR-2025-05", "2025-06-16", "2025-07-01", ["IN"], "India paternity leave raised to 10 working days", "india_paternity_working_days", 7, 10, "change"),
 ("HR-CIR-2025-06", "2025-07-21", "2025-08-01", ["ALL"], "Learning budgets revised for all levels", "learning_budget_l1_l3_inr", 20000, 25000, "change"),
 ("HR-CIR-2025-07", "2025-08-25", "2025-09-01", ["IE"], "Ireland annual leave increase to 25 days", "annual_leave_days", 23, 25, "change"),
 ("HR-CIR-2025-08", "2025-09-15", "2025-10-01", ["ALL"], "Annual benefits enrolment window 2025", None, None, None, "reminder"),
 ("HR-CIR-2025-09", "2025-10-20", "2025-11-01", ["IN"], "New employee transport vendor for Bengaluru", None, None, None, "reminder"),
 ("HR-CIR-2025-10", "2025-12-01", "2026-01-01", ["IN"], "Night shift allowance raised to ₹600", "night_shift_allowance_inr", 500, 600, "change"),
 ("HR-CIR-2025-11", "2025-12-15", "2026-01-01", ["ALL"], "Public holiday calendars for 2026", None, None, None, "reminder"),
 # ---- 2026 ----
 ("HR-CIR-2026-01", "2026-01-12", "2026-02-01", ["ALL"], "Global minimum sick leave raised to 10 days", "global_min_sick_days", 8, 10, "change"),
 ("HR-CIR-2026-02", "2026-02-02", "2026-02-15", ["CA"], "Canada sick and personal days raised to 10", "paid_sick_days", 7, 10, "change"),
 ("HR-CIR-2026-03", "2026-02-16", "2026-04-06", ["UK"], "UK statutory sick pay and paternity leave from day one", None, None, None, "change"),
 ("HR-CIR-2026-04", "2026-03-02", "2026-04-01", ["ALL"], "Hybrid office attendance raised to three days a week", "hybrid_office_days", 2, 3, "change"),
 ("HR-CIR-2026-05", "2026-03-23", "2026-04-01", ["ALL"], "Hybrid attendance: transition and exceptions", "hybrid_office_days", 2, 3, "reminder"),
 ("HR-CIR-2026-06", "2026-04-20", "2026-05-11", ["ALL"], "Migration to the new HRMS expense module", None, None, None, "reminder"),
 ("HR-CIR-2026-07", "2026-05-18", "2026-06-01", ["IN"], "Wellbeing allowance raised to ₹12,000", "wellbeing_allowance_inr", 10000, 12000, "change"),
 ("HR-CIR-2026-08", "2026-06-08", "2026-07-01", ["AU"], "Australia Paid Parental Leave rises to 26 weeks", None, None, None, "change"),
 ("HR-CIR-2026-09", "2026-06-29", "2026-07-01", ["DE"], "Germany company pension subsidy raised to 20%", "employer_retirement_contribution_pct", 15, 20, "change"),
 ("HR-CIR-2026-10", "2026-07-13", "2026-08-01", ["ALL"], "Remote cap raised to 20% of business-unit headcount", "remote_cap_pct", 15, 20, "change"),
 ("HR-CIR-2026-11", "2026-08-10", "2026-09-01", ["CA"], "Canada non-birth parent top-up extended to 6 weeks", "partner_leave_weeks_full_pay", 4, 6, "change"),
 ("HR-CIR-2026-12", "2026-08-24", "2026-09-01", ["ALL"], "Correction: India sick leave versus the global minimum", "paid_sick_days", 8, 10, "correction"),
 ("HR-CIR-2026-13", "2026-09-14", "2026-10-01", ["ALL"], "Annual benefits enrolment window 2026", None, None, None, "reminder"),
 ("HR-CIR-2026-14", "2026-09-21", "2027-01-01", ["IN"], "Night shift allowance to rise to ₹700 from January 2027", "night_shift_allowance_inr", 600, 700, "future"),
 ("HR-CIR-2026-15", "2026-10-05", "2027-01-01", ["UK"], "UK annual leave to rise to 27 days from January 2027", "annual_leave_days", 25, 27, "future"),
 ("HR-CIR-2026-16", "2026-10-12", "2027-04-01", ["SG"], "Singapore employer CPF top-up to 18% from April 2027", "employer_retirement_contribution_pct", 17, 18, "future"),
 ("HR-CIR-2026-17", "2026-10-19", "2026-11-01", ["ALL"], "Launch of Global HR Policy Manual v3.0", None, None, None, "reminder"),
 ("HR-CIR-2026-18", "2026-10-26", "2027-01-01", ["AE"], "UAE annual air ticket extended to L4 employees", None, None, None, "future"),
 ("HR-CIR-2026-19", "2026-10-28", "2027-01-01", ["NL"], "Netherlands annual leave to rise to 26 days from January 2027", "annual_leave_days", 25, 26, "future"),
 ("HR-CIR-2026-20", "2026-10-30", "2026-11-01", ["ALL"], "Public holiday calendars for 2027 (provisional)", None, None, None, "reminder"),
]
assert len(CIRCULARS) == 60, len(CIRCULARS)

KEY_EVENTS = {
 "hybrid_3_days": {"announced": "2026-03-02", "effective": "2026-04-01", "circular": "HR-CIR-2026-04"},
 "expense_migration": {"effective": "2026-05-11", "circular": "HR-CIR-2026-06"},
 "india_night_600": {"effective": "2026-01-01", "circular": "HR-CIR-2025-10"},
 "uk_ssp_day_one": {"effective": "2026-04-06", "circular": "HR-CIR-2026-03"},
 "au_ppl_26": {"effective": "2026-07-01", "circular": "HR-CIR-2026-08"},
 "blr_transport_vendor": {"effective": "2025-11-01", "circular": "HR-CIR-2025-09"},
}

# Planted conflicts and stale statements (for conflict-detection evaluation)
CONFLICTS = [
 {"id": "CF-01", "kind": "intra_manual", "description": "Chapter 15.1 (v3.0) gives India 8 paid sick days, below the 10-day global minimum in Chapter 37.1; circular HR-CIR-2026-12 states the global floor applies, so India employees are entitled to 10 days.",
  "docs": ["POL-v3.0-CH15", "POL-v3.0-CH37", "HR-CIR-2026-12"], "resolution": 10},
 {"id": "CF-02", "kind": "future_circular", "description": "Manual v3.0 sets the India night shift allowance at ₹600 per night; HR-CIR-2026-14 raises it to ₹700 only from 1 January 2027.", "docs": ["POL-v3.0-CH12", "HR-CIR-2026-14"], "resolution": "₹600 until 31 Dec 2026, ₹700 from 1 Jan 2027"},
 {"id": "CF-03", "kind": "future_circular", "description": "UK annual leave is 25 days in v3.0; HR-CIR-2026-15 raises it to 27 days from 1 January 2027.", "docs": ["POL-v3.0-CH40", "HR-CIR-2026-15"], "resolution": "25 until 31 Dec 2026, 27 from 1 Jan 2027"},
 {"id": "CF-04", "kind": "future_circular", "description": "Netherlands annual leave is 25 days in v3.0; HR-CIR-2026-19 raises it to 26 days from 1 January 2027.", "docs": ["POL-v3.0-CH42", "HR-CIR-2026-19"], "resolution": "25 until 31 Dec 2026, 26 from 1 Jan 2027"},
 {"id": "CF-05", "kind": "future_circular", "description": "Singapore employer CPF top-up rises from 17% to 18% only from 1 April 2027 (HR-CIR-2026-16).", "docs": ["POL-v3.0-CH44", "HR-CIR-2026-16"], "resolution": "17% until 31 Mar 2027"},
 {"id": "CF-06", "kind": "stale_faq", "description": "FAQ-IN-COUNTRY states 7 days of paternity leave (v2.0 value); v3.0 and HR-CIR-2025-05 give 10 working days.", "docs": ["FAQ-IN-COUNTRY", "POL-v3.0-CH16", "HR-CIR-2025-05"], "resolution": 10},
 {"id": "CF-07", "kind": "stale_faq", "description": "FAQ-HYBRID still says hybrid employees attend 2 office days a week; HR-CIR-2026-04 and v3.0 require 3 days from 1 April 2026.", "docs": ["FAQ-HYBRID", "POL-v3.0-CH09", "HR-CIR-2026-04"], "resolution": 3},
 {"id": "CF-08", "kind": "stale_handbook", "description": "The London office handbook says UK employees receive 23 days' annual leave (v1.0 value); v3.0 gives 25.", "docs": ["HB-LON", "POL-v3.0-CH40"], "resolution": 25},
 {"id": "CF-09", "kind": "stale_handbook", "description": "The Pune office handbook lists a ₹500 night shift allowance (v2.0 value); v3.0 gives ₹600.", "docs": ["HB-PNQ", "POL-v3.0-CH12", "HR-CIR-2025-10"], "resolution": 600},
 {"id": "CF-10", "kind": "stale_benefits", "description": "The Singapore benefits summary says 16 days' annual leave (v2.0 value); v3.0 and HR-CIR-2025-04 give 18.", "docs": ["BEN-SG", "POL-v3.0-CH44", "HR-CIR-2025-04"], "resolution": 18},
 {"id": "CF-11", "kind": "version", "description": "Hybrid office days: 2 (v1.0, v2.0) vs 3 (v3.0). Legitimate update, not a conflict.", "docs": ["POL-v1.0-CH09", "POL-v2.0-CH09", "POL-v3.0-CH09"], "resolution": 3},
 {"id": "CF-12", "kind": "version", "description": "Work from another country: not permitted (v1.0), 10 days (v2.0), 20 days (v3.0). Legitimate update.", "docs": ["POL-v1.0-CH10", "POL-v2.0-CH10", "POL-v3.0-CH10"], "resolution": 20},
]

if __name__ == "__main__":
    save_ledger("circulars.json", [dict(zip(["id","issued","effective","countries","topic","attribute","old","new","kind"], c)) for c in CIRCULARS])
    save_ledger("key_events.json", KEY_EVENTS)
    save_ledger("conflicts.json", CONFLICTS)
    print("ok")
