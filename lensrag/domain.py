"""Domain configuration: what the entities, metadata fields and status words of a corpus are.

LensRAG's method is domain-neutral, but every corpus names things differently: an HR
corpus has countries and offices, a legal one jurisdictions and parties. A domain file
(YAML or JSON) declares those so ingestion, the entity inventory, query planning and
version handling need no code changes. `domains/hr.yaml` reproduces the BragsLabs
behaviour; `domains/legal.yaml` is an example for contracts and case law.

Load one with `load_domain("hr")`, `load_domain("legal")` or `load_domain("path/to/x.yaml")`.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field as dc_field
from functools import lru_cache
from pathlib import Path

DOMAINS_DIR = Path(__file__).resolve().parent / "domains"
DEFAULT_DOMAIN = "hr"


@dataclass
class EntityType:
    """One kind of entity questions can be decomposed over.

    Values come either from a metadata `field` (e.g. country: IN) or, with `from_title`,
    from the titles of documents of given types (e.g. office handbooks). A derived type
    names a `parent` type; its scopes filter on the parent's field.
    """
    name: str
    plural: str
    field: str | None = None              # metadata field holding the value
    multi: bool = False                   # field may hold several values ("A; B" or "[A, B]")
    names: dict = dc_field(default_factory=dict)    # value -> display name (e.g. IN -> India)
    aliases: dict = dc_field(default_factory=dict)  # alias -> display name (case-sensitive)
    topic: str | None = None              # regex: question is about this entity type
    from_title: dict | None = None        # {doc_types: [...], pattern: regex with one group}
    parent: str | None = None             # derived types: the type whose field scopes them
    default_fanout: bool = False          # fan out over this type for corpus-wide questions
    in_header: bool = False               # list mentioned names in each chunk's Entities: header
    match_partial: bool = False           # also match a name's distinctive first word ("Acme" -> "Acme Corp")
    ignore: list = dc_field(default_factory=list)  # values never treated as entities (e.g. one's own company)

    def display(self, value):
        return self.names.get(value, value)


@dataclass
class Domain:
    name: str
    description: str = ""
    fields: dict = dc_field(default_factory=dict)        # role -> front-matter field name
    field_aliases: dict = dc_field(default_factory=dict) # field -> alternative front-matter names
    defaults: dict = dc_field(default_factory=dict)      # field -> value when missing
    global_values: list = dc_field(default_factory=lambda: ["ALL", "GLOBAL", ""])
    status: dict = dc_field(default_factory=dict)        # active / pending / superseded word lists
    version_terms: str = r"\bversions?\b|\bv\d"
    entity_types: list = dc_field(default_factory=list)  # in priority order
    item_nouns: list = dc_field(default_factory=list)    # other plurals questions select ("contracts")
    record_types: dict = dc_field(default_factory=dict)  # doc_type -> regex of words that ask for it
    type_hints: dict = dc_field(default_factory=dict)    # query type -> extra regexes
    header: str = ""                                  # chunk header template
    source: str = ""

    # --- accessors ------------------------------------------------------------------
    def f(self, role):
        """Front-matter field name for a generic role (doc_id, version, status, ...)."""
        return self.fields.get(role, role)

    def entity(self, name):
        return next((t for t in self.entity_types if t.name == name), None)

    @property
    def active_statuses(self):
        return {s.lower() for s in self.status.get("active", ["current", "in force", ""])}

    @property
    def pending_statuses(self):
        return {s.lower() for s in self.status.get("pending", ["announced"])}

    @property
    def entity_nouns(self):
        return [t.plural for t in self.entity_types] + list(self.item_nouns)

    def fingerprint(self):
        """Stable hash of the settings that change chunk text or metadata."""
        relevant = {"fields": self.fields, "field_aliases": self.field_aliases, "defaults": self.defaults,
                    "header": self.header, "in_header": [(t.name, t.field, t.names) for t in self.entity_types if t.in_header]}
        return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


def _build(data: dict, source: str) -> Domain:
    types = [EntityType(**t) for t in data.pop("entity_types", [])]
    return Domain(entity_types=types, source=source, **data)


@lru_cache(maxsize=None)
def load_domain(spec: str | None = None) -> Domain:
    """Load a domain by built-in name ('hr', 'legal') or by path to a .yaml/.json file."""
    spec = spec or DEFAULT_DOMAIN
    path = Path(spec)
    if not path.suffix:
        path = DOMAINS_DIR / f"{spec}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Domain config not found: {spec}")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        import yaml
        data = yaml.safe_load(text)
    return _build(data, str(path))


def split_values(raw, multi: bool):
    """Values of a metadata field; multi-valued fields accept 'A; B', 'A, B' or '[A, B]'."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    raw = str(raw).strip()
    if not multi:
        return [raw] if raw else []
    raw = raw.strip("[]")
    return [x.strip().strip("'\"") for x in re.split(r"[;,]", raw) if x.strip().strip("'\"")]
