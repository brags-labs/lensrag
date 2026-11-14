"""Query understanding and entity decomposition for LensRAG (steps 3 and 4).

`plan_query` turns a question into a `QueryPlan`: the query type, which entities it
names or excludes, which entity type it should be decomposed over, which policy versions
and time periods it covers, which document types and statuses are in scope, and the
parameters the deterministic aggregation needs (K, direction, threshold, aggregate).

`build_scopes` expands the plan into bounded per-entity subqueries. Each scope carries
a metadata filter, so retrieval can be checked for coverage entity by entity.

What counts as an entity (countries and offices for HR, jurisdictions and parties for
legal, ...) comes from the domain config (`lensrag/domain.py`, `lensrag/domains/*.yaml`).
The rule-based planner needs no LLM, so the benchmark can use it; the full runtime asks
an LLM for the same fields and falls back to these rules for anything missing.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from itertools import product
from .domain import Domain, load_domain, split_values

QUERY_TYPES = ("local", "count", "extremum", "rank", "filter", "aggregate", "comparison",
               "temporal", "version_diff", "theme", "sentiment_shift", "conflict")
GLOBAL_TYPES = set(QUERY_TYPES) - {"local"}
# Types whose answer depends on how a value changed, so superseded/announced documents matter.
HISTORY_TYPES = {"version_diff", "temporal", "conflict"}

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                       "august", "september", "october", "november", "december"], 1)}
_MONTH_RE = "|".join(MONTHS)
_NUM = r"(\d+(?:\.\d+)?)"


@dataclass
class QueryPlan:
    question: str
    qtype: str
    named: dict = field(default_factory=dict)      # entity type -> values the question names
    excluded: dict = field(default_factory=dict)   # entity type -> values it excludes ('excluding X')
    topics: list = field(default_factory=list)     # entity types the question is about ('which offices')
    fanout: str | None = None                      # entity type to decompose over; None = one scope
    versions: list[str] = field(default_factory=list)       # e.g. ["2.0", "3.0"]
    periods: list[tuple[int, int]] = field(default_factory=list)  # month-index ranges, inclusive
    doc_types: list[str] = field(default_factory=list)      # record types the question asks about
    include_superseded: bool = False
    operation: str | None = None   # count|max|min|rank|filter|mean|share|group|map_reduce|conflict|None
    direction: str = "desc"        # desc = highest first
    k: int | None = None
    threshold: float | None = None
    comparator: str | None = None  # gte|gt|lte|lt|eq
    mode: str = "exact"            # Step 7 computation mode: exact | estimated | generated
    domain: str = "hr"   # domain config name or path, for scope filters

    def to_dict(self):
        return asdict(self)


@dataclass
class Scope:
    """One bounded subquery: a label, the query text and the metadata it is restricted to."""
    label: str
    query: str
    entity_type: str | None = None
    entity_value: str | None = None
    filters: dict = field(default_factory=dict)   # metadata field -> required value
    version: str | None = None
    period: tuple[int, int] | None = None

    def key(self):
        return (self.entity_type, self.entity_value, tuple(sorted(self.filters.items())),
                self.version, self.period, self.label)

    @property
    def country(self):
        return self.filters.get("country")


# --- entity inventory -------------------------------------------------------------
def _value(obj, name):
    """A metadata value from a Document/Chunk: its meta dict first, then its attribute."""
    meta = getattr(obj, "meta", None) or {}
    v = meta.get(name)
    return v if v not in (None, "") else getattr(obj, name, "")


def build_inventory(docs, domain: Domain | None = None):
    """Entities present in the corpus, per entity type declared by the domain.

    Field-based types collect every distinct non-global value of their field; title-based
    types (e.g. offices) take a name from matching document titles and link it to the
    parent entity of that document. Versions and periods present are listed too.
    """
    domain = domain or load_domain()
    found = {t.name: {} for t in domain.entity_types}
    versions, periods = set(), set()
    for d in docs:
        for t in domain.entity_types:
            if t.field:
                for v in split_values(_value(d, t.field), t.multi):
                    if v in domain.global_values or v in t.ignore:
                        continue
                    e = found[t.name].setdefault(v, {"type": t.name, "value": v, "name": t.display(v),
                                                     "document_count": 0, "doc_types": set()})
                    e["document_count"] += 1; e["doc_types"].add(d.doc_type)
            elif t.from_title and d.doc_type in t.from_title.get("doc_types", [d.doc_type]):
                m = re.search(t.from_title["pattern"], d.title or "", re.I)
                if m and m.group(1).strip():
                    name = m.group(1).strip()
                    parent_t = domain.entity(t.parent) if t.parent else None
                    parents = split_values(_value(d, parent_t.field), parent_t.multi) if parent_t and parent_t.field else []
                    found[t.name][name] = {"type": t.name, "value": name, "name": name,
                                           "parent": parents[0] if parents else None, "doc_id": d.doc_id}
        if d.version: versions.add(d.version)
        if d.period: periods.add(d.period)
    entities = {name: [dict(e, doc_types=sorted(e["doc_types"])) if "doc_types" in e else e
                       for e in sorted(items.values(), key=lambda x: x["name"])]
                for name, items in found.items()}
    return {"domain": domain.name, "domain_source": domain.source, "entities": entities,
            "versions": sorted(versions), "periods": sorted(periods)}


def _domain_of(inventory, domain=None):
    inv = inventory or {}
    return domain or load_domain(inv.get("domain_source") or inv.get("domain"))


# --- parsing helpers ----------------------------------------------------------------
def _month_index(year, month):
    return int(year) * 12 + (int(month) - 1)


def period_range(label: str):
    """Month-index range for corpus period labels: '2026-05', '2026-Q2', '2026'."""
    if not label:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})", label)
    if m:
        i = _month_index(m[1], m[2]); return (i, i)
    m = re.fullmatch(r"(\d{4})-Q([1-4])", label)
    if m:
        s = _month_index(m[1], (int(m[2]) - 1) * 3 + 1); return (s, s + 2)
    m = re.fullmatch(r"(\d{4})", label)
    if m:
        return (_month_index(m[1], 1), _month_index(m[1], 12))
    return None


def overlaps(a, b):
    return a is not None and b is not None and a[0] <= b[1] and b[0] <= a[1]


def parse_periods(q: str):
    """Time ranges named in the question, as a list of month-index ranges.

    Two ranges mean the question compares them (e.g. 'Q1 2026 to Q2 2026'); a single
    'after/since <date>' produces a before/after pair.
    """
    ql = q.lower().replace("–", "-").replace("—", "-")
    ranges = []
    taken = []

    def add(rng, span):
        if any(s < span[1] and span[0] < e for s, e in taken):
            return
        taken.append(span); ranges.append((span[0], rng))

    # Month YYYY - Month YYYY / between Month YYYY and Month YYYY
    for m in re.finditer(rf"(?:between\s+)?({_MONTH_RE})\s+(\d{{4}})\s*(?:-|to|and|until)\s*({_MONTH_RE})\s+(\d{{4}})", ql):
        add((_month_index(m[2], MONTHS[m[1]]), _month_index(m[4], MONTHS[m[3]])), m.span())
    # Month - Month YYYY (same year) / Month and Month YYYY
    for m in re.finditer(rf"({_MONTH_RE})\s*(?:-|to|and)\s*({_MONTH_RE})\s+(\d{{4}})", ql):
        add((_month_index(m[3], MONTHS[m[1]]), _month_index(m[3], MONTHS[m[2]])), m.span())
    # Qn YYYY - Qn YYYY as one range when joined by 'between ... and' or '-'; 'from A to B' = two ranges
    for m in re.finditer(r"(between\s+)?q([1-4])\s+(\d{4})\s*(-|to|and)\s*q([1-4])\s+(\d{4})(\s+combined)?", ql):
        a = period_range(f"{m[3]}-Q{m[2]}"); b = period_range(f"{m[6]}-Q{m[5]}")
        if m[1] or m[4] == "-" or m[7] or "combined" in ql:
            add((a[0], b[1]), m.span())
        else:
            add(a, (m.start(), m.start(2) + 6)); add(b, (m.start(5), m.end()))
    for m in re.finditer(r"\bq([1-4])\s+(\d{4})", ql):
        add(period_range(f"{m[2]}-Q{m[1]}"), m.span())
    # after/since/before a date: produce before + after windows (bounded to the corpus era)
    m = re.search(rf"\b(after|since|before)\b[^.?]*?\b(\d{{1,2}})\s+({_MONTH_RE})\s+(\d{{4}})", ql)
    if m and not ranges:
        pivot = _month_index(m[4], MONTHS[m[3]])
        add((pivot - 120, pivot - 1), (m.start(), m.start() + 1))
        add((pivot, pivot + 120), (m.start() + 1, m.end()))
    # single Month YYYY (a day before it, e.g. '15 December 2026', is fine)
    for m in re.finditer(rf"\b({_MONTH_RE})\s+(\d{{4}})", ql):
        i = _month_index(m[2], MONTHS[m[1]]); add((i, i), m.span())
    # bare year 'in 2025' / '2026 Pulse survey' (not part of a version or doc id)
    for m in re.finditer(r"(?<![\w.-])(20\d{2})(?![\w.-])", ql):
        add(period_range(m[1]), m.span())
    return [r for _, r in sorted(ranges)]


def parse_versions(q: str, terms: str = r"\bversions?\b|\bv\d"):
    if not re.search(terms, q, re.I):
        return []
    return list(dict.fromkeys(re.findall(r"(?<![\d.])v?([1-9]\.\d)(?!\.?\d)", q)))


EXCLUSION = r"\b(excluding|except|other than|apart from|besides)\s+(the\s+)?"


def parse_entities(q: str, inventory, domain: Domain):
    """Entity values the question names and excludes, per entity type.

    A name shared by two types (Singapore is a country and an office) stays only with
    the type the question is about, or with the default fan-out type if it is about neither.
    """
    entities = (inventory or {}).get("entities", {})
    topics = [t.name for t in domain.entity_types if t.topic and re.search(t.topic, q, re.I)]
    all_names = {}
    for t in domain.entity_types:
        for e in entities.get(t.name, []):
            all_names.setdefault(e["name"].lower(), set()).add(t.name)
    named, excluded = {}, {}
    for t in domain.entity_types:
        items = entities.get(t.name, [])
        by_name = {e["name"]: e["value"] for e in items}
        found = [e["value"] for e in items if re.search(rf"\b{re.escape(e['name'])}\b", q, re.I)]
        if t.match_partial:
            # A distinctive first word ("Acme" for "Acme Corp") counts when no other entity shares it.
            firsts = {}
            for e in items:
                firsts.setdefault(e["name"].split()[0].lower(), []).append(e["value"])
            for e in items:
                w = e["name"].split()[0]
                if e["value"] not in found and len(w) >= 4 and len(firsts[w.lower()]) == 1 \
                        and re.search(rf"\b{re.escape(w)}\b", q, re.I):
                    found.append(e["value"])
        for alias, name in t.aliases.items():
            v = by_name.get(name)
            if v and v not in found and re.search(rf"(?<![\w.]){re.escape(alias)}(?![\w])", q):
                found.append(v)
        shared = lambda v: len(all_names.get(t.display(v).lower(), ())) > 1
        if t.name not in topics and not t.default_fanout:
            found = [v for v in found if not shared(v)]
        ex = [v for v in found if re.search(EXCLUSION + re.escape(t.display(v)), q, re.I)]
        if found and [v for v in found if v not in ex]: named[t.name] = [v for v in found if v not in ex]
        if ex: excluded[t.name] = ex
    return named, excluded, topics


def parse_k(q: str):
    ql = q.lower()
    m = re.search(r"\btop\s+(\d+|" + "|".join(WORD_NUMBERS) + r")\b", ql) or \
        re.search(r"\b(\d+|" + "|".join(WORD_NUMBERS) + r")\s+(?:most|least|highest|lowest|largest|smallest|longest|shortest|oldest|newest|biggest)\b", ql) or \
        re.search(r"\b(?:the|which)\s+(" + "|".join(WORD_NUMBERS) + r")\s+\w+", ql)
    if not m:
        return None
    v = m.group(1)
    return int(v) if v.isdigit() else WORD_NUMBERS[v]


def parse_direction(q: str):
    ql = q.lower()
    asc = re.search(r"\b(lowest|least|shortest|fewest|smallest|oldest|earliest|minimum)\b|from\s+\w+est\s+to", ql)
    if re.search(r"from\s+(shortest|lowest|smallest|least|fewest|oldest)\s+to", ql):
        return "asc"
    if re.search(r"from\s+(longest|highest|largest|most)\s+to", ql):
        return "desc"
    return "asc" if asc and not re.search(r"\b(highest|most|longest|largest|greatest|maximum)\b", ql) else "desc"


def parse_threshold(q: str):
    ql = q.lower()
    pats = [("gte", r"at least|no fewer than|no less than|or more"), ("lte", r"at most|no more than"),
            ("gt", r"more than|over|above|greater than|longer than|exceed(?:s|ing)?"),
            ("lt", r"less than|fewer than|below|under|shorter than"), ("eq", r"exactly")]
    for comp, words in pats:
        m = re.search(rf"\b(?:{words})\s+(?:the\s+)?(?:a\s+)?{_NUM}", ql)
        if m:
            return float(m.group(1)), comp
    return None, None


UNITS = r"(?:working |calendar |office |paid )*(?:days?|weeks?|hours?|months?|years?|%|percent)"


def detect_type(q: str, latest_version: str | None = None, domain: Domain | None = None):
    """Keyword classifier over the gold taxonomy; the full runtime asks an LLM first.

    Entity nouns ('countries', 'offices', 'contracts'), record-type words and extra
    phrasings per type come from the domain config.
    """
    domain = domain or load_domain()
    ql = q.lower()
    nouns = "|".join(re.escape(n.lower()) for n in domain.entity_nouns) or "items"
    hint = lambda t: "|".join(domain.type_hints.get(t, []))
    def matches(t, base):
        return re.search(base, ql) or (hint(t) and re.search(hint(t), ql))
    versions = parse_versions(q, domain.version_terms)
    plural_entities = re.search(rf"\b(which|in which|what) (\w+ )?({nouns})\b", ql)
    has_threshold = parse_threshold(q)[0] is not None
    superlative = re.search(r"(?<!at )\b(highest|lowest|most|least|largest|smallest|longest|shortest|maximum|minimum|biggest|oldest)\b", ql)
    asks_quantity = re.search(rf"\bhow many {UNITS}\b|\bhow much\b", ql)
    if matches("conflict", r"\bconflict|contradict|inconsisten|outdated|\bagree\b"):
        return "conflict"
    if hint("temporal") and re.search(hint("temporal"), ql):
        return "temporal"
    if versions and (len(versions) > 1 or re.search(r"\b(added|removed|covered|introduced|dropped)\b", ql)
                     or (latest_version and any(v != latest_version for v in versions))) or \
            (hint("version_diff") and re.search(hint("version_diff"), ql)):
        return "version_diff"
    if matches("sentiment_shift", r"\bsentiment\b|more negative|more positive"):
        return "sentiment_shift"
    if matches("comparison", r"compared with|\bcompare|change from|how did .* change|\bvs\.?\b|versus"):
        return "comparison"
    if matches("theme", r"\bthemes?\b|most common \w+ categor|primary \w+ reasons|topics? attracted|top \w+ (?:primary )?(?:reasons|topics|categories)"
               r"|^\s*(why|what explains|what insights?|what recommendations?|what can we learn)\b"):
        return "theme"
    if matches("aggregate", r"\baverage\b|\bmean\b|what share|what proportion|what percentage|\bratio\b"):
        return "aggregate"
    if re.search(rf"^\s*(how many|in how many)\b|\bnumber of\b.*\b({nouns})\b", ql) and not asks_quantity \
            or (hint("count") and re.search(hint("count"), ql)):
        return "count"
    if plural_entities and has_threshold:
        return "filter"
    if re.search(r"\brank\b|\btop\s+(\d+|" + "|".join(WORD_NUMBERS) + r")\b|which (\w+ )?(\d+|"
                 + "|".join(WORD_NUMBERS) + rf") ({nouns})", ql) or (plural_entities and superlative) \
            or (hint("rank") and re.search(hint("rank"), ql)):
        return "rank"
    if plural_entities or (hint("filter") and re.search(hint("filter"), ql)):
        return "filter"
    if superlative and re.search(r"\bwhich\b|\bwhat (was|is) the most\b|\bin which\b", ql) \
            or (hint("extremum") and re.search(hint("extremum"), ql)):
        return "extremum"
    if parse_periods(q) and not any(re.search(p, ql) for p in domain.record_types.values()):
        return "temporal"  # a value at a point in time
    if re.search(r"\b(will|would|applies|apply|came into force|taking effect)\b", ql):
        return "temporal"
    return "local"


OPERATIONS = {"count": "count", "extremum": None, "rank": "rank", "filter": "filter", "aggregate": None,
              "comparison": "group", "temporal": "group", "version_diff": "group", "theme": "map_reduce",
              "sentiment_shift": "map_reduce", "conflict": "conflict", "local": None}


def plan_query(question: str, inventory=None, overrides: dict | None = None,
               domain: Domain | None = None) -> QueryPlan:
    """Rule-based plan; `overrides` (e.g. from an LLM) win for any field they set validly."""
    domain = _domain_of(inventory, domain)
    inventory = inventory or {"entities": {}, "versions": [], "periods": []}
    q = question
    ql = q.lower()
    qtype = detect_type(q, max(inventory.get("versions") or [None], key=lambda v: v or ""), domain)
    named, excluded, topics = parse_entities(q, inventory, domain)
    versions = parse_versions(q, domain.version_terms)
    doc_types = [t for t, p in domain.record_types.items() if re.search(p, ql)]
    plan = QueryPlan(question=q, qtype=qtype, named=named, excluded=excluded, topics=topics,
                     versions=versions, periods=parse_periods(q), doc_types=doc_types,
                     include_superseded=bool(versions), direction=parse_direction(q), k=parse_k(q),
                     domain=domain.source)
    plan.threshold, plan.comparator = parse_threshold(q)
    for key, value in (overrides or {}).items():
        if value in (None, "", [], {}) or not hasattr(plan, key):
            continue
        if key == "qtype" and value not in QUERY_TYPES:
            continue
        setattr(plan, key, value)
    plan.operation = OPERATIONS[plan.qtype]
    if plan.qtype == "extremum":
        plan.operation = "min" if plan.direction == "asc" else "max"
        if re.search(r"\bmost (common|frequent|popular)\b|\bmost often\b", ql):
            plan.operation = "mode"  # a categorical extremum: the most common category
    if plan.qtype == "filter" and plan.threshold is None and re.search(r"\bboth\b|\ball of\b", ql):
        plan.operation = "all_of"  # entities meeting every listed yes/no criterion
    if plan.qtype == "aggregate":
        plan.operation = "share" if re.search(r"\bshare\b|proportion|percentage|ratio", ql) else "mean"
    if plan.qtype == "rank" and plan.k is None and not re.search(r"\brank\b", ql) \
            and re.search(r"\b(longest|highest|most|largest)\b", ql):
        plan.k = 1  # 'which countries have the longest ...' = every entity tied for first
    plan.include_superseded = plan.include_superseded or plan.qtype in HISTORY_TYPES
    plan.fanout = choose_fanout(plan, domain)
    plan.mode = computation_mode(plan)
    return plan


def computation_mode(plan: QueryPlan) -> str:
    """Step 7 mode. `estimated` may still run exactly when the records in scope are few enough
    to read in full; the pipeline decides that once it knows the population size.

    exact      numbers, rankings, filters, categories over records that can be read in full
    estimated  shares, means, counts or category frequencies over record logs (tickets, surveys...)
    generated  themes, insights, explanations and sentiment change (with exact/estimated numbers inside)
    """
    if plan.qtype in ("theme", "sentiment_shift"):
        return "generated"
    over_records = bool(plan.doc_types)
    if over_records and (plan.qtype in ("aggregate", "comparison")
                         or plan.operation in ("mode", "count", "frequency")):
        return "estimated"
    return "exact"


def choose_fanout(plan: QueryPlan, domain: Domain):
    """The entity type to decompose over: the first type (in config priority order) the
    question is about or names; else the default type for corpus-wide questions; else none."""
    for t in domain.entity_types:
        if t.name in plan.topics or plan.named.get(t.name):
            return t.name
    if plan.qtype in ("local", "temporal"):
        return None  # point lookups: one search, no fan-out
    return next((t.name for t in domain.entity_types if t.default_fanout), None)


# --- decomposition ------------------------------------------------------------------
def build_scopes(plan: QueryPlan, inventory, domain: Domain | None = None) -> list[Scope]:
    """Expand a plan into bounded subqueries across every entity dimension it names.

    The fan-out type contributes one scope per entity: those the question names, else
    those under a named parent (offices in India), else all of them minus exclusions.
    Versions and periods split scopes further when the question contrasts several.
    """
    domain = _domain_of(inventory, domain)
    q = plan.question
    t = domain.entity(plan.fanout) if plan.fanout else None
    entities = [(None, None, None, {})]
    if t is not None:
        items = inventory.get("entities", {}).get(t.name, [])
        if plan.named.get(t.name):
            chosen = [e for e in items if e["value"] in plan.named[t.name]]
        elif t.parent and plan.named.get(t.parent):
            chosen = [e for e in items if e.get("parent") in plan.named[t.parent]]
        else:
            chosen = [e for e in items if e["value"] not in plan.excluded.get(t.name, [])]
        parent_t = domain.entity(t.parent) if t.parent else None
        entities = []
        for e in chosen:
            if t.field:
                filters = {t.field: e["value"]}
            elif parent_t and parent_t.field and e.get("parent"):
                filters = {parent_t.field: e["parent"]}
            else:
                filters = {}
            entities.append((e["name"], t.name, e["value"], filters))
    versions = plan.versions if len(plan.versions) > 1 else [plan.versions[0] if plan.versions else None]
    periods = plan.periods if len(plan.periods) > 1 else [plan.periods[0] if plan.periods else None]
    scopes = []
    for (name, etype, value, filters), version, period in product(entities, versions, periods):
        parts = [p for p in (name, f"version {version}" if version and len(plan.versions) > 1 else None) if p]
        label = " / ".join(parts + ([_period_label(period)] if period and len(plan.periods) > 1 else [])) or "all"
        scopes.append(Scope(label=label, query=" ".join([q] + parts), entity_type=etype, entity_value=value,
                            filters=filters, version=version, period=period))
    return scopes


def _period_label(rng):
    def fmt(i): return f"{i // 12}-{i % 12 + 1:02d}"
    return fmt(rng[0]) if rng[0] == rng[1] else f"{fmt(rng[0])}..{fmt(rng[1])}"


def scope_filter(plan: QueryPlan, scope: Scope, domain: Domain | None = None):
    """Chunk predicate for one scope: entity fields, version, period, document type and status."""
    domain = domain or load_domain(plan.domain)
    want_types = set(plan.doc_types)
    record_types = set(domain.record_types)
    active = domain.active_statuses
    multi = {t.field: t.multi for t in domain.entity_types if t.field}
    globals_ = set(domain.global_values)

    def ok(c):
        for fld, want in scope.filters.items():
            have = split_values(_value(c, fld), multi.get(fld, False))
            if have and want not in have and not globals_.intersection(have):
                return False
        if want_types:
            if c.doc_type not in want_types:
                return False
        elif c.doc_type in record_types:
            return False
        if scope.version and c.version and c.version != scope.version:
            return False
        if scope.period and c.period and not overlaps(period_range(c.period), scope.period):
            return False
        if not plan.include_superseded and str(c.status).lower() not in active:
            return False
        return True
    return ok
