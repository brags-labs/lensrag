from __future__ import annotations
import json, re, zipfile, shutil
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Iterable

TIERS = {"S": 1, "M": 2, "L": 3}
COUNTRIES = {
    "AE":"United Arab Emirates","AU":"Australia","CA":"Canada","DE":"Germany",
    "IE":"Ireland","IN":"India","NL":"Netherlands","SG":"Singapore","UK":"United Kingdom","US":"United States"
}
COUNTRY_NAMES = list(COUNTRIES.values())

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

def load_documents(corpus_dir: Path, tier: str) -> list[Document]:
    max_tier=TIERS[tier]
    docs=[]
    for item in read_manifest(corpus_dir):
        if item.get("retrieval_exclude", False): continue
        if TIERS[item["tier"]] > max_tier: continue
        path=corpus_dir/"corpus"/item["path"]
        if not path.exists(): continue
        raw=path.read_text(encoding="utf-8", errors="replace")
        meta, body=parse_frontmatter(raw)
        docs.append(Document(
            doc_id=meta.get("doc_id",item.get("doc_id",path.stem)),
            path=item["path"], doc_type=meta.get("doc_type",item.get("doc_type","unknown")),
            country=meta.get("country",item.get("country","ALL")),
            version=meta.get("version",""), effective_date=meta.get("effective_date",""),
            period=meta.get("period",""), status=meta.get("status",""),
            tier=item["tier"], text=body,
            title=meta.get("title", "") or next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("# ")), path.stem),
            employee_category=meta.get("employee_category",meta.get("employee_group",meta.get("employee_type","")))
        ))
    return docs

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

def chunk_document(doc: Document, max_words=260, overlap_words=40):
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
        for n,piece in enumerate(pieces):
            mentioned=tuple(name for name in COUNTRY_NAMES if name.lower() in piece.lower())
            entity_name=COUNTRIES.get(doc.country)
            entities=tuple(dict.fromkeys(((entity_name,) if entity_name else ()) + mentioned))
            header=(f"Document: {doc.title or doc.doc_id} [{doc.doc_id}] | Type: {doc.doc_type} | "
                    f"Section: {section or 'document'} | Scope: {doc.country} | Employee category: {doc.employee_category or 'unspecified'} | "
                    f"Version: {doc.version or 'unspecified'} | "
                    f"Effective date: {doc.effective_date or 'unspecified'} | "
                    f"Status: {doc.status or 'unspecified'} | "
                    f"Entities: {', '.join(entities) or 'unspecified'} | "
                    f"Period: {doc.period or 'unspecified'}")
            chunks.append(Chunk(
                chunk_id=f"{doc.doc_id}::C{n:04d}", doc_id=doc.doc_id, path=doc.path,
                doc_type=doc.doc_type, country=doc.country, version=doc.version,
                effective_date=doc.effective_date, status=doc.status,
                period=doc.period, entities=entities, section_path=section,
                text=piece, enriched_text=header+"\n"+piece, title=doc.title, employee_category=doc.employee_category
            ))
    return chunks

def load_gold(corpus_dir: Path):
    path=corpus_dir/"gold"/"questions.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
