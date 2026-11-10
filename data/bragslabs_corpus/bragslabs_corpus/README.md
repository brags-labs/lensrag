# BragsLabs HR corpus (LensRAG benchmark) — version 1.0

A synthetic enterprise HR document collection for a fictional multinational, **BragsLabs**, built to test local and corpus-level (aggregation) retrieval. 500 Markdown files, about **1.52 million words** (body text, alphanumeric tokens). No real people or employee data: all names, IDs, contacts and records are fictional.

Built 5 November 2026. Company renamed from "Global Data Science and AI Company" to BragsLabs; domain bragslabs.com.

## Contents

| Folder | Files | Words | What it is |
| --- | --- | --- | --- |
| `corpus/policy/v3.0` | 47 | 41,238 | Current Global HR Policy Manual (effective 1 Nov 2026), one file per chapter; 10 country addenda (Ch 38–47) |
| `corpus/policy/v2.0` | 45 | 39,058 | Superseded version (effective 1 Jan 2024), 8 countries |
| `corpus/policy/v1.0` | 41 | 35,350 | Superseded version (effective 1 Apr 2022), 6 countries, no cross-border or comparison chapter |
| `corpus/circulars` | 60 | 42,517 | HR circulars 2022–2026: value changes, reminders, a correction, and 6 announced future changes (effective 2027) |
| `corpus/faqs` | 30 | 39,188 | 20 topic FAQs and 10 country FAQs (paraphrased policy text; deliberate near-duplicates) |
| `corpus/handbooks` | 14 | 13,338 | Office handbooks (Boston, Austin, Bengaluru, Hyderabad, Pune, Chennai, London, Berlin, Amsterdam, Dublin, Singapore, Dubai, Toronto, Sydney) |
| `corpus/benefits` | 10 | 13,813 | 2026 benefits summary per country |
| `corpus/reports` | 3 | 9,189 | Policy change log v1→v3 and annual HR reports 2025, 2026 (**retrieval-excluded**) |
| `corpus/tickets` | 120 | 714,866 | HR helpdesk ticket logs, 10 countries × 12 months (Nov 2025–Oct 2026), 6,038 tickets |
| `corpus/grievances` | 80 | 243,476 | Grievance registers, 10 countries × 8 quarters (Q4 2024–Q3 2026), 1,697 cases |
| `corpus/exit_notes` | 40 | 160,966 | Exit interview notes, 10 countries × 4 quarters (Q4 2025–Q3 2026), 960 interviews |
| `corpus/surveys` | 10 | 169,387 | Pulse Survey June 2026 open comments, one file per country, 3,850 comments |

Every file starts with YAML front matter (`doc_id`, `doc_type`, `country`, `version`, `effective_date`, `period`, `status`, `retrieval_exclude`, …).

## Corpus tiers (for scaling experiments)

`manifest.jsonl` lists every file with its tier and word count.

| Tier | Contents | Files (retrievable) | Words |
| --- | --- | --- | --- |
| S | Manual v3.0 only | 46 | ~40k |
| M | S + v1.0, v2.0, circulars, FAQs, handbooks, benefits | 245 | ~223k |
| L | Everything | 495 | ~1.51M |

**Shortcut control:** five files have `retrieval_exclude: true` — Chapter 37 (country comparison) in v2.0 and v3.0, the change log and both annual reports. They pre-aggregate answers; use them only to check gold answers.

## Ground truth

- `ledger/` — the facts the text was generated from: `policy_values.json` (every entitlement by country and version), `circulars.json`, `key_events.json`, `conflicts.json`, and full record ledgers (`tickets.json`, `grievances.json`, `exit_notes.json`, `survey_comments.json`) with category, date, sentiment label, resolution time, etc.
- `gold/questions.jsonl` — 89 questions with answers **computed in code from the ledger**, evidence doc IDs, answer format (value, set, tuple, ranked_list, ratio, text) and the minimum tier needed. Types: local, count, filter, extremum, rank, version_diff, temporal, conflict, theme, sentiment_shift, aggregate, comparison.

Sentiment labels for exits, tickets and survey comments exist only in the ledger; the text conveys tone through wording, quotes, CSAT and recommend scores.

## Planted signals

- **Events:** hybrid office days 2 → 3 from 1 Apr 2026 (HR-CIR-2026-04) raises hybrid tickets, hybrid grievances and "office attendance" exit reasons, and makes exit sentiment more negative (negative share ~35% before vs ~56% after); expense-module migration (May 2026) raises reimbursement ticket volume and resolution time; India night shift allowance change (Jan 2026) raises shift tickets; Bengaluru transport vendor change raises transport grievances.
- **Conflicts** (`ledger/conflicts.json`, 12 items): India sick days 8 in Ch 15.1 vs 10-day global minimum (corrected by HR-CIR-2026-12); future circulars (UK 27 days, NL 26 days, India ₹700 night allowance, Singapore CPF 18%); stale FAQs (hybrid 2 days, India paternity 7 days), stale handbooks (London 23 days, Pune ₹500) and stale Singapore benefits summary (16 days); plus legitimate version updates that are *not* conflicts.

## Regenerating

Scripts are in `generator/` (Python 3, standard library only, fixed seed). Run in order: `policy_versions.py` (needs the exported v3.0 manual at `/home/claude/src/manual_v3.md`), `events.py`, `records.py`, `docs.py`, `gold.py`, `validate.py`. The validator runs ~2,700 checks (ledger vs text, planted conflicts, record counts, evidence IDs, no placeholders).

## Limitations

- Records, circulars, FAQs and handbooks are template-generated from the ledger, so phrasing repeats more than real enterprise text.
- Versions 1.0 and 2.0 are derived from v3.0 by changing values and removing later material; they are plausible but not historical.
- Legal references reflect the authors' understanding as of late 2026 and are illustrative only.
