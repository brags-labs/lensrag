"""Index-time fact table: the facts that reference documents state in Markdown tables.

Policy addenda, benefits summaries, handbooks and circulars state most of their numbers in
tables, for example

    | Employer retirement contribution (% of pay) | 12 |          (attribute | value)
    | India — Revised night shift allowance | ₹400 per night | ₹450 per night |   (item | before | after)
    | Floor | Teams | Desks |  ...                                (a matrix: attribute = row — column)

Reading them with an LLM at question time costs most of a question's latency (about 16 extraction
calls). Reading them once, when the index is loaded, is exact and takes well under a second. Each
fact keeps its chunk, so scope filters (entity, version, status) work on facts as on chunks, and
its row is its evidence span.

No field list is configured; the patterns are generic Markdown tables. Prose facts ("the office
opened in 2016") are not covered: those questions keep the retrieval path.
"""
from __future__ import annotations
import re

_ROW = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")
_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_NUM = re.compile(r"^[^\d\-]{0,3}?(-?\d[\d,]*(?:\.\d+)?)")
_CHANGE_HEAD = re.compile(r"^(before|old|previous|from\b.*|after|new|now|revised|current)$", re.I)
_GENERIC_HEAD = re.compile(r"^(item|field|term|detail|details|value|description|meaning|what you get|rule)$", re.I)


_DATE = re.compile(r"^\d{1,2}\s+[A-Za-z]+\s+\d{4}$|^\d{4}-\d{2}-\d{2}$")
_REF = re.compile(r"^(chapter|section|§)?\s*\d+(\.\d+)*$", re.I)


def number(value):
    """The leading number of a cell ('12', '₹450 per night', '5%', '2 days a week') or None.
    Dates are not numbers."""
    if _DATE.match(str(value).strip()):
        return None
    m = _NUM.match(str(value).strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


_UNIT = re.compile(r"\(([^()]*?(?:days?|weeks?|hours?|months?|years?|%))\)\s*$", re.I)


def unit_of(label):
    """The unit an attribute label names in parentheses: 'Paid annual leave (working days)' -> 'working days'."""
    m = _UNIT.search(str(label))
    return m.group(1).strip().lower() if m else None


def number_in_unit(value, label):
    """The number stated in the label's unit when the cell gives several
    ('30 calendar days (22 working days)' under '(working days)' -> 22), else the leading number."""
    unit = unit_of(label)
    if unit and "%" not in unit:
        stem = re.escape(unit.rstrip("s"))
        m = re.search(rf"(\d+(?:\.\d+)?)\s+{stem}s?\b", str(value), re.I)
        if m:
            return float(m.group(1))
    return number(value)


def tables(text):
    """[(header cells, [row cells])] for each Markdown table in text."""
    out, cur = [], None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _ROW.match(line)
        if not m:
            cur = None
            continue
        if _SEP.match(line):
            continue
        cells = [c.strip() for c in m.group("cells").split("|")]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if cur is None:
            if _SEP.match(nxt):          # a header row is followed by the separator row
                cur = (cells, [], [])
                out.append(cur)
            continue
        cur[1].append(cells)
        cur[2].append(line.strip())
    return [(h, rows, spans) for h, rows, spans in out]


def facts_of_chunk(chunk):
    """Facts in one chunk's tables, as evidence records (entity is filled in per scope)."""
    out = []
    for head, rows, spans in tables(str(chunk.text)):
        n = len(head)
        change = n == 3 and bool(_CHANGE_HEAD.match(head[1])) and bool(_CHANGE_HEAD.match(head[2]))
        for cells, span in zip(rows, spans):
            if len(cells) != n or not cells[0]:
                continue
            key = cells[0].strip("* ")
            subject = None
            if " — " in key:             # 'India — Revised night shift allowance'
                subject, key = [x.strip() for x in key.split(" — ", 1)]
            if n == 2:
                items = [(key, cells[1])]
            elif change:                 # before | after: the fact is the new value
                items = [(key, cells[2])]
            else:
                items = [(key if _GENERIC_HEAD.match(head[j]) else f"{key} — {head[j]}", cells[j])
                         for j in range(1, n) if cells[j]]
            for attr, val in items:
                val = val.strip("* ")
                rec = {"attribute": attr, "value": val, "number": number_in_unit(val, attr), "evidence_span": span,
                       "reference": bool(_REF.match(val)) and "chapter" in " ".join(head).lower(),
                       "doc_id": chunk.doc_id, "doc_type": chunk.doc_type, "version": chunk.version or "",
                       "status": chunk.status, "effective_date": chunk.effective_date or "", "period": chunk.period,
                       "chunk_id": chunk.chunk_id, "subject": subject}
                if change:
                    rec["previous_value"] = cells[1].strip("* ")
                out.append(rec)
    return out


def build_facts(chunks, skip_types=()):
    """{chunk_id: [fact]} for every chunk with a table, skipping record-log document types."""
    out = {}
    for c in chunks:
        if c.doc_type in skip_types:
            continue
        fs = facts_of_chunk(c)
        if fs:
            out[c.chunk_id] = fs
    return out


def norm_attr(a):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%()/ ]+", " ", str(a).lower())).strip()
