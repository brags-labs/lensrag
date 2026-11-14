from __future__ import annotations
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
from ..planning import QUERY_TYPES, plan_query, build_scopes, build_inventory, scope_filter
from ..synthesis import consistent_insights
from ..retrieval import coverage_retrieve
from .index import DenseEncoder, PersistentHybridIndex, corpus_fingerprint
from .providers import create_llm

@dataclass
class PipelineConfig:
    tier: str = "L"
    domain: str = "hr"              # built-in domain name or path to a domain .yaml/.json
    corpus_dir: str | None = None   # a folder of .md/.txt files; None = the BragsLabs zip corpus
    index_dir: str = "artifacts/index_L"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_model: str | None = None     # None = the provider's default (claude-opus-5-5 / gpt-4o-mini)
    llm_provider: str | None = None  # anthropic | openai | auto (see full/providers.py)
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

class LensRAGPipeline:
    """End-to-end LensRAG (steps 3-9): plan, decompose, cover, filter+extract, compute, verify, answer."""
    def __init__(self, index, inventory, llm, config):
        self.index,self.inventory,self.llm,self.config=index,inventory,llm,config
        self.domain=load_domain(inventory.get("domain_source") or inventory.get("domain") or config.domain)

    @classmethod
    def build(cls, corpus_zip, extract_dir, config=None, use_llm=True):
        cfg=config or PipelineConfig(); domain=load_domain(cfg.domain)
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
        llm=create_llm(cfg.llm_provider,cfg.llm_model) if use_llm else None
        Path(cfg.index_dir).joinpath("entities.json").write_text(json.dumps(inventory,indent=2),encoding="utf-8")
        return cls(idx,inventory,llm,cfg)

    @classmethod
    def load(cls, index_dir, config=None, use_llm=True):
        cfg=config or PipelineConfig(index_dir=str(index_dir)); idx,meta=PersistentHybridIndex.load(index_dir)
        ep=Path(index_dir)/"entities.json"
        inventory=json.loads(ep.read_text()) if ep.exists() else None
        if not isinstance(inventory,dict) or "entities" not in inventory:  # missing or an older format
            inventory=build_inventory(idx.chunks,load_domain(cfg.domain))
        llm=create_llm(cfg.llm_provider,cfg.llm_model) if use_llm else None
        return cls(idx,inventory,llm,cfg)

    def ask(self, question: str):
        if not self.llm: raise RuntimeError("Query answering requires an LLM: set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY and load with use_llm=True.")
        t0=time.perf_counter()
        plan=self._plan(question)                                    # step 3
        scopes=build_scopes(plan,self.inventory,self.domain)         # step 4
        aggregate=None; flags=[]; estimate=None; synthesis=None; hits=[]; telemetry={}; rejected=[]
        if plan.doc_types and plan.mode in ("estimated","generated"):
            # Step 7, Mode B: record logs are sampled and labelled, then estimated in code (exact when small).
            estimate,records,sampled=self._estimate(question,plan,scopes)
            hits=[(c,0.0,lab,None) for lab,c in sampled]
            telemetry={"mode":"sampled" if not estimate.get("exact") else "all records","scopes":len(scopes)}
            if plan.mode=="generated":                               # Mode C on top of the estimates
                synthesis=self._synthesise(question,plan,records,{"estimate":estimate},[c.doc_id for _,c in sampled])
        else:
            mapping=plan.operation=="map_reduce"
            hits,telemetry=coverage_retrieve(self.index,plan,scopes,  # step 5: loop until no new relevant evidence
                                             judge=self._llm_judge(question,extract=not mapping),
                                             page=self.config.page_size,max_rounds=self.config.adaptive_round_limit)
            rejected=[x for *_,payload in hits for x in (payload or {}).get("rejected",[])]
            if mapping:                                              # Mode C: map, count in code, consistent reduce
                records,aggregate=self._map(question,hits,plan)
                synthesis=self._synthesise(question,plan,records,aggregate,[c.doc_id for c,*_ in hits])
            else:
                records,bad=validate_evidence_records(_unique_records(hits))  # step 6
                rejected.extend(bad)
                if plan.qtype!="local":                              # Mode A: deterministic code
                    aggregate,flags=self._compute(plan,records)
        mode=plan.mode if not (estimate and estimate.get("exact") and plan.mode=="estimated") else "exact"
        if plan.qtype=="local" and not plan.doc_types:
            answer=self._generate_local(question,hits)
        else:
            answer=self._write(question,plan,mode,records,aggregate,estimate,synthesis,flags)
        verification=self._verify(question,plan,scopes,answer,records,flags,estimate,synthesis)   # step 8
        answer=self._finalize(question,answer,records,verification)            # step 9
        evidence_text=[c.text for c,*_ in hits]
        verification["number_provenance"]=self._number_check(question,answer,records,aggregate,estimate,synthesis,
                                                             evidence_text,[c.doc_id for c,*_ in hits])
        return {"query_type":plan.qtype,"computation_mode":mode,"plan":plan.to_dict(),"answer":answer,
                "deterministic_result":aggregate,"estimate":estimate,"insights":synthesis,
                "retrieved_chunks":[{"chunk_id":c.chunk_id,"doc_id":c.doc_id,"scope":lab,"score":sc} for c,sc,lab,_ in hits],
                "evidence_records":records,"verification":verification,"rejected_evidence":rejected,
                "adaptive_retrieval":telemetry,"latency_ms":round((time.perf_counter()-t0)*1000,2)}

    # --- step 3: understand the question ------------------------------------------------
    def _plan(self, question):
        """LLM classification and parameters; the rule-based planner fills or replaces invalid fields."""
        entities=self.inventory.get("entities",{})
        by_name={t:{e["name"]:e["value"] for e in items} for t,items in entities.items()}
        out=self.llm.json(
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
        overrides={"qtype":out.get("qtype"),"direction":out.get("direction") if out.get("direction") in ("asc","desc") else None,
                   "k":out.get("k") if isinstance(out.get("k"),int) and out.get("k")>0 else None,
                   "threshold":out.get("threshold") if isinstance(out.get("threshold"),(int,float)) else None,
                   "comparator":out.get("comparator") if out.get("comparator") in ("gte","gt","lte","lt","eq") else None,
                   "named":{t:v for t,v in named.items() if v},"excluded":{t:v for t,v in excluded.items() if v},
                   "versions":[str(v) for v in out.get("versions") or [] if str(v) in self.inventory.get("versions",[])]}
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
            out=self.llm.json(task,json.dumps({"question":question,"scope":scope.label,"passages":passages}))
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

    def _map(self, question, hits, plan):
        """Mode C, map: one call per entity scope labels each passage; code counts the labels."""
        by_scope=defaultdict(list)
        for c,_,label,_ in hits: by_scope[label].append(c)
        mapped=[]
        for label,chunks in by_scope.items():
            out=self.llm.json("For each passage, list the query-relevant themes or categories as short labels, its sentiment "
                              "(positive|negative|neutral|mixed|null) and a verbatim evidence_span. Return JSON {items:[{index, labels:[], "
                              "sentiment, evidence_span}]}. Do not invent.",
                              json.dumps({"question":question,"scope":label,"passages":[{"index":i,"period":c.period,"passage":c.text} for i,c in enumerate(chunks)]}))
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
        return consistent_insights(self.llm,question,notes,stats,evidence_doc_ids,k=self.config.reduce_runs,
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
        labelled={}  # (scope, chunk_id) -> {"applies":[...], "values":[...], "span":str}
        for label,chunks in sample.items():
            for i in range(0,len(chunks),cfg.label_batch):
                batch=chunks[i:i+cfg.label_batch]
                for run in range(passes):
                    for c,lab in zip(batch,self._label(question,kind,label,batch,run)):
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
            out=self.llm.json(system,user,temperature=1.0 if run else 0)
        except TypeError:
            out=self.llm.json(system,user)
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
                    out.append(sum(str(v).lower()=="negative" for v in vals)/len(vals) if vals else None)
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
        return self.llm.text("Answer only from supplied evidence. Cite every material claim using [doc_id]. If evidence is insufficient, say so. "
                             "Prefer current/in-force documents; mention superseded or announced values when they differ.",json.dumps({"question":q,"evidence":evidence}))

    def _write(self,q,plan,mode,records,aggregate,estimate,synthesis,flags):
        return self.llm.text("Write the answer from the computed results only; they are authoritative. Label every statement: "
                             "[exact] for results computed from all the evidence, [estimated] for sampled estimates (always give the "
                             "95% interval and the sample size), [generated] for insights (give their support, e.g. 4/5 runs, and "
                             "call 'hypothesis' insights tentative). Use only numbers present in the results; never compute new ones. "
                             "Cite document IDs. State missing coverage, version differences and conflicts.",
                             json.dumps({"question":q,"query_type":plan.qtype,"operation":plan.operation,"computation_mode":mode,
                                         "deterministic_result":aggregate,"estimate":estimate,"insights":synthesis,
                                         "records":records[:200],"version_and_conflict_flags":flags},default=str))

    # --- step 8: verification ---------------------------------------------------------------
    def _verify(self,q,plan,scopes,answer,records,flags,estimate=None,synthesis=None):
        expected=[s.label for s in scopes] if plan.qtype!="local" else []
        coverage=completeness_report([{"entity":r.get("scope")} for r in records],expected)
        conflicts=find_conflicts(records) if plan.operation!="map_reduce" and not estimate else []
        judge=self.llm.json("Check whether each answer claim is supported by supplied evidence spans and doc IDs. Return JSON {supported:boolean, unsupported_claims:[], notes:string}. Be conservative.",json.dumps({"question":q,"answer":answer,"records":records[:200]},default=str))
        return {"coverage":coverage,"conflicts":conflicts,"version_resolution":flags,"claim_support":judge,
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
        return self.llm.text("Produce the final answer with concise citations [doc_id]. Keep each statement's [exact], [estimated] or "
                             "[generated] label and its interval or support. Explicitly disclose incomplete coverage, conflicts, "
                             "superseded or pending values, or unsupported claims from verification. Do not hide uncertainty and "
                             "do not add numbers that are not in the draft.",
                             json.dumps({"question":q,"draft_answer":answer,"evidence_records":records,"verification":verification},default=str))


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
