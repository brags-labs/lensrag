from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
import json, time
from collections import Counter, defaultdict
from ..data import ensure_extracted, load_documents, load_folder, chunk_document
from ..domain import load_domain
import re
from ..aggregation import (validate_evidence_records, aggregate_records, completeness_report, find_conflicts,
                           resolve_versions, reduce_labels, normalize_label, numbers_in, number_provenance)
from ..estimation import (stratified_sample, soft_labels, majority_category, stratified_estimate,
                          stratified_difference, category_shares)
from ..planning import (QUERY_TYPES, plan_query, build_scopes, build_inventory, scope_filter,
                        explicit_direction, parse_threshold, parse_versions, parse_k)
from ..synthesis import consistent_insights
from ..retrieval import coverage_retrieve
from .index import DenseEncoder, PersistentHybridIndex, corpus_fingerprint
from .providers import create_llm
from .routing import role as _role, stack_components
from .local_models import Reranker, EntityNER, NLIVerifier, SentimentClassifier

@dataclass
class PipelineConfig:
    tier: str = "L"
    domain: str = "hr"              # built-in domain name or path to a domain .yaml/.json
    corpus_dir: str | None = None   # a folder of .md/.txt files; None = the BragsLabs zip corpus
    index_dir: str = "artifacts/index_L"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_model: str | None = None     # None = the provider's default (claude-opus-5-5 / gpt-4o-mini)
    llm_provider: str | None = None  # anthropic | openai | ollama | auto (see full/providers.py)
    llm_stack: str | None = None     # per-stage model preset, e.g. local-qwen (see full/routing.py)
    page_size: int = 5              # chunks fetched per entity scope per round
    adaptive_round_limit: int = 4   # safety cap; the loop normally stops when no new relevant evidence appears
    allow_lexical_fallback: bool = False
    # Step 7, Mode B (estimated): when more records are in scope than this, sample instead of reading all.
    max_exact_records: int = 150
    sample_size: int = 150           # total sampled records across strata (proportional allocation)
    label_passes: int = 3            # independent labelling passes per sampled record (label uncertainty)
    label_batch: int = 10            # records per labelling call
    # Step 7, Mode C (generated): repeated reduce runs and the share of runs an insight needs.
    reduce_runs: int = 5
    support_threshold: float = 0.5
    seed: int = 42
    # Open-source components from Table 3.1 (full/local_models.py). None = off. The local stacks
    # (llm_stack="local-qwen", ...) switch them on; see routing.LOCAL_COMPONENTS.
    reranker_model: str | None = None   # Search + rerank for local questions, e.g. BAAI/bge-reranker-v2-m3
    rerank_candidates: int = 20         # passages retrieved before reranking down to page_size
    spacy_model: str | None = None      # NER fallback for entity selection, e.g. en_core_web_sm
    nli_model: str | None = None        # NLI claim verification, e.g. cross-encoder/nli-deberta-v3-large
    sentiment_model: str | None = None  # per-record sentiment soft labels in Mode B
    components_from_stack: bool = True  # fill unset component fields from the stack's preset
    # Question type: "rules" = the rule-based classifier decides and the LLM only supplies
    # parameters (entities, k, threshold); "llm" = the LLM's type wins (the 21-22 Nov run).
    # A 3B classifier was right on 39% of types against the rules' 100% on the benchmark.
    type_source: str = "rules"
    # Record logs: answer from parsed record fields (exact) when the fields can express the
    # question; otherwise fall back to sampling and labelling (Mode B).
    record_fields: bool = True
    # Latency (see docs and `fast_config`): read table facts once at load time and answer from
    # them in code; skip LLM steps whose work code already did.
    fact_table: bool = True          # answer from index-time table facts when they cover the question
    llm_classify: bool = True        # False: the rules plan alone (no classify call)
    template_answers: bool = False   # True: write computed answers in code (no write/finalize calls)
    llm_verify: bool = True          # False: NLI + number provenance only (no verify call)
    as_of_date: str | None = None    # ISO date for "in force now"; None = today
    doc_catalogue: bool = True       # answer questions about which documents exist from index metadata
    llm_workers: int = 1             # concurrent LLM calls per retrieval round (a local server needs as many parallel slots)


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def fast_config(cfg):
    """The low-latency profile: one resident model, no LLM step that code already covers."""
    cfg.llm_classify=False; cfg.template_answers=True; cfg.llm_verify=False
    cfg.adaptive_round_limit=min(cfg.adaptive_round_limit,2)
    # Mode B: one labelling pass over a smaller sample in bigger batches (wider intervals, stated);
    # Mode C: fewer repeated reduce runs.
    cfg.label_passes=1; cfg.sample_size=min(cfg.sample_size,60); cfg.label_batch=max(cfg.label_batch,20)
    cfg.max_exact_records=min(cfg.max_exact_records,60); cfg.reduce_runs=min(cfg.reduce_runs,2)
    # Judge the scopes of a retrieval round together: Ollama with OLLAMA_NUM_PARALLEL=4 decodes four
    # requests at about 2.5x the throughput of one (memory-bound decoding on Apple silicon).
    cfg.llm_workers=int(os.getenv("LENSRAG_LLM_WORKERS") or max(cfg.llm_workers,4))
    return cfg


def apply_stack_components(cfg):
    """Fill component fields the caller left unset from the stack's preset (full/routing.py)."""
    # The stack can come from the config or, like the LLM client (providers.create_llm), from
    # LENSRAG_LLM_STACK, so a run configured by environment gets the same components.
    cfg.llm_stack = cfg.llm_stack or os.getenv("LENSRAG_LLM_STACK") or None
    if not (cfg.llm_stack and cfg.components_from_stack):
        return cfg
    for name, value in stack_components(cfg.llm_stack).items():
        current = getattr(cfg, name, None)
        if name == "embedding_model":
            if current == DEFAULT_EMBEDDING_MODEL and value:
                cfg.embedding_model = value
        elif current is None:
            setattr(cfg, name, value)
    return cfg

class LensRAGPipeline:
    """End-to-end LensRAG (steps 3-9): plan, decompose, cover, filter+extract, compute, verify, answer."""
    def __init__(self, index, inventory, llm, config):
        self.index,self.inventory,self.llm,self.config=index,inventory,llm,apply_stack_components(config)
        c=self.config
        self.reranker=Reranker(c.reranker_model) if c.reranker_model else None
        self.ner=EntityNER(c.spacy_model) if c.spacy_model else None
        self.nli=NLIVerifier(c.nli_model) if c.nli_model else None
        self.sentiment=SentimentClassifier(c.sentiment_model) if c.sentiment_model else None
        self.domain=load_domain(inventory.get("domain_source") or inventory.get("domain") or config.domain)

    @classmethod
    def build(cls, corpus_zip, extract_dir, config=None, use_llm=True):
        cfg=apply_stack_components(config or PipelineConfig()); domain=load_domain(cfg.domain)
        if cfg.corpus_dir:
            docs=load_folder(Path(cfg.corpus_dir),domain)
        else:
            docs=load_documents(ensure_extracted(Path(corpus_zip),Path(extract_dir)),cfg.tier,domain)
        chunks=[x for d in docs for x in chunk_document(d,domain=domain)]
        if not chunks: raise RuntimeError("No chunks found in selected tier")
        encoder=DenseEncoder(cfg.embedding_model)
        idx=PersistentHybridIndex(chunks,encoder=encoder)
        fp=corpus_fingerprint(chunks); idx.save(cfg.index_dir,fp)
        inventory=build_inventory(docs,domain)
        llm=create_llm(cfg.llm_provider,cfg.llm_model,cfg.llm_stack) if use_llm else None
        Path(cfg.index_dir).joinpath("entities.json").write_text(json.dumps(inventory,indent=2),encoding="utf-8")
        return cls(idx,inventory,llm,cfg)

    @classmethod
    def load(cls, index_dir, config=None, use_llm=True):
        cfg=config or PipelineConfig(index_dir=str(index_dir)); idx,meta=PersistentHybridIndex.load(index_dir)
        ep=Path(index_dir)/"entities.json"
        inventory=json.loads(ep.read_text()) if ep.exists() else None
        if not isinstance(inventory,dict) or "entities" not in inventory:  # missing or an older format
            inventory=build_inventory(idx.chunks,load_domain(cfg.domain))
        llm=create_llm(cfg.llm_provider,cfg.llm_model,cfg.llm_stack) if use_llm else None
        pipe=cls(idx,inventory,llm,cfg)
        pipe.index_dir=str(index_dir)
        return pipe

    def ask(self, question: str):
        if not self.llm: raise RuntimeError("Query answering requires an LLM: set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY and load with use_llm=True.")
        t0=time.perf_counter()
        plan=self._plan(question)                                    # step 3
        scopes=build_scopes(plan,self.inventory,self.domain)         # step 4
        aggregate=None; flags=[]; estimate=None; synthesis=None; hits=[]; telemetry={}; rejected=[]
        fact_answer=self._fact_answer(question,plan,scopes) if self.config.fact_table else None
        field_answer=None if fact_answer else (self._field_estimate(question,plan,scopes) if plan.doc_types and self.config.record_fields else None)
        if not (fact_answer or field_answer) and self.config.doc_catalogue:
            fact_answer=self._catalogue_answer(question,plan)   # questions about which documents exist
        if fact_answer:
            # Reference facts stated in tables: read at load time, selected and computed in code.
            records,aggregate,flags,hits,telemetry=fact_answer
            plan.mode="exact"
        elif field_answer:
            # Record logs whose fields express the question: read every record in scope, exactly.
            estimate,records,sampled=field_answer
            hits=[(c,0.0,lab,None) for lab,c in sampled]
            telemetry={"mode":"record fields","scopes":len(scopes),"records":estimate.get("records_in_scope")}
            plan.mode="exact"
        elif plan.doc_types and plan.mode in ("estimated","generated"):
            # Step 7, Mode B: record logs are sampled and labelled, then estimated in code (exact when small).
            estimate,records,sampled=self._estimate(question,plan,scopes)
            hits=[(c,0.0,lab,None) for lab,c in sampled]
            telemetry={"mode":"sampled" if not estimate.get("exact") else "all records","scopes":len(scopes)}
            if plan.mode=="generated":                               # Mode C on top of the estimates
                synthesis=self._synthesise(question,plan,records,{"estimate":estimate},[c.doc_id for _,c in sampled])
        elif plan.qtype=="local" and self.reranker:
            # Local path (Figure 1.1): hybrid search, cross-encoder rerank, then LLM filter + extract.
            hits,telemetry=self._local_retrieve(question,plan,scopes)
            rejected=[x for *_,payload in hits for x in (payload or {}).get("rejected",[])]
            records,bad=validate_evidence_records(_unique_records(hits)); rejected.extend(bad)
        else:
            mapping=plan.operation=="map_reduce"
            hits,telemetry=coverage_retrieve(self.index,plan,scopes,  # step 5: loop until no new relevant evidence
                                             judge=self._llm_judge(question,extract=not mapping),
                                             page=self.config.page_size,max_rounds=self.config.adaptive_round_limit,
                                             workers=self.config.llm_workers)
            rejected=[x for *_,payload in hits for x in (payload or {}).get("rejected",[])]
            if mapping:                                              # Mode C: map, count in code, consistent reduce
                records,aggregate=self._map(question,hits,plan)
                synthesis=self._synthesise(question,plan,records,aggregate,[c.doc_id for c,*_ in hits])
            else:
                records,bad=validate_evidence_records(_unique_records(hits))  # step 6
                rejected.extend(bad)
                records,outside=self._in_version(records,plan)
                rejected.extend(outside)
                if plan.qtype!="local":                              # Mode A: deterministic code
                    aggregate,flags=self._compute(plan,records)
        mode=plan.mode if not (estimate and estimate.get("exact") and plan.mode=="estimated") else "exact"
        templated=self._template(plan,aggregate,records,estimate,synthesis) if self.config.template_answers else None
        if templated:
            answer=templated
        elif plan.qtype=="local" and not plan.doc_types and not fact_answer:
            answer=self._generate_local(question,hits)
        else:
            answer=self._write(question,plan,mode,records,aggregate,estimate,synthesis,flags)
        self._evidence_text=[c.enriched_text for c,*_ in hits]  # with the context header, for NLI
        verification=self._verify(question,plan,scopes,answer,records,flags,estimate,synthesis)   # step 8
        if not templated:
            answer=self._finalize(question,answer,records,verification)        # step 9
        else:
            note=disclosures(verification)   # step 9 for a templated answer: disclosed in code, no LLM call
            if note: answer=answer.rstrip()+"\n"+note
        evidence_text=[c.text for c,*_ in hits]
        verification["number_provenance"]=self._number_check(question,answer,records,aggregate,estimate,synthesis,
                                                             evidence_text,[c.doc_id for c,*_ in hits])
        return {"query_type":plan.qtype,"type_source":self.config.type_source,"llm_qtype":getattr(self,"_llm_qtype",None),
                "answer_source":(telemetry.get("mode") if telemetry.get("mode") in ("fact table","document catalogue") else None),"templated":bool(templated),
                "computation_mode":mode,"plan":plan.to_dict(),"answer":answer,
                "deterministic_result":aggregate,"estimate":estimate,"insights":synthesis,
                "retrieved_chunks":[{"chunk_id":c.chunk_id,"doc_id":c.doc_id,"scope":lab,"score":sc} for c,sc,lab,_ in hits],
                "evidence_records":records,"verification":verification,"rejected_evidence":rejected,
                "adaptive_retrieval":telemetry,"latency_ms":round((time.perf_counter()-t0)*1000,2)}

    def _local_retrieve(self, question, plan, scopes):
        """Retrieve rerank_candidates per scope, keep the reranker's best page_size, then judge them."""
        judge=self._llm_judge(question,extract=True); pages=[]
        for sc in scopes:
            cands=self.index.search(sc.query,self.config.rerank_candidates,where=scope_filter(plan,sc,self.domain))
            pages.append((sc,self.reranker.rerank(question,cands,self.config.page_size)))
        run=lambda x:[(c,s,x[0].label,payload) for c,s,payload in judge(*x)]
        if self.config.llm_workers>1 and len(pages)>1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.llm_workers) as pool: hits=[h for hs in pool.map(run,pages) for h in hs]
        else:
            hits=[h for x in pages for h in run(x)]
        return hits,{"reranker":self.reranker.model_name,"candidates":self.config.rerank_candidates,
                     "kept":self.config.page_size,"scopes":len(scopes),"converged":True}

    # --- step 3: understand the question ------------------------------------------------
    def _plan(self, question):
        """LLM classification and parameters; the rule-based planner fills or replaces invalid fields."""
        entities=self.inventory.get("entities",{})
        by_name={t:{e["name"]:e["value"] for e in items} for t,items in entities.items()}
        if not self.config.llm_classify and self.config.type_source!="llm":
            self._llm_qtype=None
            ner_named={}
            if self.ner:
                for t,vals in self.ner.match(question,self.inventory,self.domain).items(): ner_named[t]=list(vals)
            rule=plan_query(question,self.inventory,None,self.domain)
            # an entity the question excludes ('excluding the Netherlands') is not a named one
            ner_named={t:[v for v in vals if v not in rule.excluded.get(t,[])] for t,vals in ner_named.items()}
            ner_named={t:v for t,v in ner_named.items() if v}
            return rule if rule.named or not ner_named else plan_query(question,self.inventory,{"named":ner_named},self.domain)
        out=_role(self.llm,"classify").json(
            f"Classify a question about this corpus ({self.domain.description or self.domain.name}) and extract its parameters. "
            "Return JSON {qtype, named, excluded, versions, direction, k, threshold, comparator}. qtype is one of: "+", ".join(QUERY_TYPES)+". "
            "local = one fact from one or few passages; count = how many entities; extremum = single highest/lowest; "
            "rank = ordered list or top-K; filter = entities meeting a condition; aggregate = average or share over records; "
            "comparison = values compared across periods or entities; temporal = value at a point in time; "
            "version_diff = differences between versions; theme = common categories/topics; "
            "sentiment_shift = sentiment change over time; conflict = contradictions between documents. "
            "named / excluded: objects mapping an entity type to the names (from the supplied inventory only) that the "
            "question names / excludes. versions: like \"3.0\". direction: desc for highest-first, asc for lowest-first. "
            "k: the number asked for (\"top three\" = 3) or null. threshold: the number in a condition or null; "
            "comparator: gte|gt|lte|lt|eq or null. Never invent values.",
            json.dumps({"question":question,"entity_types":{t:list(names) for t,names in by_name.items()}}))
        def pick(key):
            raw=out.get(key) if isinstance(out.get(key),dict) else {}
            return {t:[by_name[t][n] for n in names if n in by_name.get(t,{})]
                    for t,names in raw.items() if t in by_name and isinstance(names,list)}
        named,excluded=pick("named"),pick("excluded")
        if self.ner:  # Table 3.1: entity-list lookup + spaCy NER, LLM as fallback
            for t,vals in self.ner.match(question,self.inventory,self.domain).items():
                named.setdefault(t,[])
                named[t]+=[v for v in vals if v not in named[t] and v not in excluded.get(t,[])]
        self._llm_qtype=out.get("qtype")
        if self.config.type_source!="llm":
            rule=plan_query(question,self.inventory,None,self.domain)
            if rule.named:  # the rules found the entities: the LLM may only add parameters, not entities
                named,excluded=dict(rule.named),dict(rule.excluded)
        overrides={"qtype":out.get("qtype") if self.config.type_source=="llm" else None,"direction":out.get("direction") if out.get("direction") in ("asc","desc") else None,
                   "k":out.get("k") if isinstance(out.get("k"),int) and out.get("k")>0 else None,
                   "threshold":out.get("threshold") if isinstance(out.get("threshold"),(int,float)) else None,
                   "comparator":out.get("comparator") if out.get("comparator") in ("gte","gt","lte","lt","eq") else None,
                   "named":{t:v for t,v in named.items() if v},"excluded":{t:v for t,v in excluded.items() if v},
                   "versions":[str(v) for v in out.get("versions") or [] if str(v) in self.inventory.get("versions",[])]}
        if self.config.type_source!="llm":
            # Rules first for parameters too: what the question states in words ("highest",
            # "more than 16", "version 2.0") wins; the LLM only fills what the rules can't find.
            stated=explicit_direction(question)
            if stated: overrides["direction"]=stated
            thr,comp=parse_threshold(question)
            if thr is not None: overrides["threshold"],overrides["comparator"]=thr,comp
            vers=parse_versions(question,self.domain.version_terms)
            if vers: overrides["versions"]=vers
            k=parse_k(question)
            if k: overrides["k"]=k
        return plan_query(question,self.inventory,overrides,self.domain)

    # --- steps 5-6: relevance filter + evidence extraction during retrieval -------------------
    def _llm_judge(self, question, extract=True):
        """Judge a page of passages for one scope in a single LLM call, extracting records if asked."""
        def judge(scope, items):
            passages=[{"index":i,"doc_id":c.doc_id,"version":c.version,"status":c.status,"effective_date":c.effective_date,
                       "period":c.period,"passage":c.text} for i,(c,_) in enumerate(items)]
            task=("Decide for each passage whether it contains evidence that helps answer the question for the given scope; "
                  "a passage covering several entities (e.g. a table of all countries) is relevant if it covers the scope's entity. "
                  "Return JSON {passages:[{index, relevant:boolean, records:[{entity, attribute, value, evidence_span}]}]}. ")
            if extract:
                task+=("For relevant passages extract explicit facts as records: entity is the "
                       +", ".join(t.name for t in self.domain.entity_types)+" (or other entity) the fact is about; value is a JSON number when numeric (units belong in attribute), true/false for yes/no criteria, "
                       "otherwise a short string; evidence_span must be copied verbatim from the passage. Extract only facts about the "
                       "scope's entity (all entities when the scope is 'all'). Do not infer missing facts.")
            else:
                task+="Return empty records lists."
            out=_role(self.llm,"extract").json(task,json.dumps({"question":question,"scope":scope.label,"passages":passages}))
            verdicts={v.get("index"):v for v in out.get("passages",[]) if isinstance(v,dict)}
            kept=[]
            for i,(c,s) in enumerate(items):
                v=verdicts.get(i) or {}
                if not v.get("relevant"): continue
                records,rejected=[],[]
                for r in v.get("records") or []:
                    if not isinstance(r,dict): continue
                    span=str(r.get("evidence_span") or "")
                    if span and span in c.text:
                        records.append(dict(r,doc_id=c.doc_id,version=c.version,status=c.status,
                                            effective_date=c.effective_date,period=c.period,scope=scope.label))
                    else:
                        rejected.append({"doc_id":c.doc_id,"reason":"evidence span not verbatim"})
                kept.append((c,s,{"records":records,"rejected":rejected}))
            return kept
        return judge

    # --- step 7: deterministic computation ----------------------------------------------
    def _compute(self, plan, records):
        """Run the plan's operation in code. Returns (result, version/conflict flags)."""
        statuses=dict(active_statuses=self.domain.active_statuses,pending_statuses=self.domain.pending_statuses)
        records=self._canonical_entities(records)
        _,flags=resolve_versions(records,**statuses)
        op=plan.operation
        if op=="conflict":
            return None,find_conflicts(records)
        if op is None:
            return None,flags
        if op=="filter" and plan.threshold is None and not any(isinstance(r.get("value"),bool) for r in records):
            return None,flags  # criterion is not numeric or yes/no: leave the judgement to the grounded answer
        result=aggregate_records(records,op,top_k=plan.k,threshold=plan.threshold,
                                 comparator=plan.comparator or "gte",direction=plan.direction,
                                 resolve=plan.qtype not in {"version_diff","comparison","temporal"},**statuses)
        return result,flags

    # --- reference facts from tables (index time) ---------------------------------------------
    FACT_TYPES=("local","extremum","rank","filter","count","version_diff")

    def _facts(self):
        if getattr(self,"_fact_index",None) is None:
            from ..facts import build_facts
            self._fact_index=build_facts(self.index.chunks,skip_types=set(self.domain.record_types))
            self._chunk_by_id={c.chunk_id:c for c in self.index.chunks}
            self._attr_vecs={}
        return self._fact_index

    def _attr_similarity(self, question, attrs):
        """Cosine similarity of the question to each attribute label (dense encoder, cached)."""
        enc=getattr(self.index,"encoder",None)
        if enc is None:   # lexical fallback: shared words
            qw=set(re.findall(r"[a-z]{3,}",question.lower()))
            return [len(qw&set(re.findall(r"[a-z]{3,}",a.lower())))/(1+len(set(re.findall(r"[a-z]{3,}",a.lower())))) for a in attrs]
        import numpy as np
        todo=[a for a in attrs if a not in self._attr_vecs]
        if todo:
            for a,v in zip(todo,enc.encode(todo)): self._attr_vecs[a]=np.asarray(v,dtype=float)
        q=np.asarray(enc.encode([question])[0],dtype=float)
        def cos(v): return float(v@q/((np.linalg.norm(v)*np.linalg.norm(q)) or 1))
        return [cos(self._attr_vecs[a]) for a in attrs]

    def _fact_answer(self, question, plan, scopes):
        """Answer from table facts: pick the attribute the question asks about, collect its value
        per scope, compute in code. Returns (records, aggregate, flags, hits, telemetry) or None
        when the facts don't cover the question (the retrieval path then runs as before)."""
        if plan.qtype not in self.FACT_TYPES or plan.doc_types or plan.operation=="conflict":
            return None
        criteria=plan.operation in ("all_of","any_of")   # 'offices with both a gym and a crèche
        from ..facts import norm_attr
        facts=self._facts()
        entity_scopes=[sc for sc in scopes if sc.entity_value]
        fanout=len({sc.entity_value for sc in entity_scopes})>1
        nouns="|".join(re.escape(n.lower()) for n in self.domain.entity_nouns) or "items"
        # a global rule ('office days under version 2.0'): no entity named and none asked about
        lookup=(plan.qtype=="local" or (plan.qtype=="version_diff" and len(plan.versions)<=1)) \
            and not plan.named and not re.search(rf"\b({nouns})\b",question.lower())
        if lookup: fanout=False
        if plan.qtype in ("extremum","rank","filter","count") and not fanout:
            return None   # counting or ranking documents, not entities: not a table-fact question
        if plan.qtype=="count" and not re.search(rf"\b({nouns})\b",question.lower()):
            return None   # 'how many circulars ...' counts documents, not entities
        pool=[]
        for sc in scopes:
            keep=scope_filter(plan,sc,self.domain)
            for cid,fs in facts.items():
                c=self._chunk_by_id[cid]
                if not keep(c): continue
                own={str(c.country),str((c.meta or {}).get("office") or "")} if isinstance(c.meta,dict) else {str(c.country)}
                specific=bool(sc.entity_value) and sc.entity_value in own
                for f in fs:
                    if f.get("reference"): continue
                    if lookup and specific: continue        # a global question reads the global rule
                    name="all" if lookup or not sc.entity_value else _entity_label(sc,self.inventory)
                    if f.get("subject") and sc.entity_value and f["subject"]!=name and not specific: continue
                    pool.append(dict(f,entity=name,scope=sc.label,specific=specific,chunk=c))
        if not pool: return None
        pool=list({(f["entity"],f["chunk_id"],f["evidence_span"],f["attribute"]):f for f in pool}.values())
        by_attr=defaultdict(list)
        for f in pool: by_attr[norm_attr(f["attribute"])].append(f)
        attrs=list(by_attr)
        sims=self._attr_similarity(question,[by_attr[a][0]["attribute"] for a in attrs])
        n_ent=max(1,len({sc.entity_value for sc in entity_scopes}))
        def cover(a): return len({f["entity"] for f in by_attr[a] if f["specific"] or not fanout})/n_ent
        scored=[(a,sim+(0.15*cover(a) if fanout else 0)) for a,sim in zip(attrs,sims) if not fanout or cover(a)>=0.5]
        top=sorted(scored,key=lambda x:-x[1])[:12]
        if not top: return None
        cands=[{"id":i,"attribute":by_attr[a][0]["attribute"],
                "examples":"; ".join(sorted({f"{f['entity']}: {f['value'][:40]}" for f in by_attr[a]})[:3]),
                "entities":len({f["entity"] for f in by_attr[a]})} for i,(a,_) in enumerate(top)]
        try:
            pick=_role(self.llm,"extract").json(
                ("The question lists several yes/no criteria. Pick the table attribute(s) that state each criterion; "
                 "return JSON {criteria:[{criterion, attribute_ids:[int], required:boolean}], answerable:boolean}. required is "
                 "false when the question asks for the criterion to be absent ('a gym but no crèche': the crèche has "
                 "required false). answerable is false when a criterion has no matching attribute." if criteria else
                 "Pick the table attribute(s) that state the quantity the question asks about. Several ids may be "
                 "the same quantity worded differently in different documents; return all of those. Return JSON "
                 "{attribute_ids:[int], answerable:boolean}. answerable is false when none of them is the asked "
                 "quantity (a related but different quantity is not enough: annual leave days are not office days)."),
                json.dumps({"question":question,"candidates":cands},ensure_ascii=False))
        except Exception:
            return None
        if criteria:
            return self._fact_criteria(plan,pick,top,by_attr,cands,entity_scopes,question)
        ids=[i for i in (pick or {}).get("attribute_ids") or [] if isinstance(i,int) and 0<=i<len(top)]
        if not ids or pick.get("answerable") in (False,"false","no"): return None
        chosen=[f for i in ids for f in by_attr[top[i][0]]]
        # per entity, facts from the entity's own documents beat global ones
        specific={f["entity"] for f in chosen if f["specific"]}
        chosen=[f for f in chosen if f["specific"] or f["entity"] not in specific]
        records=[]
        for f in chosen:
            v=f["number"] if f["number"] is not None else f["value"]
            records.append({k:f[k] for k in ("entity","attribute","evidence_span","doc_id","version","status",
                                                "effective_date","period","scope")}|{"value":v,"value_as_written":f["value"]})
        from ..aggregation import normalize_units
        asked=re.search(r"\b(working days|calendar days|weeks|days|hours|months|years)\b",question.lower())
        def in_asked_unit(r):
            if asked:   # the question's unit wins when the cell states the value in it
                m=re.search(rf"(\d+(?:\.\d+)?)\s+{re.escape(asked.group(1).rstrip('s'))}s?\b",str(r["value_as_written"]),re.I)
                if m: return dict(r,value=float(m.group(1)))
            return normalize_units(r)
        records=[in_asked_unit(r) for r in records]
        # A value announced from a later date is pending, not in force (unless the question asks about a date).
        as_of=self.config.as_of_date or __import__("datetime").date.today().isoformat()
        if plan.qtype!="temporal":
            records=[r for r in records if not str(r.get("effective_date") or "") > as_of]
        if plan.versions:   # 'under version X': the manual's own text beats undated documents for the same entity
            tagged={r["entity"] for r in records if str(r.get("version"))}
            records=[r for r in records if str(r.get("version")) or r["entity"] not in tagged]
        if plan.qtype=="version_diff" and len(plan.versions)>=2:
            aggregate=self._version_changes(plan,records)
            flags=[]
        else:
            records=self._in_force_under(records,plan)
            if not records: return None
            if plan.qtype=="version_diff": plan.qtype,plan.operation="local",None   # one version: a lookup
            covered={r["entity"] for r in records}
            if fanout and len(covered)<0.7*len({sc.entity_value for sc in entity_scopes}): return None   # facts too sparse
            if plan.qtype=="local" or plan.operation is None:
                statuses=dict(active_statuses=self.domain.active_statuses,pending_statuses=self.domain.pending_statuses)
                resolved,flags=resolve_versions(records,**statuses)
                aggregate=resolved[0] if len(resolved)==1 else resolved
            elif plan.qtype=="count" and plan.threshold is None and (year:=self._asked_year(question,records)):
                # 'how many offices opened in 2025': the year is the condition on a date-valued attribute
                hit=[r for r in records if re.search(rf"\b{year}\b",str(r["value_as_written"]))]
                aggregate={"count":len(hit),"entities":[{"entity":r["entity"],"value":r["value_as_written"]} for r in hit]}
                flags=[]
            elif plan.qtype=="count" and plan.threshold is not None:
                plan.operation="filter"
                aggregate,flags=self._compute(plan,records)
                aggregate={"count":len(aggregate or []),"entities":aggregate}
                plan.operation="count"
            else:
                aggregate,flags=self._compute(plan,records)
        if aggregate in (None,[],{}): return None
        hits=[(f["chunk"],0.0,f["scope"],None) for f in {id(f["chunk"]):f for f in chosen}.values()][:20]
        return records,aggregate,flags,hits,{"mode":"fact table","attributes":[cands[i]["attribute"] for i in ids],
                                             "facts":len(records),"scopes":len(scopes)}

    _YES=re.compile(r"^\s*(yes|y|true|available|provided|✓|✔)\b",re.I)
    _NO=re.compile(r"^\s*(no|n|false|none|not available|not provided|✗|✘)\b",re.I)

    _NEGATION=r"\b(no|not|neither|without|lacks?|lacking|nor|excluding|except)\b"

    @classmethod
    def criterion_wanted(cls, question, criterion, required=None):
        """Whether a criterion must hold (True) or be absent (False). The question's wording decides
        when it negates the criterion's words ('a gym but no crèche'); otherwise the model's
        'required' field, else True."""
        import unicodedata
        fold=lambda t:"".join(ch for ch in unicodedata.normalize("NFKD",str(t or "").lower()) if not unicodedata.combining(ch))
        ql=fold(question)
        for w in re.findall(r"[^\W\d_]{3,}",fold(criterion)):
            for m in re.finditer(rf"\b{re.escape(w[:max(3,len(w)-2)])}",ql):
                before=ql[max(0,m.start()-40):m.start()]
                tail=re.split(r"\b(and|but|or|with|while|whereas)\b|[,;]",before)[-1]
                if re.search(cls._NEGATION,tail): return False
                if re.search(rf"\b(does|do|did|is|are)n[’']t\b",tail): return False
            if re.search(rf"\b{re.escape(w[:max(3,len(w)-2)])}",ql): return True
        return required not in (False,"false","no",0)

    def _fact_criteria(self, plan, pick, top, by_attr, cands, entity_scopes, question=""):
        """all_of / any_of over yes/no table facts: the entities whose value for every (any) criterion
        matches what the question asks (present, or absent for 'no crèche'). An entity with a
        criterion unstated is left out; too few covered -> None."""
        raw=[c for c in (pick or {}).get("criteria") or [] if isinstance(c,dict)]
        crit,wanted=[],[]
        for c in raw:
            ids=[i for i in (c.get("attribute_ids") or []) if isinstance(i,int) and 0<=i<len(top)]
            if ids:
                crit.append(ids)
                wanted.append(self.criterion_wanted(question,c.get("criterion") or cands[ids[0]]["attribute"],c.get("required")))
        if len(crit)<2 or (pick or {}).get("answerable") in (False,"false","no"): return None
        per={}   # entity -> [bool per criterion]
        chosen=[]
        for k,ids in enumerate(crit):
            fs=[f for i in ids for f in by_attr[top[i][0]]]
            specific={f["entity"] for f in fs if f["specific"]}
            for f in fs:
                if not f["specific"] and f["entity"] in specific: continue
                yes=bool(self._YES.match(str(f["value"]))); no=bool(self._NO.match(str(f["value"])))
                if not (yes or no): continue
                per.setdefault(f["entity"],[None]*len(crit))[k]=(yes==wanted[k])
                chosen.append(f)
        n_ent=len({sc.entity_value for sc in entity_scopes})
        full={e:v for e,v in per.items() if None not in v}
        if not full or len(full)<0.7*n_ent: return None
        test=all if plan.operation=="all_of" else any
        keep=sorted(e for e,v in full.items() if test(v))
        records=[{"entity":f["entity"],"attribute":f["attribute"],"value":f["value"],"value_as_written":f["value"],
                  "evidence_span":f["evidence_span"],"doc_id":f["doc_id"],"version":f["version"],"status":f["status"],
                  "effective_date":f["effective_date"],"period":f["period"],"scope":f["scope"]} for f in chosen if f["entity"] in full]
        aggregate=[{"entity":e,"value":True,"value_as_written":("meets every criterion" if plan.operation=="all_of" else "meets a criterion")
                                      +(" (absent: "+", ".join(str(raw[k].get("criterion") or k) for k,w in enumerate(wanted) if not w)+")" if not all(wanted) else ""),
                    "doc_id":next((r["doc_id"] for r in records if r["entity"]==e),None)} for e in keep]
        hits=[(f["chunk"],0.0,f["scope"],None) for f in {id(f["chunk"]):f for f in chosen}.values()][:20]
        return records,aggregate or None,[],hits,{"mode":"fact table","attributes":[cands[i]["attribute"] for c in crit for i in c],
                                                   "facts":len(chosen),"scopes":len(entity_scopes)}

    CATALOGUE_TYPES=("count","version_diff","temporal","filter","local")

    def _catalogue_answer(self, question, plan):
        """Questions about which documents exist (how many addenda in v3.0, circulars issued in
        2025, countries covered by v1.0 or added in v3.0), answered from one metadata row per
        document. Returns the fact-answer tuple, or None when the question is about content."""
        if plan.qtype not in self.CATALOGUE_TYPES or plan.doc_types or plan.operation in ("conflict",):
            return None
        from ..doc_catalogue import build_catalogue, describe, run, DATE
        if getattr(self,"_doc_rows",None) is None:
            names={t:{e["value"]:e["name"] for e in items} for t,items in self.inventory.get("entities",{}).items()}
            self._doc_rows=build_catalogue(self.index.chunks,lambda t,v:names.get(t,{}).get(v,v),self.domain.global_values)
            self._doc_fields=describe(self._doc_rows)
        rows,fields=self._doc_rows,self._doc_fields
        starts={v:w[0] for v,w in self._version_windows().items()}
        system=("Decide whether the question is about which documents exist in a corpus, using only each document's "
                "metadata (type, title, version, country, office, dates, status), and if so map it to a query. Questions about "
                "values or rules stated INSIDE documents (allowances, leave days, office days, benefits, whether something is "
                "permitted, conflicts between documents) are NOT answerable here. Return JSON {answerable, operation, filters, "
                "target, minus_filters}. operation: count (documents matching filters) | count_distinct (distinct target values) "
                "| list (distinct target values). filters / minus_filters: [{field, op, value}], op eq | ne | in | contains | gte "
                "| gt | lte | lt; dates are ISO strings. minus_filters: documents whose target values are removed from the list "
                "('countries in version 3.0 but not in version 2.0'). target: the field to list or count distinct values of, "
                "or 'document' to list documents. Use field values exactly as listed. Version start dates are given for "
                "questions like 'after version 3.0 came into force'.")
        try:
            q=_role(self.llm,"extract").json(system,json.dumps({"question":question,"fields":fields,
                                                                 "version_start_dates":starts},ensure_ascii=False))
        except Exception:
            return None
        if not isinstance(q,dict) or q.get("answerable") in (False,"false","no",None) or \
                q.get("operation") not in ("count","count_distinct","list"):
            return None
        ql=question.lower(); named_starts={starts[v] for v in plan.versions if v in starts}
        def grounded(f,minus=False):
            """Every filter value comes from the question: its words, a number or year it states, or
            the start date of a version it names. 'exists' needs the question to name the field
            ('which countries'); a minus filter may use any listed value ('added in 3.0' implies
            the version before it)."""
            if not isinstance(f,dict) or f.get("field") not in fields or "value" not in f: return False
            if f.get("op")=="exists":
                return any(w[:5] in ql for w in re.findall(r"[a-z]{4,}",f["field"].replace("_"," ")))
            listed={str(x).lower() for x in fields[f["field"]].get("values",[])}
            for v in (f["value"] if isinstance(f["value"],list) else [f["value"]]):
                if minus and str(v).strip().lower() in listed: continue
                sv=str(v).strip().lower()
                if DATE.match(sv):
                    if sv not in named_starts and sv[:4] not in ql: return False
                elif re.fullmatch(r"\d+(\.\d+)?",sv):
                    if not re.search(rf"(?<![\d.]){re.escape(sv)}(?![\d])",ql): return False
                else:
                    words=re.findall(r"[a-z]{4,}",sv)
                    if not words or sum(w[:5] in ql for w in words)<max(1,(len(words)+1)//2): return False
            return True
        filters=q.get("filters") or []; minus=q.get("minus_filters") or []
        for f in filters:   # 'after <date>' is strictly after; 'before <date>' strictly before
            if isinstance(f,dict) and DATE.match(str(f.get("value",""))):
                if f.get("op")=="gte" and re.search(r"\bafter\b",ql) and not re.search(r"\bon or after\b",ql): f["op"]="gt"
                if f.get("op")=="lte" and re.search(r"\bbefore\b",ql) and not re.search(r"\bon or before\b",ql): f["op"]="lt"
        if not filters or not all(grounded(f) for f in filters) or not all(grounded(f,True) for f in minus): return None
        if q.get("target") and q["target"] not in fields: return None
        answer,hit=run(rows,{**q,"filters":filters,"minus_filters":minus})
        if answer is None or answer==[] or (q["operation"]!="list" and not hit): return None
        aggregate={"catalogue":answer,"operation":q["operation"],"target":q.get("target") or "document","query":q}
        records=[{"entity":r.get("country") or r.get("office") or "all","attribute":"document","value":r["document"],
                  "evidence_span":r.get("title") or r["document"],"doc_id":r["document"],"version":r.get("version",""),
                  "status":r.get("status"),"effective_date":r.get("effective_date",""),"period":None,"scope":"catalogue"}
                 for r in hit[:50]]
        by_doc={c.doc_id:c for c in self.index.chunks}
        hits=[(by_doc[r["document"]],0.0,"catalogue",None) for r in hit[:20] if r["document"] in by_doc]
        plan.mode="exact"
        return records,aggregate,[],hits,{"mode":"document catalogue","query":q,"documents":len(hit)}

    @staticmethod
    def _asked_year(question, records):
        """The year a count question conditions on, when the attribute's values are years or dates."""
        years=re.findall(r"\b(19\d\d|20\d\d)\b",question)
        if len(years)!=1 or not records: return None
        dated=sum(bool(re.search(r"\b(19|20)\d\d\b",str(r["value_as_written"]))) for r in records)
        return years[0] if dated>=0.8*len(records) else None

    def _version_changes(self, plan, records):
        """version_diff over facts: each entity's value under each asked version, and the changed ones."""
        by=defaultdict(dict)
        statuses=dict(active_statuses=self.domain.active_statuses,pending_statuses=self.domain.pending_statuses)
        for v in plan.versions:
            sub=self._in_force_under(records,type("P",(),{"versions":[v]})())
            tagged={r["entity"] for r in sub if str(r.get("version"))==v}
            sub=[r for r in sub if str(r.get("version"))==v or r["entity"] not in tagged]
            for r in resolve_versions(sub,**statuses)[0] if sub else []:
                by[r["entity"]][v]=r["value"]
        changed=[e for e,vals in by.items() if len(vals)==len(plan.versions) and len({str(x) for x in vals.values()})>1]
        return {"by_version":dict(by),"changed":sorted(changed),"versions":plan.versions} if by else None

    def _template(self, plan, aggregate, records, estimate, synthesis):
        """The answer written in code from a computed result, with citations; None when there is
        nothing computed (the LLM writes it then)."""
        def cite(rs): return " ".join(f"[{d}]" for d in dict.fromkeys(r.get("doc_id") for r in rs if r.get("doc_id")))
        def show(r): return f"{r['entity']}: {r.get('value_as_written', r['value'])}"
        a=aggregate
        if isinstance(a,dict) and "catalogue" in a:
            v=a["catalogue"]; what=a["target"].replace("_"," ")
            body=f"{v} ({'documents' if a['operation']=='count' else 'distinct '+what+'s'})" if not isinstance(v,list) else "; ".join(map(str,v))
            return f"[exact] From the document catalogue (index metadata): {body} " + cite(records[:20])
        if isinstance(estimate,dict) and estimate.get("kind")=="fields" and estimate.get("groups"):
            # every record in scope was read from its fields: the figures are exact
            lines=[]
            for g,v in estimate["groups"].items():
                if "categories" in v:
                    what=v.get("values_are","counts")
                    lines.append((f"{g}: " if g!="all" else "")+"; ".join(f"{c['category']} {round(c['count'],3)}" for c in v["categories"])
                                 +f" ({what})")
                else:
                    lines.append((f"{g}: " if g!="all" else "")+f"{v['estimate']} ({v.get('what','')}, n={v.get('n')})")
            return (f"[exact] Read from all {estimate.get('records_in_scope')} records in scope.\n" + "\n".join(lines)
                    + "\n" + cite(records))
        if isinstance(a,dict) and "changed" in a:
            lines=[f"{e}: "+", ".join(f"v{v} {a['by_version'][e].get(v,'not stated')}" for v in a["versions"]) for e in sorted(a["by_version"])]
            return (f"[exact] Changed between versions {' and '.join(a['versions'])}: {', '.join(a['changed']) or 'none'}.\n"
                    + "\n".join(lines) + "\n" + cite(records))
        if isinstance(a,dict) and "count" in a:
            ents=a.get("entities") or []
            return f"[exact] {a['count']}: " + ", ".join(show(r) for r in ents) + " " + cite(ents)
        if isinstance(a,dict) and "entity" in a:
            return f"[exact] {show(a)} " + cite([a])
        if isinstance(a,list) and a and isinstance(a[0],dict) and "entity" in a[0]:
            return "[exact] " + "; ".join(show(r) for r in a) + " " + cite(a)
        if isinstance(a,(int,float)) and not isinstance(a,bool):
            return f"[exact] {a} " + cite(records)
        return None

    def _version_windows(self):
        """version -> (first effective date, next version's first date or None), from the index."""
        if not hasattr(self,"_windows"):
            starts={}
            for c in self.index.chunks:
                if c.version and c.effective_date:
                    starts[c.version]=min(starts.get(c.version,c.effective_date),c.effective_date)
            order=sorted(starts,key=lambda v:starts[v])
            self._windows={v:(starts[v],starts[order[i+1]] if i+1<len(order) else None) for i,v in enumerate(order)}
        return self._windows

    def _in_version(self, records, plan, strict=False):
        """For a question about one version, keep the facts that held under it: records of that
        version, and unversioned ones (circulars, FAQs) dated inside its window. A circular that
        introduced the next version's rule otherwise competes with the version asked about."""
        if len(plan.versions)!=1:
            return records,[]
        v=plan.versions[0]; win=self._version_windows().get(v)
        if not win:
            return records,[]
        keep,drop=[],[]
        for r in records:
            rv=str(r.get("version") or ""); d=str(r.get("effective_date") or "")
            if rv:
                ok=rv==v
            elif d:
                ok=d>=win[0] and (win[1] is None or d<win[1])
            else:
                ok=True   # undated, unversioned: no evidence it belongs elsewhere
            (keep if ok else drop).append(r)
        if not keep and not strict:   # never empty the evidence on a metadata technicality
            return records,[]
        return keep,[{"doc_id":r.get("doc_id"),"reason":f"outside version {v}"} for r in drop]

    def _in_force_under(self, records, plan):
        """Facts that can hold under the one asked version: records tagged with it, and untagged
        ones (circulars, FAQs) dated before the next version began, so a change made earlier and
        still in force counts. Version resolution then keeps the latest per entity."""
        if len(plan.versions)!=1:
            return records
        v=plan.versions[0]; win=self._version_windows().get(v)
        if not win:
            return records
        out=[]
        for r in records:
            rv=str(r.get("version") or ""); d=str(r.get("effective_date") or "")
            if rv: ok=rv==v
            else: ok=not d or win[1] is None or d<win[1]
            if ok: out.append(r)
        return out

    def _canonical_entities(self, records):
        """Name each record's entity as the inventory does. A fact retrieved for the scope
        'India' may name the legal entity ('BragsLabs India Pvt. Ltd.'); counted as written,
        that is a second entity, and an answer naming it doesn't match the country."""
        names={e["name"] for items in (self.inventory.get("entities") or {}).values() for e in items}
        out=[]
        for r in records:
            if r.get("scope") in names and r.get("entity") not in names:
                r=dict(r,entity=r["scope"],entity_as_written=r.get("entity"))
            out.append(r)
        return out

    def _map(self, question, hits, plan):
        """Mode C, map: one call per entity scope labels each passage; code counts the labels."""
        by_scope=defaultdict(list)
        for c,_,label,_ in hits: by_scope[label].append(c)
        mapped=[]
        def map_scope(item):
            label,chunks=item
            return _role(self.llm,"map").json("For each passage, list the query-relevant themes or categories as short labels, its sentiment "
                              "(positive|negative|neutral|mixed|null) and a verbatim evidence_span. Return JSON {items:[{index, labels:[], "
                              "sentiment, evidence_span}]}. Do not invent.",
                              json.dumps({"question":question,"scope":label,"passages":[{"index":i,"period":c.period,"passage":c.text} for i,c in enumerate(chunks)]}))
        scopes=list(by_scope.items())
        if self.config.llm_workers>1 and len(scopes)>1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.llm_workers) as pool: outs=list(pool.map(map_scope,scopes))
        else:
            outs=[map_scope(x) for x in scopes]
        for (label,chunks),out in zip(scopes,outs):
            for item in out.get("items",[]):
                if not isinstance(item,dict) or not isinstance(item.get("index"),int) or not 0<=item["index"]<len(chunks): continue
                c=chunks[item["index"]]; span=item.get("evidence_span") or ""
                if (item.get("labels") or item.get("sentiment")) and span and span in c.text:
                    mapped.append({"labels":item.get("labels") or [],"sentiment":item.get("sentiment"),"period":c.period,
                                   "scope":label,"doc_id":c.doc_id,"evidence_span":span,"entity":label,"version":c.version})
        group_field="scope" if plan.qtype=="sentiment_shift" and len(plan.periods)>1 else "period"
        totals=Counter(normalize_label(l) for m in mapped for l in m["labels"])
        counts={"basis":"counts over the retrieved evidence, not the whole corpus",
                "top_labels":totals.most_common(plan.k) if plan.k else totals.most_common(),
                "by_group":reduce_labels(mapped,group_field),"items":len(mapped),
                "entities_per_label":{k:len({m["entity"] for m in mapped if k in {normalize_label(x) for x in m["labels"]}})
                                      for k,_ in totals.most_common(20)}}
        records=[{"entity":m["entity"],"attribute":plan.qtype,"value":v,"evidence_span":m["evidence_span"],"doc_id":m["doc_id"],
                  "version":m.get("version",""),"period":m.get("period",""),"scope":m["scope"]}
                 for m in mapped for v in (m["labels"] if plan.qtype=="theme" else [m["sentiment"]] if m.get("sentiment") else [])]
        return records,counts

    def _synthesise(self, question, plan, records, stats, evidence_doc_ids):
        """Mode C, reduce: k independent runs; keep insights most runs agree on, with support and citations."""
        notes=[{"entity":r.get("entity"),"period":r.get("period"),"value":r.get("value"),"doc_id":r.get("doc_id"),
                "evidence_span":r.get("evidence_span")} for r in records[:150]]
        return consistent_insights(_role(self.llm,"reduce"),question,notes,stats,evidence_doc_ids,k=self.config.reduce_runs,
                                   threshold=self.config.support_threshold,max_insights=plan.k or 5)

    def _estimate(self, question, plan, scopes):
        """Mode B: every record in scope (all chunks passing the scope filter) is the population.

        Small populations are labelled in full (exact). Larger ones are sampled per stratum
        (scope), each sampled record is labelled `label_passes` times, and the estimate and
        its 95% interval are computed in code. Returns (estimate, evidence records, [(scope, chunk)]).
        """
        cfg=self.config
        strata={sc.label:[c for c in self.index.chunks if scope_filter(plan,sc,self.domain)(c)] for sc in scopes}
        population=sum(len(v) for v in strata.values())
        full=population<=cfg.max_exact_records
        sample,sizes=stratified_sample(strata,population if full else cfg.sample_size,seed=cfg.seed)
        kind=("category" if plan.operation in ("mode","frequency","map_reduce") and plan.qtype!="sentiment_shift"
              else "sentiment" if plan.qtype=="sentiment_shift" else "number" if plan.operation in ("mean","sum") else "flag")
        passes=1 if full and kind!="sentiment" else cfg.label_passes
        if kind=="sentiment" and self.sentiment:
            passes=1  # the classifier gives a probability per record: already a soft label
        labelled={}  # (scope, chunk_id) -> {"applies":[...], "values":[...], "span":str}
        for label,chunks in sample.items():
            for i in range(0,len(chunks),cfg.label_batch):
                batch=chunks[i:i+cfg.label_batch]
                for run in range(passes):
                    labels=(self._classify_sentiment(batch) if kind=="sentiment" and self.sentiment
                            else self._label(question,kind,label,batch,run))
                    for c,lab in zip(batch,labels):
                        slot=labelled.setdefault((label,c.chunk_id),{"chunk":c,"applies":[],"values":[],"span":""})
                        slot["applies"].append(lab.get("applies"))
                        slot["values"].append(lab.get("value"))
                        span=str(lab.get("evidence_span") or "")
                        if span and span in c.text and not slot["span"]: slot["span"]=span
        records=[]; per_scope={}
        for label in sample:
            items=[v for (lab,_),v in labelled.items() if lab==label]
            rows=[]
            for it in items:
                # Majority of passes must agree the record is one the question is about.
                p_applies=soft_labels([[a] for a in it["applies"]])
                known=[x for x in p_applies if x is not None]
                if not known or sum(known)/len(known)<0.5: continue
                vals=[v for v in it["values"] if v is not None]
                rows.append((it,vals))
                if it["span"] and vals:
                    records.append({"entity":label.split(" / ")[0],"attribute":kind,"value":vals[0],"evidence_span":it["span"],
                                    "doc_id":it["chunk"].doc_id,"scope":label,"period":it["chunk"].period,
                                    "version":it["chunk"].version,"status":it["chunk"].status})
            applicable_share=len(rows)/max(1,len(items))
            per_scope[label]={"rows":rows,"population":round(sizes[label]*applicable_share) or len(rows),
                              "sampled":len(items),"records_in_scope":sizes[label]}
        estimate=self._summarise_estimate(plan,kind,per_scope,scopes)
        estimate.update({"kind":kind,"records_in_scope":population,"sampled_records":sum(len(v) for v in sample.values()),
                         "label_passes":passes,"exact":full and passes==1,
                         "method":"all records labelled once" if full and passes==1 else
                                  f"stratified random sample, {passes} labelling passes, 95% intervals"})
        sampled=[(lab,c) for lab,chunks in sample.items() for c in chunks]
        return estimate,records,sampled

    def _records(self):
        if getattr(self,"_record_index",None) is None:
            from ..records import build_records
            recs=build_records(self.index.chunks,set(self.domain.record_types))
            # sentiment labelled once at index time (label_records), read as an ordinary field
            from ..record_labels import load_labels, apply_labels
            path=Path(getattr(self,"index_dir",None) or self.config.index_dir)/"record_labels.json"
            self._labelled=apply_labels(recs,load_labels(path)) if path.exists() else 0
            by_chunk=defaultdict(list)
            for r in recs: by_chunk[r.chunk.chunk_id].append(r)
            self._record_index=(recs,by_chunk)
        return self._record_index

    def label_records(self, workers=2, progress=print):
        """Label the sentiment of every record in the domain's opinion record types, once, with the
        extract model; cached as record_labels.json in the index directory. Returns {key: label}."""
        from ..record_labels import label_records
        recs,_=self._records()
        todo=[r for r in recs if r.doc_type in set(self.domain.opinion_record_types)]
        view=_role(self.llm,"extract")
        path=Path(getattr(self,"index_dir",None) or self.config.index_dir)/"record_labels.json"
        labels=label_records(todo,view.json,getattr(view,"model",None) or str(self.llm.model),path,workers,progress)
        self._record_index=None; self._full_catalogue=None   # reload with the labels applied
        return labels

    def _field_estimate(self, question, plan, scopes):
        """Answer a record-log question from parsed record fields, exactly. Returns
        (estimate, evidence records, [(scope, chunk)]) or None when the fields can't express it.

        An LLM maps the question to a small query over the field catalogue (filters, operation,
        target, grouping); entity and period scopes are applied by the planner as usual. Code
        runs the query over every record in scope.
        """
        from ..records import catalogue, run_query
        recs,by_chunk=self._records()
        if not recs: return None
        record_chunks=[c for c in self.index.chunks if c.chunk_id in by_chunk]
        scoped=[]  # [(scope, [records])]
        for sc in scopes:
            keep=scope_filter(plan,sc,self.domain)
            scoped.append((sc,[r for c in record_chunks if keep(c) for r in by_chunk[c.chunk_id]]))
        in_scope={id(r):r for _,rs in scoped for r in rs}
        if not in_scope: return None
        if getattr(self,"_full_catalogue",None) is None:
            self._full_catalogue=catalogue(recs)  # field kinds judged over all records, not one scope
        cat={t:v for t,v in catalogue(list(in_scope.values())).items() if not plan.doc_types or t in plan.doc_types}
        for t,v in cat.items():
            whole=self._full_catalogue.get(t,{}).get("fields",{})
            v["fields"]={k:i for k,i in v["fields"].items() if k in whole}
        # Entities and periods are applied by the scopes; hiding their fields keeps the model from
        # filtering on them a second time (with date strings that never match).
        entity_names={str(e.get("name","")).lower() for items in self.inventory.get("entities",{}).values() for e in items}
        for v in cat.values():
            v["fields"]={k:i for k,i in v["fields"].items() if i["type"]!="date"
                         and not (i.get("values") and sum(str(x).lower() in entity_names for x in i["values"])>=len(i["values"])/2)}
        allowed={k for v in cat.values() for k in v["fields"]}
        entity_words={w for n in entity_names for w in re.findall(r"[a-z]{4,}",n)}
        system=("Map the question to a query over structured record fields, or say it cannot be answered from them. "
                "The records are already restricted to the question's entities and periods; do not filter on those again "
                "unless a field is the only way to express them. Return JSON {answerable, operation, filters, target, "
                "condition, minus_condition, k, group_by}. operation: count | sum | mean | share | net_share | mode | top_k | "
                "rank_groups | max_group | min_group. filters, condition and minus_condition: lists of {field, op, value} with op eq | ne | contains | in | gte | gt | "
                "lte | lt; use field values exactly as listed. target: the field to average, sum or take the most common "
                "value of. share = fraction of the filtered records that meet condition. mode = most common value of target; "
                "top_k = the k most common. rank_groups / max_group / min_group rank groups by their number of records. "
                "group_by: none (one answer over all records) | period (one answer per period: use it to compare periods "
                "or to find the month/quarter with the most) | entity (one per country/office scope) | a field name. "
                "answerable is false when the needed information is not a field, e.g. sentiment or tone of free text. "
                "To rank or compare countries/offices by how many records they have, use operation rank_groups (or max_group) "
                "with group_by entity. To rank groups by a share, give condition; by a net score (share meeting condition minus "
                "share meeting minus_condition, e.g. promoters minus detractors), give condition and minus_condition. "
                "operation net_share = that net score for one answer. Add a filter only for a condition the question states in words; never filter on a field just because it "
                "exists. Example: 'How many leave tickets were raised?' -> {answerable:true, operation:count, filters:"
                "[{field:title, op:eq, value:<the leave category as listed>}], group_by:none}. Example: 'Which category was "
                "most common?' -> {answerable:true, operation:mode, target:title, filters:[], group_by:none}.")
        user=json.dumps({"question":question,"periods_in_question":[str(p) for p in plan.periods],
                         "fields":cat},ensure_ascii=False,default=str)
        try:
            q=_role(self.llm,"answer").json(system,user)  # one call; the strong model maps far more reliably
        except Exception:
            return None
        if not isinstance(q,dict) or q.get("answerable") in (False,"false","no",None): return None
        values_of={k:i.get("values") or [] for v in cat.values() for k,i in v["fields"].items()}
        ql=question.lower()
        numeric={k for v in cat.values() for k,i in v["fields"].items() if i["type"]=="number"}
        def num_in_question(v):
            t=str(v).strip(); t=t.rstrip('0').rstrip('.') if re.fullmatch(r"-?\d+\.\d+",t) else t
            return bool(re.fullmatch(r"-?\d+(\.\d+)?",t)) and bool(re.search(rf"(?<![\d.]){re.escape(t)}(?![\d]|\.\d)",ql))
        def grounded(f):
            """A filter must come from the question: its words or number appear there."""
            if not (isinstance(f,dict) and f.get("field") in allowed and "value" in f): return False
            vals=f["value"] if isinstance(f["value"],list) else [f["value"]]
            if f.get("op") in ("gte","gt","lte","lt") or f["field"] in numeric:
                # a number the question states ('CSAT 3', 'at least 8'): any comparison, equality included
                return all(num_in_question(v) for v in vals)
            options=values_of.get(f["field"]) or []
            # a word most of the field's values share ('helpdesk' in every 'X (HR Helpdesk, India)') identifies nothing
            common={w for w,n in Counter(w for o in options for w in set(re.findall(r"[a-z]{4,}",o.lower()))).items()
                    if len(options)>=3 and n>len(options)/2}
            snapped=[]
            for v in vals:
                if any(re.search(rf"\b{re.escape(n)}\b",str(v).lower()) for n in entity_names if len(n)>=4):
                    return False   # the value names an entity: the scopes already apply it
                opt=next((o for o in options if o.lower()==str(v).strip().lower()),None)
                field_words=[w for w in re.findall(r"[a-z]{4,}",f["field"].replace("_"," ")) if w not in ("field","value")]
                if opt and (re.search(rf"\b{re.escape(opt.lower())}\b",ql) or
                            (len(opt)<=5 and any(w[:5] in ql for w in field_words))):
                    snapped.append(opt); continue   # a listed value the question states ('upheld'), or a yes/no on a field it names ('rejoin')
                words=[w for w in re.findall(r"[a-z]{4,}",str(v).lower()) if w not in entity_words and w not in common]
                # most of the value's words must be in the question (one shared word such as 'helpdesk' is not enough)
                if not words or sum(w[:5] in ql for w in words)<max(1,(len(words)+1)//2): return False
                best=max(options,key=lambda o:len(set(re.findall(r"[a-z]{4,}",o.lower()))&set(words)),default=None)
                fits=best if best and set(re.findall(r"[a-z]{4,}",best.lower()))&set(words) else None
                if fits is None and options and (f.get("op") in ("eq","in",None) or
                        (f.get("op")=="contains" and not any(str(v).lower() in o.lower() for o in options))):
                    return False   # matches no listed value
                snapped.append(fits or v)
            f["value"]=snapped if isinstance(f["value"],list) else snapped[0]
            if f.get("op")=="contains" and f["value"] in (values_of.get(f["field"]) or []): f["op"]="eq"
            return True
        def stated(f):
            """A rejected numeric condition the question states ('a CSAT of 3', read as CSAT 4): the
            condition is real but its value is wrong, and dropping it would answer a broader question,
            so the record path gives up instead. Rejected word values are dropped: they are mostly
            invented or put on the wrong field ('work_mode contains policy')."""
            if not isinstance(f,dict) or "value" not in f or f.get("field") not in numeric: return False
            vals=f["value"] if isinstance(f["value"],list) else [f["value"]]
            if any(num_in_question(v) for v in vals): return True
            field_words=[w for w in re.findall(r"[a-z]{3,}",str(f["field"]).replace("_"," ").lower()) if w not in ("field","value")]
            if not field_words: return False
            near=rf"\b{re.escape(field_words[0])}\w*(\W+[a-z]+){{0,3}}?\W+(?!(19|20)\d\d\b)\d+(\.\d+)?\b(?!\s*(january|february|march|april|may|june|july|august|september|october|november|december))"
            return bool(re.search(near,ql))
        def as_ranges(fl):
            """'likelihood in 9,10' on a numeric field: the range gte 9, lte 10 (a run of whole numbers)."""
            out=[]
            for f in fl or []:
                if isinstance(f,dict) and f.get("field") in numeric and f.get("op") in ("in","eq"):
                    raw=f.get("value"); raw=raw if isinstance(raw,list) else re.split(r"[,\s]+",str(raw))
                    try: nums=sorted({float(x) for x in raw if str(x).strip()!=""})
                    except ValueError: nums=[]
                    if len(nums)>1 and all(b-a==1 for a,b in zip(nums,nums[1:])):
                        lo,hi=(int(x) if x.is_integer() else x for x in (nums[0],nums[-1]))
                        out+=[{"field":f["field"],"op":"gte","value":lo},{"field":f["field"],"op":"lte","value":hi}]
                        continue
                out.append(f)
            return out
        essential_dropped=[]
        def clean(fl):
            kept=[]
            for f in as_ranges(fl):
                if grounded(f): kept.append(f)
                elif stated(f): essential_dropped.append(f)
            return kept
        q["filters"]=clean(q.get("filters")); q["condition"]=clean(q.get("condition")); q["minus_condition"]=clean(q.get("minus_condition"))
        if essential_dropped: return None   # cannot express a stated condition: another path answers
        cond_keys={json.dumps(f,sort_keys=True,default=str) for f in q["condition"]+q["minus_condition"]}
        q["filters"]=[f for f in q["filters"] if json.dumps(f,sort_keys=True,default=str) not in cond_keys]   # a condition repeated as a filter
        if q["minus_condition"] and not q["condition"]:
            # 'promoters minus detractors' with the promoter range put in filters: those filters are the condition
            minus_fields={f["field"] for f in q["minus_condition"]}
            q["condition"]=[f for f in q["filters"] if f["field"] in minus_fields]
            q["filters"]=[f for f in q["filters"] if f["field"] not in minus_fields]
        if q.get("operation")=="share" and not q["condition"] and q["filters"]:
            # 'what share of grievances were upheld' with the condition put in filters: the filters are the condition
            q["condition"],q["filters"]=q["filters"],[]
        if q.get("operation") in ("share","net_share") and not q["condition"]: return None
        if q.get("target") and q["target"] not in allowed: q["target"]=None
        if q.get("operation")=="sum" and not q.get("target"): q["operation"]="count"   # 'the number of grievances
        if q.get("operation") in ("rank_groups","max_group","min_group"):
            # ranking groups by a field's mean needs the question to name that field; 'the most tickets' is a count
            if q.get("target") and not any(w[:5] in ql for w in re.findall(r"[a-z]{3,}",q["target"].replace("_"," "))):
                q["target"]=None
            if q.get("condition") and not q.get("minus_condition") and not re.search(r"\b(share|proportion|percent\w*|fraction|rate|ratio)\b",ql):
                q["condition"]=[]
        if q.get("operation") in ("mean","sum","mode","top_k") and not q.get("target"): return None
        group_by=str(q.get("group_by") or "none").lower()
        nouns="|".join(re.escape(n.lower()) for n in self.domain.entity_nouns)
        if nouns and len(scoped)>1 and re.search(rf"\bwhich (\w+ )?({nouns})\b",ql) and \
                q.get("operation") in ("mode","top_k","rank_groups","max_group","min_group"):
            # 'which three countries raised the most tickets': the answer is entities, so the groups are the entity scopes
            if q["operation"] in ("mode","top_k"):
                q["operation"]="max_group" if q["operation"]=="mode" or q.get("k")==1 else "rank_groups"
                q["target"]=None
            group_by="entity"
        if q.get("operation") in ("mode","top_k") and group_by==str(q.get("target") or "").lower():
            group_by="none"   # 'the three most common categories': one ranking, not one group per category
        if group_by in {t.name.lower() for t in self.domain.entity_types}: group_by="entity"
        elif group_by in ("month","quarter","year","week","date","time"): group_by="period"
        if group_by=="period" and q.get("operation") in ("count","sum","mean","share","net_share") and \
                (re.search(r"\b(combined|in total|altogether|overall)\b",ql) or not
                 re.search(r"\b(each|per|compare|compared|change|changed|vs|versus|differ|from .+ to)\b",ql)):
            group_by="none"   # one figure over the whole span ('between Q4 2024 and Q3 2026', 'Q4 and Q1 combined')
        if group_by in ("none","") and len(plan.periods)>1 and \
                re.search(r"\b(change|changed|before|after|compare|compared|vs|versus|from .+ to)\b",ql):
            group_by="period"   # 'how did the share change after 1 April': one figure per period
        groups=defaultdict(list); order=[]
        def add(key,r):
            if key not in groups: order.append(key)
            groups[key].append(r)
        if group_by=="period" and len(plan.periods)>1:
            for sc,rs in scoped:                    # the question's own periods, in question order
                for r in rs: add(_period_label(sc.period),r)
        elif group_by=="period":
            for r in sorted(in_scope.values(),key=lambda r:str(r.chunk.period)): add(_period_label(r.chunk.period),r)
        elif group_by=="entity":
            for sc,rs in scoped:
                for r in rs: add(_entity_label(sc,self.inventory),r)
        elif group_by not in ("none","") and any(group_by in v["fields"] for v in cat.values()):
            for r in in_scope.values(): add(r.get(group_by) or "unknown",r)
        else:
            for r in in_scope.values(): add("all",r)
        groups={k:list({id(r):r for r in v}.values()) for k,v in groups.items()}
        try:
            est=run_query(groups,q)
        except Exception:
            return None
        if not est or not est.get("groups"): return None
        est.update({"kind":"fields","records_in_scope":len(in_scope),"sampled_records":len(in_scope),"label_passes":0,
                    "exact":True,"method":"all records in scope, read from their fields","field_query":q,"order":order})
        if len(order)>1 and "groups" in est and set(order)<=set(est["groups"]):
            est["groups"]={k:est["groups"][k] for k in order}
        records=[{"entity":k,"attribute":"record count","value":len(v),"evidence_span":v[0].rid,"doc_id":v[0].doc_id,
                  "scope":k,"period":v[0].chunk.period,"version":None,"status":v[0].chunk.status} for k,v in groups.items() if v]
        chunks={r.chunk.chunk_id:r.chunk for r in in_scope.values()}
        sampled=[("records",c) for c in list(chunks.values())[:20]]  # a few for citation; all were read
        return est,records,sampled

    def _classify_sentiment(self, batch):
        """Per-record P(negative) from the sentiment classifier (Table 3.1's RoBERTa option).

        Scope filters already restrict the batch to the records the question is about.
        """
        probs=self.sentiment.negative_probs([c.text for c in batch])
        return [{"applies":True,"value":round(p,4),"evidence_span":c.text[:120]} for c,p in zip(batch,probs)]

    def _label(self, question, kind, scope_label, batch, run):
        what={"flag":"value is true or false: whether the record meets the question's condition",
              "number":"value is the number the question asks about for this record (a JSON number), or null",
              "category":"value is a short category label for this record as the question asks (e.g. its ticket category or main topic)",
              "sentiment":"value is the record's sentiment: positive, negative, neutral or mixed"}[kind]
        system=("Label each record for the question. Return JSON {records:[{index, applies, value, evidence_span}]}: applies is "
                "true if the record is one the question is about (right type, entity and period); "+what+
                "; evidence_span is copied verbatim from the record. Judge each record independently.")
        user=json.dumps({"question":question,"scope":scope_label,"records":[{"index":i,"period":c.period,"text":c.text}
                                                                            for i,c in enumerate(batch)]},ensure_ascii=False)
        try:
            out=_role(self.llm,"extract").json(system,user,temperature=1.0 if run else 0)
        except TypeError:
            out=_role(self.llm,"extract").json(system,user)
        got={r.get("index"):r for r in (out or {}).get("records",[]) if isinstance(r,dict)}
        return [got.get(i,{}) for i in range(len(batch))]

    def _summarise_estimate(self, plan, kind, per_scope, scopes):
        """Combine labelled rows into per-group estimates (weighted by population) in code."""
        period_of={s.label:s.period for s in scopes}
        groups=defaultdict(dict)
        for label,info in per_scope.items():
            key=str(period_of.get(label)) if len(plan.periods)>1 else "all"
            groups[key][label]=info
        def values(info):
            out=[]
            for it,vals in info["rows"]:
                if kind=="number":
                    nums=[float(v) for v in vals if isinstance(v,(int,float)) and not isinstance(v,bool)]
                    if nums: out.append(sum(nums)/len(nums))
                elif kind=="flag":
                    # Soft label: the share of passes that said the record meets the condition.
                    out.append(sum(_is_yes(v) for v in vals)/len(vals) if vals else None)
                elif kind=="sentiment":
                    # LLM labels are words ("negative"); classifier labels are P(negative).
                    out.append(sum(float(v) if isinstance(v,(int,float)) and not isinstance(v,bool)
                                   else float(str(v).lower()=="negative") for v in vals)/len(vals) if vals else None)
            return out
        result={"groups":{}}
        for key,scopes_in in groups.items():
            if kind=="category":
                # Each record's category is the majority label across passes.
                cats=[majority_category([[normalize_label(v)] for v in vals if v])[0][0] if any(vals) else None
                      for info in scopes_in.values() for _,vals in info["rows"]]
                result["groups"][key]=category_shares(cats,population=sum(i["population"] for i in scopes_in.values()))
                if plan.k: result["groups"][key]["categories"]=result["groups"][key]["categories"][:max(plan.k,1)]
            elif plan.operation=="count":
                applicable=sum(i["population"] for i in scopes_in.values())
                sampled_share={l:([1.0]*len(i["rows"])+[0.0]*(i["sampled"]-len(i["rows"])),i["records_in_scope"])
                               for l,i in scopes_in.items()}
                share=stratified_estimate(sampled_share,seed=self.config.seed)
                total=sum(i["records_in_scope"] for i in scopes_in.values())
                result["groups"][key]={"estimate":applicable,"ci_low":share["ci_low"]*total if share["ci_low"] is not None else None,
                                       "ci_high":share["ci_high"]*total if share["ci_high"] is not None else None,
                                       "n":share["n"],"population":total,"what":"number of matching records"}
            else:
                result["groups"][key]=stratified_estimate({l:(values(i),i["population"]) for l,i in scopes_in.items()},
                                                          seed=self.config.seed)
                result["groups"][key]["what"]={"number":"mean value","flag":"share meeting the condition",
                                               "sentiment":"share negative"}[kind]
        if len(groups)==2 and kind!="category":
            (ka,a),(kb,b)=sorted(groups.items())
            result["difference"]=stratified_difference({l:(values(i),i["population"]) for l,i in a.items()},
                                                       {l:(values(i),i["population"]) for l,i in b.items()},seed=self.config.seed)
            result["difference"]["between"]=[ka,kb]
        return result

    # --- step 9 helpers -------------------------------------------------------------------
    def _generate_local(self,q,hits):
        evidence=[{"doc_id":c.doc_id,"path":c.path,"version":c.version,"status":c.status,"effective_date":c.effective_date,"text":c.text} for c,*_ in hits]
        return _role(self.llm,"answer").text("Answer only from supplied evidence. Cite every material claim using [doc_id]. If evidence is insufficient, say so. "
                             "Prefer current/in-force documents; mention superseded or announced values when they differ.",json.dumps({"question":q,"evidence":evidence}))

    def _write(self,q,plan,mode,records,aggregate,estimate,synthesis,flags):
        return _role(self.llm,"answer").text("Write the answer from the computed results only; they are authoritative. Label every statement: "
                             "[exact] for results computed from all the evidence, [estimated] for sampled estimates (always give the "
                             "95% interval and the sample size), [generated] for insights (give their support, e.g. 4/5 runs, and "
                             "call 'hypothesis' insights tentative). Use only numbers present in the results; never compute new ones. "
                             "Cite document IDs. State missing coverage, version differences and conflicts.",
                             json.dumps({"question":q,"query_type":plan.qtype,"operation":plan.operation,"computation_mode":mode,
                                         "deterministic_result":aggregate,"estimate":estimate,"insights":synthesis,
                                         "records":records[:200],"version_and_conflict_flags":flags},default=str))

    # --- step 8: verification ---------------------------------------------------------------
    def _verify(self,q,plan,scopes,answer,records,flags,estimate=None,synthesis=None):
        # every record in scope read from its fields, or one row per document: coverage is not partial
        whole=(estimate or {}).get("kind")=="fields" or any(r.get("scope")=="catalogue" for r in records)
        expected=[s.label for s in scopes] if plan.qtype!="local" and not whole else []
        coverage=completeness_report([{"entity":r.get("scope")} for r in records],expected)
        conflicts=find_conflicts(records) if plan.operation!="map_reduce" and not estimate else []
        judge=_role(self.llm,"verify").json("Check whether each answer claim is supported by supplied evidence spans and doc IDs. Return JSON {supported:boolean, unsupported_claims:[], notes:string}. Be conservative.",json.dumps({"question":q,"answer":answer,"records":records[:200]},default=str)) if self.config.llm_verify else {"skipped":"llm_verify off: NLI and number provenance only"}
        nli=None
        if self.nli:  # Table 3.1: NLI model alongside the LLM judge
            evidence=[r.get("evidence_span") for r in records if r.get("evidence_span")]+list(getattr(self,"_evidence_text",[]))
            nli=self.nli.verify(answer,evidence)
        return {"coverage":coverage,"conflicts":conflicts,"version_resolution":flags,"claim_support":judge,"nli":nli,
                "uncertainty":uncertainty_report(estimate,synthesis)}

    def _number_check(self,q,answer,records,aggregate,estimate,synthesis,evidence_text,doc_ids):
        """Numbers in the final answer that no code result, record or evidence passage contains."""
        allowed=(numbers_in(q)+numbers_in([r.get("value") for r in records])+numbers_in([r.get("evidence_span") for r in records])
                 +numbers_in(aggregate)+numbers_in(estimate)+numbers_in(synthesis)+numbers_in(evidence_text))
        text=str(answer)
        for d in sorted(set(doc_ids)|{r.get("doc_id") for r in records if r.get("doc_id")},key=len,reverse=True):
            text=text.replace(d,"")
        text=re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b|\b(19|20)\d{2}-?Q[1-4]\b","",text)  # dates and period labels
        unsupported=number_provenance(text,allowed)
        return {"unsupported_numbers":unsupported,"ok":not unsupported}

    def _finalize(self,q,answer,records,verification):
        return _role(self.llm,"answer").text("Produce the final answer with concise citations [doc_id]. Keep each statement's [exact], [estimated] or "
                             "[generated] label and its interval or support. Explicitly disclose incomplete coverage, conflicts, "
                             "superseded or pending values, or unsupported claims from verification. Do not hide uncertainty and "
                             "do not add numbers that are not in the draft.",
                             json.dumps({"question":q,"draft_answer":answer,"evidence_records":records,"verification":verification},default=str))


def disclosures(verification):
    """What a templated answer must state from verification: missing coverage, conflicts,
    superseded or pending values, unsupported claims and unstated uncertainty. '' when none."""
    v=verification or {}; out=[]
    cov=v.get("coverage") or {}
    if cov.get("expected_count") and not cov.get("complete", True):
        miss=cov.get("missing_entities") or []
        out.append(f"Incomplete coverage: no evidence for {len(miss)} of {cov['expected_count']} scopes"
                   +(f" ({', '.join(map(str,miss[:8]))}{', ...' if len(miss)>8 else ''})" if miss else "")+".")
    def key(f):
        k=f.get("key"); return ", ".join(f"{x}" for x in k.values() if x) if isinstance(k,dict) else str(k or "")
    for f in v.get("conflicts") or []:
        if f.get("kind")=="conflict":
            out.append(f"Conflict: {key(f)} is stated as {' / '.join(map(str,f.get('values') or []))}"
                       +f" in {', '.join(sorted({str(x.get('doc_id')) for x in f.get('sources') or [] if x.get('doc_id')}))}.")
    for f in v.get("version_resolution") or []:
        kind=str(f.get("kind") or "")
        if not kind: continue
        chosen=(f.get("chosen") or {}); other=(f.get("other") or {})
        detail=f" (used {chosen.get('value')} [{chosen.get('doc_id')}]" if chosen else ""
        detail+=(f"; other value {other.get('value')} [{other.get('doc_id')}]" if other else "")+(")" if chosen else "")
        out.append(f"{kind.replace('_',' ').capitalize()}: {key(f)}{detail}.")
    cs=v.get("claim_support") or {}
    if isinstance(cs,dict) and (cs.get("supported") is False or cs.get("unsupported_claims")):
        claims=[str(c) for c in cs.get("unsupported_claims") or []]
        out.append("Not supported by the evidence: "+("; ".join(claims[:5]) if claims else "the verifier rejected the answer")+".")
    for p in (v.get("uncertainty") or {}).get("problems") or []:
        out.append(f"Uncertainty not stated: {p}.")
    out=list(dict.fromkeys(out))
    return ("Verification notes:\n"+"\n".join("- "+o for o in out)) if out else ""


def _is_yes(v):
    return v is True or str(v).strip().lower() in ("true","yes","y","1")


def uncertainty_report(estimate, synthesis):
    """Step 8 check 4: estimates state their uncertainty; generated insights carry support and citations."""
    out={"ok":True,"problems":[]}
    if estimate:
        for key,g in (estimate.get("groups") or {}).items():
            if "categories" in g:
                if not g.get("n"): out["problems"].append(f"group {key}: no labelled records")
            elif g.get("estimate") is None:
                out["problems"].append(f"group {key}: no estimate")
            elif not estimate.get("exact") and (g.get("ci_low") is None or g.get("n") in (None,0)):
                out["problems"].append(f"group {key}: estimate without interval or sample size")
    if synthesis:
        hyp=[i["key"] for i in synthesis.get("insights",[]) if i["status"]=="hypothesis"]
        nums=[i["key"] for i in synthesis.get("insights",[]) if i["unverified_numbers"]]
        if hyp: out["problems"].append(f"insights without citations (hypotheses): {hyp}")
        if nums: out["problems"].append(f"insights with numbers not computed by code: {nums}")
        out["insights_kept"]=len(synthesis.get("insights",[])); out["insights_dropped"]=len(synthesis.get("dropped",[]))
    out["ok"]=not out["problems"]
    return out


def _unique_records(hits):
    """Evidence records from all scope hits, without repeats.

    A shared chunk is judged once per scope, so the same fact can be extracted twice;
    counting it twice would skew means and shares.
    """
    out,seen=[],set()
    for *_,payload in hits:
        for r in (payload or {}).get("records",[]):
            key=(str(r.get("entity")),str(r.get("attribute")),str(r.get("value")),r.get("doc_id"),r.get("evidence_span"))
            if key not in seen:
                seen.add(key); out.append(r)
    return out


def build_entity_inventory(docs):
    """HR country entities with document counts (kept for callers of the earlier API)."""
    return [{"name":c["name"],"country_code":c["value"],"document_count":c["document_count"],"doc_types":c["doc_types"]}
            for c in build_inventory(docs,load_domain("hr"))["entities"]["country"]]



_MONTH_NAMES=["January","February","March","April","May","June","July","August","September","October","November","December"]


def _period_label(period):
    """'2026-04' -> 'April 2026', '2026-Q2' -> 'Q2 2026'; a (start, end) month-index range is labelled by its months."""
    if isinstance(period,(tuple,list)) and len(period)==2 and all(isinstance(x,int) for x in period):
        a,b=period
        name=lambda m:f"{_MONTH_NAMES[m%12]} {m//12}"
        return name(a) if a==b else f"{name(a)} – {name(b)}"
    p=str(period)
    m=re.match(r"^(\d{4})-(\d{2})$",p)
    if m: return f"{_MONTH_NAMES[int(m.group(2))-1]} {m.group(1)}"
    m=re.match(r"^(\d{4})-Q([1-4])$",p)
    if m: return f"Q{m.group(2)} {m.group(1)}"
    return p


def _entity_label(scope,inventory):
    for items in inventory.get("entities",{}).values():
        for e in items:
            if e.get("value")==scope.entity_value: return e.get("name") or scope.entity_value
    return scope.entity_value or scope.label
