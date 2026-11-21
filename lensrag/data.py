from __future__ import annotations
import json, re, zipfile, string
from pathlib import Path
from dataclasses import dataclass, field
from .domain import Domain, load_domain, split_values

TIERS = {"S": 1, "M": 2, "L": 3}
# Country code -> name for the HR domain (kept for callers of the earlier API; the
# source of truth is lensrag/domains/hr.yaml).
COUNTRIES = dict(load_domain("hr").entity("country").names)
COUNTRY_NAMES = list(COUNTRIES.values())
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}

@dataclass
class Document:
    doc_id: str
    path: str
    doc_type: str
    country: str
    version: str
    effective_date: str
    period: str
    status: str
    tier: str
    text: str
    title: str = ""
    employee_category: str = ""
    meta: dict = field(default_factory=dict)   # every front-matter field, after aliases/defaults

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    path: str
    doc_type: str
    country: str
    version: str
    effective_date: str
    status: str
    period: str
    entities: tuple[str, ...]
    section_path: str
    text: str
    enriched_text: str
    title: str = ""
    employee_category: str = ""
    meta: dict = field(default_factory=dict)

def ensure_extracted(zip_path: Path, extract_dir: Path) -> Path:
    marker = extract_dir / "bragslabs_corpus" / "manifest.jsonl"
    if marker.exists():
        return extract_dir / "bragslabs_corpus"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        # Reject path traversal in archive members.
        for name in zf.namelist():
            target = (extract_dir / name).resolve()
            if not str(target).startswith(str(extract_dir.resolve())):
                raise ValueError(f"Unsafe archive path: {name}")
        zf.extractall(extract_dir)
    if not marker.exists():
        raise FileNotFoundError("Expected bragslabs_corpus/manifest.jsonl in ZIP")
    return marker.parent

def read_manifest(corpus_dir: Path):
    return [json.loads(x) for x in (corpus_dir/"manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

def parse_frontmatter(raw: str):
    meta = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k,v=line.split(":",1); meta[k.strip()] = v.strip().strip('"').strip("'")
            raw=parts[2].lstrip()
    return meta, raw

def _make_document(meta: dict, body: str, rel_path: str, tier: str, fallback: dict, domain: Domain) -> Document:
    """Build a Document from front matter, filling missing fields from aliases, the manifest and defaults."""
    meta = dict(meta)
    for name, alts in domain.field_aliases.items():
        if name not in meta:
            meta[name] = next((meta[a] for a in alts if a in meta), "")
    for name, default in domain.defaults.items():
        if name not in meta:
            meta[name] = fallback.get(name, default)
    f = domain.f
    stem = Path(rel_path).with_suffix("").as_posix()
    doc_id = meta.get(f("doc_id")) or fallback.get("doc_id") or stem
    meta.setdefault(f("doc_id"), doc_id)
    title = meta.get(f("title"), "") or next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("# ")), Path(rel_path).stem)
    return Document(doc_id=doc_id, path=rel_path, doc_type=meta.get(f("doc_type"), "unknown"),
                    country=meta.get("country", ""), version=meta.get(f("version"), ""),
                    effective_date=meta.get(f("effective_date"), ""), period=meta.get(f("period"), ""),
                    status=meta.get(f("status"), ""), tier=tier, text=body, title=title,
                    employee_category=meta.get("employee_category", ""), meta=meta)


def load_documents(corpus_dir: Path, tier: str, domain: Domain | None = None) -> list[Document]:
    """Load a manifest-based corpus (manifest.jsonl + corpus/) up to a size tier."""
    domain = domain or load_domain()
    max_tier=TIERS[tier]
    docs=[]
    for item in read_manifest(corpus_dir):
        if item.get("retrieval_exclude", False): continue
        if TIERS[item["tier"]] > max_tier: continue
        path=corpus_dir/"corpus"/item["path"]
        if not path.exists(): continue
        meta, body=parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        docs.append(_make_document(meta, body, item["path"], item["tier"], item, domain))
    return docs


def load_folder(folder: Path, domain: Domain | None = None) -> list[Document]:
    """Load every Markdown/text file under `folder`; front matter is optional.

    For corpora without a manifest. Documents without a doc_id use their relative path.
    """
    domain = domain or load_domain()
    folder = Path(folder)
    docs = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if str(meta.get("retrieval_exclude", "")).lower() == "true":
            continue
        docs.append(_make_document(meta, body, path.relative_to(folder).as_posix(), "L", {}, domain))
    return docs


class _HeaderValues(dict):
    def __missing__(self, key):
        return "unspecified"


def _header_entities(doc: Document, piece: str, domain: Domain):
    """Display names for the Entities: header field: the document's own, then any mentioned."""
    names = []
    for t in domain.entity_types:
        if not t.in_header or not t.field:
            continue
        names += [t.display(v) for v in split_values(doc.meta.get(t.field), t.multi) if v in t.names]
        names += [n for n in t.names.values() if n.lower() in piece.lower()]
    return tuple(dict.fromkeys(names))


def render_header(doc: Document, section: str, entities, domain: Domain) -> str:
    values = _HeaderValues({k: v for k, v in doc.meta.items() if v not in (None, "")})
    values.update(doc_id=doc.doc_id, title_or_id=doc.title or doc.doc_id, section=section or "document",
                  entities=", ".join(entities) or "unspecified")
    return string.Formatter().vformat(domain.header, (), values)


def _split_sections(text: str):
    """Split on Markdown headings; retain heading path to avoid losing section context."""
    lines=text.splitlines()
    stack=[]
    current=[]
    for line in lines:
        m=re.match(r'^(#{1,6})\s+(.+)',line.strip())
        if m:
            if current:
                yield " > ".join(stack), "\n".join(current).strip()
            level=len(m.group(1))
            stack=stack[:level-1]
            stack.append(m.group(2).strip())
            current=[line]
        else:
            current.append(line)
    if current:
        yield " > ".join(stack), "\n".join(current).strip()

def chunk_document(doc: Document, max_words=260, overlap_words=40, domain: Domain | None = None):
    domain=domain or load_domain()
    chunks=[]
    for section, text in _split_sections(doc.text):
        words=text.split()
        if not words: continue
        pieces=[]
        if len(words)<=max_words:
            pieces=[text]
        else:
            paras=[p.strip() for p in re.split(r'\n\s*\n',text) if p.strip()]
            buf=[]
            for para in paras:
                nonempty=[line.strip() for line in para.splitlines() if line.strip()]
                is_table=bool(nonempty) and all(line.startswith("|") for line in nonempty)
                if is_table:
                    if buf:
                        pieces.append("\n\n".join(buf)); buf=[]
                    pieces.append(para)
                elif len((" ".join(buf)+" "+para).split()) > max_words and buf:
                    pieces.append("\n\n".join(buf)); buf=[para]
                else:
                    buf.append(para)
            if buf: pieces.append("\n\n".join(buf))
            final=[]
            for piece in pieces:
                w=piece.split()
                nonempty=[line.strip() for line in piece.splitlines() if line.strip()]
                is_table=bool(nonempty) and all(line.startswith("|") for line in nonempty)
                if len(w)>max_words*1.5 and not is_table:
                    for i in range(0,len(w),max_words-overlap_words):
                        final.append(" ".join(w[i:i+max_words]))
                else:
                    final.append(piece)
            pieces=final
        for piece in pieces:
            n=len(chunks)  # numbered per document, so chunk ids are unique across sections
            entities=_header_entities(doc,piece,domain)
            header=render_header(doc,section,entities,domain)
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}::C{n:04d}", doc_id=doc.doc_id, path=doc.path,
                doc_type=doc.doc_type, country=doc.country, version=doc.version,
                effective_date=doc.effective_date, status=doc.status,
                period=doc.period, entities=entities, section_path=section,
                text=piece, enriched_text=header+"\n"+piece, title=doc.title, employee_category=doc.employee_category,
                meta=doc.meta
            ))
    return chunks

def load_gold(corpus_dir: Path):
    path=corpus_dir/"gold"/"questions.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
