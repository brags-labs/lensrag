# Domain configuration: using LensRAG beyond HR

LensRAG's method doesn't depend on the subject matter. Two things do: what counts as an entity, and how documents describe themselves. Both are declared in a **domain config file**, so a new corpus (legal, research, finance…) needs a config, not code changes.

Built-in configs:

| Name | File | Entities |
|---|---|---|
| `hr` (default) | `lensrag/domains/hr.yaml` | office (from office handbook titles, scoped by its country), country (metadata field) |
| `legal` | `lensrag/domains/legal.yaml` | party (multi-valued `parties` field), jurisdiction (metadata field) |

Use one by name (`--domain legal`) or by path (`--domain path/to/mine.yaml`; JSON works too). The `hr` config reproduces the original behaviour exactly: on the BragsLabs benchmark, all 732 per-question results (3 tiers × 4 methods, TF-IDF and dense) retrieved the same documents before and after the change.

## How entities are determined

The inventory is built by `build_inventory(docs, domain)` in `lensrag/planning.py`:

- When: the benchmark builds it at the start of each tier's run; `build-index` builds it once and saves it to `<index-dir>/entities.json`.
- For each entity type in the config, in order:
  - **Field-based types** (`field: country`): every distinct value of that front-matter field becomes an entity. Values in `global_values` (`ALL`, `GLOBAL`…) and in `ignore` are skipped. Multi-valued fields (`multi: true`) accept `A; B`, `A, B` or `[A, B]`. The display name comes from `names` (`IN` → India), or else the value itself.
  - **Title-based types** (`from_title`): for documents of the listed `doc_types`, the regex's first group, taken from the title, is the entity name ("Bengaluru office handbook" → Bengaluru). With `parent: country`, the entity is linked to its document's country, and its scopes filter on that country.
- The policy versions and periods present are listed as well.

To list them:

```bash
python -m lensrag.cli entities
```

```bash
python -m lensrag.cli entities --domain legal --corpus tests/fixtures/legal_corpus
```

```bash
python -m lensrag.cli entities --index-dir artifacts/index_L --json
```

Without `--json`, `entities` shows each type, where its values come from, whether it's the default fan-out type or scoped by a parent, and each entity with its document count.

## How a question uses them

1. **Named entities.**
   - Display names match case-insensitively at word boundaries; `aliases` match case-sensitively ("UK", "USA").
   - With `match_partial: true`, a distinctive first word ("Acme" → "Acme Corp") also matches.
   - "Excluding X" / "other than X" moves X to the excluded list.
   - A name shared by two types (Singapore is a country and an office) stays with the type the question is about, or with the default fan-out type.
2. **Fan-out type.** This is the first type, in config order, whose `topic` regex matches the question ("which offices") or which the question names. Otherwise, corpus-wide questions use the `default_fanout` type, and point lookups (local, temporal) get a single scope.
3. **Scopes.** There is one scope per chosen entity:
   - the named ones; else those under a named parent ("offices in India"); else all, minus exclusions.
   - Each scope filters chunks to that entity's field value plus global documents.
   - Version and period splits are added when the question contrasts them.
4. **Document types and status.**
   - `record_types` lists record-style document types and the words that ask for them. Other questions exclude those types.
   - The `status` lists decide which documents count as active, pending or superseded. Superseded and pending documents are searched only for version, temporal or conflict questions, or when a version is named.

## Chunks that belong to several entities

A chunk has no entity labels of its own: it carries its document's metadata (`chunk.meta`, stored in ChromaDB as `meta_json`). Membership is decided when a question runs, by `scope_filter`. A chunk is in an entity's scope when:
- its field holds that entity's value; multi-valued fields such as `parties: BragsLabs; Acme Corp` put it in every listed party's scope;
- its field holds a global value (`ALL`, `GLOBAL`, blank), which puts it in every entity's scope (1,944 of the 13,187 HR chunks on tier L);
- for title-derived types, its parent field matches. Every office in a country shares that country's chunks; the office name in the query text decides ranking within them.

The `Entities:` line in the chunk header lists every name mentioned in the text. It helps search, but it doesn't add scope membership: an India chunk that mentions Germany isn't in Germany's scope.

In the coverage loop, each scope tracks the chunks it has seen separately. A shared chunk is therefore judged once per scope, and evidence is extracted for each scope's entity, so a company-wide table counts as evidence for every country it covers. Hits are returned per (scope, chunk) pair, and telemetry reports `shared_chunks`. The full runtime removes duplicate records (same entity, attribute, value, document and span) before computing, so a fact extracted twice isn't counted twice in means or shares. The benchmark's cross-encoder judge caches scores per chunk, since its score doesn't depend on the scope.

## Config reference

```yaml
name: legal                       # used in store collection names and outputs
description: ...                  # shown to the LLM classifier
fields:                           # generic role -> front-matter field name
  doc_id: doc_id
  doc_type: doc_type
  title: title
  version: version
  effective_date: effective_date
  status: status
  period: period                  # month '2026-05', quarter '2026-Q2' or year '2026'
field_aliases:                    # field -> alternative names that fill it when missing
  employee_category: [employee_group]
defaults:                         # field -> value when a document has none
  jurisdiction: ALL
global_values: [ALL, ""]          # values meaning "applies to every entity"
status:
  active: [in force, current, ""]
  pending: [signed, announced]
  superseded: [superseded, terminated]
version_terms: '\bversions?\b|\bamendments?\b'   # regex: the question names versions

entity_types:                     # priority order
  - name: party
    plural: parties               # used by the keyword classifier ("which parties ...")
    field: parties                # front-matter field holding the value(s)
    multi: true
    match_partial: true
    ignore: [BragsLabs]
    topic: '\bparties\b|\bvendors?\b'   # regex: the question is about this type
  - name: jurisdiction
    plural: jurisdictions
    field: jurisdiction
    default_fanout: true          # corpus-wide questions decompose over this type
    in_header: true               # list mentioned names in each chunk's "Entities:" header
    names: {US-NY: New York}      # value -> display name
    aliases: {NY: New York}       # alias -> display name
  # a title-derived type:
  # - name: office
  #   plural: offices
  #   from_title: {doc_types: [office_handbook], pattern: '^(.*?)\s+office handbook'}
  #   parent: country

item_nouns: [contracts, clauses]  # other plural nouns questions select ("which contracts ...")
record_types:                     # doc_type -> regex of words that ask for it
  case_note: '\bcases?\b|\bcourts?\b'
type_hints:                       # query type -> extra regexes for the keyword classifier
  version_diff: ['\bamend(ed|ment)\b.*\bchang']
source_roles:                     # conflict scan only: which document types state, update or restate values
  primary: [contract]             #   the authoritative source (its current version applies)
  update: [amendment]             #   documents that change a primary value (pending ones do not apply yet;
                                  #   superseded ones never do; the latest effective one wins)
  secondary: [standard]           #   restating sources; they never win a disagreement
                                  # HR: policy_manual_chapter / hr_circular / faq, office_handbook, benefits_summary
header: >-                        # chunk header; {field} = metadata value or 'unspecified'
  Document: {title_or_id} [{doc_id}] | Type: {doc_type} | Section: {section} |
  Jurisdiction: {jurisdiction} | Parties: {parties} | Entities: {entities}
```

Header placeholders: any metadata field name, plus `{title_or_id}`, `{doc_id}`, `{section}` (heading path) and `{entities}`.

## Using a new corpus

1. Put documents in a folder as `.md`, `.markdown` or `.txt` files. YAML-style front matter between `---` lines is optional; without it, the doc id is the relative path and the title is the first `# ` heading.
2. Write a domain config, starting from `legal.yaml`.
3. Check the entities:
   ```bash
   python -m lensrag.cli entities --domain my.yaml --corpus my_docs
   ```
4. Build the index (stored in ChromaDB, with the inventory beside it):
   ```bash
   python -m lensrag.cli build-index --domain my.yaml --corpus my_docs --index-dir artifacts/index_my
   ```
5. Ask questions. This needs an LLM: `LENSRAG_LLM_STACK=local-qwen-14b` for local models, or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. The index directory remembers the domain:
   ```bash
   python -m lensrag.cli ask "Which contracts with Acme allow termination on under 60 days notice?" --index-dir artifacts/index_my
   ```

`tests/fixtures/legal_corpus/` is a six-document example (contracts, an amendment history, a group standard and a case note). `tests/test_domains.py` runs ingestion, planning, scope filtering, storage and a stand-in-LLM pipeline on it.

## What is still HR- or BragsLabs-specific

- **The benchmark runner** (`run`) expects the BragsLabs zip layout: `manifest.jsonl` with S/M/L tiers, `corpus/`, and `gold/questions.jsonl`. `--domain` changes how that corpus is interpreted, but evaluating another corpus needs its own gold file and loader.
- **The keyword classifier's base patterns** are English and tuned on the 89 HR gold questions. Configs add phrasing through `type_hints` and `item_nouns`; the full runtime's LLM classifier is the main path for new domains.
- **Periods** are parsed as months, quarters and years (`2026-05`, `2026-Q2`, `2026`); other period formats need a code change in `planning.period_range`.
- **Entities named only in body text** aren't extracted. The inventory reads metadata and titles only. A text-based extractor (NER or an LLM pass at ingestion) would be the next step for corpora without good front matter.
