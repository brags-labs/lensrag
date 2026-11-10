"""Shared constants, ledger of policy facts and helpers for the BragsLabs HR corpus."""
import json, os, random, re, textwrap
from datetime import date, timedelta

ROOT = "/home/claude/bragslabs_corpus"
CORPUS = f"{ROOT}/corpus"
LEDGER = f"{ROOT}/ledger"
GOLD = f"{ROOT}/gold"
COMPANY = "BragsLabs"
DOMAIN = "bragslabs.com"
SEED = 20261105

COUNTRIES = ["US", "IN", "UK", "DE", "NL", "IE", "SG", "AE", "CA", "AU"]
CNAME = {"US": "United States", "IN": "India", "UK": "United Kingdom", "DE": "Germany",
         "NL": "Netherlands", "IE": "Ireland", "SG": "Singapore", "AE": "United Arab Emirates",
         "CA": "Canada", "AU": "Australia"}
ENTITY = {"US": "BragsLabs Inc.", "IN": "BragsLabs India Pvt. Ltd.", "UK": "BragsLabs UK Ltd",
          "DE": "BragsLabs GmbH", "NL": "BragsLabs B.V.", "IE": "BragsLabs Ireland Ltd",
          "SG": "BragsLabs Pte. Ltd.", "AE": "BragsLabs FZ-LLC", "CA": "BragsLabs Canada Inc.",
          "AU": "BragsLabs Pty Ltd"}
CURRENCY = {"US": "USD", "IN": "INR", "UK": "GBP", "DE": "EUR", "NL": "EUR", "IE": "EUR",
            "SG": "SGD", "AE": "AED", "CA": "CAD", "AU": "AUD"}
CSYM = {"USD": "USD ", "INR": "₹", "GBP": "£", "EUR": "€", "SGD": "SGD ", "AED": "AED ",
        "CAD": "CAD ", "AUD": "AUD "}
HR_LEAD = {"US": "Michael Turner", "IN": "Rohit Sharma", "UK": "James Whitfield", "DE": "Thomas Becker",
           "NL": "Sanne Jansen", "IE": "Siobhán Murphy", "SG": "Rachel Lim", "AE": "Fatima Al Mansoori",
           "CA": "Emily Tremblay", "AU": "Olivia Brown"}
# Countries present in each manual version
VERSION_COUNTRIES = {
    "v1.0": ["US", "IN", "UK", "DE", "NL", "SG"],
    "v2.0": ["US", "IN", "UK", "DE", "NL", "IE", "SG", "CA"],
    "v3.0": COUNTRIES,
}
VERSION_DATE = {"v1.0": "2022-04-01", "v2.0": "2024-01-01", "v3.0": "2026-11-01"}
VERSION_YEAR = {"v1.0": 2022, "v2.0": 2024, "v3.0": 2026}
ADDENDUM_ORDER = ["US", "IN", "UK", "DE", "NL", "IE", "SG", "AE", "CA", "AU"]

OFFICES = [
    # code, city, country, opened, headcount_2026, floors, parking, gym, creche, address
    ("BOS", "Boston", "US", 2015, 640, 6, 180, True, False, "200 Summit Avenue, Suite 1400, Boston, MA 02110"),
    ("AUS", "Austin", "US", 2019, 310, 3, 140, True, False, "1100 Congress Lane, Floor 9, Austin, TX 78701"),
    ("BLR", "Bengaluru", "IN", 2016, 2150, 11, 420, True, True, "Tower B, Embassy Crest Tech Park, Outer Ring Road, Bengaluru 560103"),
    ("HYD", "Hyderabad", "IN", 2018, 1180, 7, 260, True, True, "Block 4, Raidurg Knowledge Park, HITEC City, Hyderabad 500081"),
    ("PNQ", "Pune", "IN", 2020, 760, 5, 150, False, True, "Wing C, Riverside Business Bay, Kharadi, Pune 411014"),
    ("MAA", "Chennai", "IN", 2022, 520, 4, 110, False, True, "Level 6, Olympia Tidal Square, OMR, Chennai 600113"),
    ("LON", "London", "UK", 2017, 430, 4, 25, True, False, "18 Finsbury Crescent, London EC2M 7AB"),
    ("BER", "Berlin", "DE", 2018, 260, 3, 40, False, False, "Friedrichstraße 148, 10117 Berlin"),
    ("AMS", "Amsterdam", "NL", 2019, 210, 2, 30, True, False, "Zuidas Plaza 12, 1082 MS Amsterdam"),
    ("DUB", "Dublin", "IE", 2023, 180, 2, 35, False, False, "4 Grand Canal Quay, Dublin 2, D02 X9Y4"),
    ("SIN", "Singapore", "SG", 2017, 340, 3, 45, True, False, "8 Marina Vista, #21-01, Singapore 018985"),
    ("DXB", "Dubai", "AE", 2025, 150, 2, 60, True, False, "Building 7, Office 402, Dubai Internet City, Dubai"),
    ("YYZ", "Toronto", "CA", 2023, 230, 2, 50, False, False, "330 Bay Street, Suite 1800, Toronto, ON M5H 2S8"),
    ("SYD", "Sydney", "AU", 2025, 160, 2, 30, True, False, "Level 14, 100 Harbour Street, Sydney NSW 2000"),
]
OFFICE_BY_COUNTRY = {}
for o in OFFICES:
    OFFICE_BY_COUNTRY.setdefault(o[2], []).append(o)
HEADCOUNT = {c: sum(o[4] for o in OFFICE_BY_COUNTRY[c]) for c in COUNTRIES}

# ---------------------------------------------------------------------------
# Policy-value ledger: company entitlement per country per version.
# Units are explicit so gold answers can be computed in code.
# ---------------------------------------------------------------------------
POLICY = {
 # attribute: {country: {version: value}}
 "annual_leave_days": {   # paid annual leave in working days, excl. public holidays
   "US": {"v1.0": 15, "v2.0": 18, "v3.0": 20}, "IN": {"v1.0": 15, "v2.0": 18, "v3.0": 18},
   "UK": {"v1.0": 23, "v2.0": 25, "v3.0": 25}, "DE": {"v1.0": 26, "v2.0": 27, "v3.0": 28},
   "NL": {"v1.0": 25, "v2.0": 25, "v3.0": 25}, "IE": {"v2.0": 23, "v3.0": 25},
   "SG": {"v1.0": 14, "v2.0": 16, "v3.0": 18}, "AE": {"v3.0": 22},
   "CA": {"v2.0": 15, "v3.0": 15}, "AU": {"v3.0": 20}},
 "paid_sick_days": {
   "US": {"v1.0": 6, "v2.0": 8, "v3.0": 10}, "IN": {"v1.0": 7, "v2.0": 8, "v3.0": 8},
   "UK": {"v1.0": 5, "v2.0": 10, "v3.0": 10}, "DE": {"v1.0": 30, "v2.0": 30, "v3.0": 30},
   "NL": {"v1.0": 260, "v2.0": 260, "v3.0": 260}, "IE": {"v2.0": 5, "v3.0": 10},
   "SG": {"v1.0": 14, "v2.0": 14, "v3.0": 14}, "AE": {"v3.0": 20},
   "CA": {"v2.0": 7, "v3.0": 10}, "AU": {"v3.0": 12}},
 "birth_parent_leave_weeks_full_pay": {
   "US": {"v1.0": 12, "v2.0": 14, "v3.0": 16}, "IN": {"v1.0": 26, "v2.0": 26, "v3.0": 26},
   "UK": {"v1.0": 12, "v2.0": 14, "v3.0": 16}, "DE": {"v1.0": 14, "v2.0": 14, "v3.0": 16},
   "NL": {"v1.0": 16, "v2.0": 16, "v3.0": 16}, "IE": {"v2.0": 14, "v3.0": 16},
   "SG": {"v1.0": 16, "v2.0": 16, "v3.0": 16}, "AE": {"v3.0": 16},
   "CA": {"v2.0": 14, "v3.0": 16}, "AU": {"v3.0": 16}},
 "partner_leave_weeks_full_pay": {
   "US": {"v1.0": 4, "v2.0": 6, "v3.0": 8}, "IN": {"v1.0": 1, "v2.0": 1.4, "v3.0": 2},
   "UK": {"v1.0": 2, "v2.0": 2, "v3.0": 2}, "DE": {"v1.0": 1, "v2.0": 2, "v3.0": 2},
   "NL": {"v1.0": 1, "v2.0": 2, "v3.0": 2}, "IE": {"v2.0": 2, "v3.0": 2},
   "SG": {"v1.0": 2, "v2.0": 2, "v3.0": 2}, "AE": {"v3.0": 2},
   "CA": {"v2.0": 4, "v3.0": 6}, "AU": {"v3.0": 4}},
 "notice_period_senior_days": {  # L4 and above, company contractual notice, calendar days
   "US": {"v1.0": 14, "v2.0": 14, "v3.0": 14}, "IN": {"v1.0": 90, "v2.0": 90, "v3.0": 90},
   "UK": {"v1.0": 90, "v2.0": 90, "v3.0": 90}, "DE": {"v1.0": 90, "v2.0": 90, "v3.0": 90},
   "NL": {"v1.0": 60, "v2.0": 60, "v3.0": 60}, "IE": {"v2.0": 90, "v3.0": 90},
   "SG": {"v1.0": 60, "v2.0": 60, "v3.0": 60}, "AE": {"v3.0": 60},
   "CA": {"v2.0": 56, "v3.0": 56}, "AU": {"v3.0": 90}},
 "standard_weekly_hours": {
   "US": {"v1.0": 40, "v2.0": 40, "v3.0": 40}, "IN": {"v1.0": 40, "v2.0": 40, "v3.0": 40},
   "UK": {"v1.0": 37.5, "v2.0": 37.5, "v3.0": 37.5}, "DE": {"v1.0": 40, "v2.0": 40, "v3.0": 40},
   "NL": {"v1.0": 40, "v2.0": 40, "v3.0": 40}, "IE": {"v2.0": 39, "v3.0": 39},
   "SG": {"v1.0": 40, "v2.0": 40, "v3.0": 40}, "AE": {"v3.0": 40},
   "CA": {"v2.0": 37.5, "v3.0": 37.5}, "AU": {"v3.0": 38}},
 "employer_retirement_contribution_pct": {
   "US": {"v1.0": 4, "v2.0": 4, "v3.0": 5}, "IN": {"v1.0": 12, "v2.0": 12, "v3.0": 12},
   "UK": {"v1.0": 4, "v2.0": 5, "v3.0": 5}, "DE": {"v1.0": 15, "v2.0": 15, "v3.0": 20},
   "NL": {"v1.0": 8, "v2.0": 10, "v3.0": 10}, "IE": {"v2.0": 5, "v3.0": 6},
   "SG": {"v1.0": 17, "v2.0": 17, "v3.0": 17}, "AE": {"v3.0": 0},
   "CA": {"v2.0": 4, "v3.0": 5}, "AU": {"v3.0": 12}},
 "public_holidays": {
   "US": {"v1.0": 10, "v2.0": 11, "v3.0": 11}, "IN": {"v1.0": 10, "v2.0": 10, "v3.0": 10},
   "UK": {"v1.0": 8, "v2.0": 8, "v3.0": 8}, "DE": {"v1.0": 10, "v2.0": 10, "v3.0": 10},
   "NL": {"v1.0": 8, "v2.0": 8, "v3.0": 8}, "IE": {"v2.0": 10, "v3.0": 10},
   "SG": {"v1.0": 11, "v2.0": 11, "v3.0": 11}, "AE": {"v3.0": 13},
   "CA": {"v2.0": 11, "v3.0": 11}, "AU": {"v3.0": 10}},
 "life_cover_multiple": {
   "US": {"v1.0": 2, "v2.0": 2, "v3.0": 2}, "IN": {"v1.0": 3, "v2.0": 3, "v3.0": 3},
   "UK": {"v1.0": 4, "v2.0": 4, "v3.0": 4}, "DE": {"v1.0": 2, "v2.0": 2, "v3.0": 2},
   "NL": {"v1.0": 2, "v2.0": 2, "v3.0": 2}, "IE": {"v2.0": 4, "v3.0": 4},
   "SG": {"v1.0": 3, "v2.0": 3, "v3.0": 3}, "AE": {"v3.0": 2},
   "CA": {"v2.0": 2, "v3.0": 2}, "AU": {"v3.0": 3}},
}
ATTR_LABEL = {
 "annual_leave_days": "paid annual leave (working days)",
 "paid_sick_days": "paid sick leave at full pay (working days)",
 "birth_parent_leave_weeks_full_pay": "birth-parent leave at full pay (weeks)",
 "partner_leave_weeks_full_pay": "partner / non-birth-parent leave at full pay (weeks)",
 "notice_period_senior_days": "contractual notice period for L4 and above (calendar days)",
 "standard_weekly_hours": "standard working hours per week",
 "employer_retirement_contribution_pct": "employer retirement contribution (% of pay)",
 "public_holidays": "paid public holidays per year",
 "life_cover_multiple": "life cover (multiple of annual base salary)",
}
# Global (India-chapter) values that changed between versions
GLOBAL = {
 "hybrid_office_days": {"v1.0": 2, "v2.0": 2, "v3.0": 3},
 "anchor_days": {"v1.0": 1, "v2.0": 2, "v3.0": 2},
 "work_from_abroad_days": {"v1.0": 0, "v2.0": 10, "v3.0": 20},
 "remote_setup_allowance_inr": {"v1.0": 15000, "v2.0": 20000, "v3.0": 25000},
 "hybrid_setup_allowance_inr": {"v1.0": 6000, "v2.0": 8000, "v3.0": 10000},
 "remote_internet_allowance_inr": {"v1.0": 1000, "v2.0": 1200, "v3.0": 1500},
 "hybrid_internet_allowance_inr": {"v1.0": 600, "v2.0": 800, "v3.0": 1000},
 "night_shift_allowance_inr": {"v1.0": 400, "v2.0": 500, "v3.0": 600},
 "late_shift_allowance_inr": {"v1.0": 250, "v2.0": 300, "v3.0": 400},
 "afternoon_shift_allowance_inr": {"v1.0": 150, "v2.0": 200, "v3.0": 250},
 "learning_budget_l1_l3_inr": {"v1.0": 15000, "v2.0": 20000, "v3.0": 25000},
 "learning_budget_l4_l6_inr": {"v1.0": 25000, "v2.0": 30000, "v3.0": 40000},
 "learning_budget_l7_inr": {"v1.0": 50000, "v2.0": 60000, "v3.0": 75000},
 "wellbeing_allowance_inr": {"v1.0": 5000, "v2.0": 8000, "v3.0": 12000},
 "health_sum_insured_inr": {"v1.0": 300000, "v2.0": 400000, "v3.0": 500000},
 "remote_cap_pct": {"v1.0": 10, "v2.0": 15, "v3.0": 20},
 "india_paternity_working_days": {"v1.0": 5, "v2.0": 7, "v3.0": 10},
 "referral_bonus_min_inr": {"v1.0": 15000, "v2.0": 20000, "v3.0": 25000},
 "referral_bonus_max_inr": {"v1.0": 40000, "v2.0": 50000, "v3.0": 60000},
 "coworking_budget_inr": {"v1.0": 15000, "v2.0": 20000, "v3.0": 30000},
 "global_min_annual_leave_days": {"v1.0": 15, "v2.0": 15, "v3.0": 18},
 "global_min_sick_days": {"v1.0": 7, "v2.0": 8, "v3.0": 10},
 "global_min_birth_parent_weeks": {"v1.0": 12, "v2.0": 14, "v3.0": 16},
}

def money(country, amount):
    cur = CURRENCY[country]
    if cur == "INR":
        return "₹" + indian(amount)
    return f"{CSYM[cur]}{amount:,}"

def indian(n):
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:]); head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail

def rename(text):
    """Apply the BragsLabs rename (decision of 5 Nov 2026)."""
    subs = [
        ("Global Data Science and AI Company Inc.", "BragsLabs Inc."),
        ("Global Data Science and AI Company Pvt. Ltd.", "BragsLabs India Pvt. Ltd."),
        ("Global Data Science and AI Company UK Ltd", "BragsLabs UK Ltd"),
        ("Global Data Science and AI Company GmbH", "BragsLabs GmbH"),
        ("Global Data Science and AI Company B.V.", "BragsLabs B.V."),
        ("Global Data Science and AI Company Ireland Ltd", "BragsLabs Ireland Ltd"),
        ("Global Data Science and AI Company Pte. Ltd.", "BragsLabs Pte. Ltd."),
        ("Global Data Science and AI Company FZ-LLC", "BragsLabs FZ-LLC"),
        ("Global Data Science and AI Company Canada Inc.", "BragsLabs Canada Inc."),
        ("Global Data Science and AI Company Pty Ltd", "BragsLabs Pty Ltd"),
        ("Global Data Science and AI Company", "BragsLabs"),
        ("gdsai.com", DOMAIN), ("ethicsline.gdsai", "ethicsline.bragslabs"),
    ]
    for a, b in subs:
        text = text.replace(a, b)
    return text

def front_matter(meta):
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, (list, dict)):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{k}: null")
        else:
            sv = str(v)
            if re.search(r"[:#\[\]{}&*!|>'\"%@`,]", sv) or sv != sv.strip():
                sv = json.dumps(sv, ensure_ascii=False)
            lines.append(f"{k}: {sv}")
    lines.append("---\n")
    return "\n".join(lines)

def write_doc(relpath, meta, body):
    path = os.path.join(CORPUS, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    meta = {"doc_id": meta.get("doc_id") or os.path.splitext(os.path.basename(relpath))[0], **meta}
    with open(path, "w", encoding="utf-8") as f:
        body = re.sub(r"\b(Ltd|Inc|Pte|B\.V)\.\.", r"\1.", body)
        f.write(front_matter(meta) + body.strip() + "\n")
    return path

def save_ledger(name, obj):
    os.makedirs(LEDGER, exist_ok=True)
    with open(os.path.join(LEDGER, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, default=str)

def pick(rng, seq):
    return seq[rng.randrange(len(seq))]

def wc(text):
    return sum(1 for w in text.split() if re.search(r"\w", w))
