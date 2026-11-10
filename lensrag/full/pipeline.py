from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, re, time
from collections import defaultdict
from ..data import ensure_extracted, load_documents, chunk_document, read_manifest, COUNTRY_NAMES
from ..aggregation import validate_evidence_records, aggregate_records, completeness_report, find_conflicts, reduce_labels
from .index import DenseEncoder, PersistentHybridIndex, corpus_fingerprint
from .llm import LLMClient

@dataclass
class PipelineConfig:
    tier: str = "L"
    index_dir: str = "artifacts/index_L"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_model: str = "gpt-4o-mini"
    top_k: int = 12
    adaptive_round_limit: int = 4
    allow_lexical_fallback: bool = False
    use_reranker: bool = True

class LensRAGPipeline:
    def __init__(self, index, entities, llm, config):
        self.index,self.entities,self.llm,self.config=index,entities,llm,config

    @classmethod
    def build(cls, corpus_zip, extract_dir, config=None, use_llm=True):
        cfg=config or PipelineConfig(); corpus=ensure_extracted(Path(corpus_zip),Path(extract_dir))
        docs=load_documents(corpus,cfg.tier); chunks=[x for d in docs for x in chunk_document(d)]
        if not chunks: raise RuntimeError("No chunks found in selected tier")
        encoder=DenseEncoder(cfg.embedding_model)
        idx=PersistentHybridIndex(chunks,encoder=encoder)
        fp=corpus_fingerprint(chunks); idx.save(cfg.index_dir,fp)
        entities=build_entity_inventory(docs)
        llm=LLMClient(model=cfg.llm_model) if use_llm else None
        Path(cfg.index_dir).joinpath("entities.json").write_text(json.dumps(entities,indent=2),encoding="utf-8")
        return cls(idx,entities,llm,cfg)

    @classmethod
    def load(cls, index_dir, config=None, use_llm=True):
        cfg=config or PipelineConfig(index_dir=str(index_dir)); idx,meta=PersistentHybridIndex.load(index_dir)
        ep=Path(index_dir)/"entities.json"; entities=json.loads(ep.read_text()) if ep.exists() else []
        llm=LLMClient(model=cfg.llm_model) if use_llm else None
        return cls(idx,entities,llm,cfg)

    def ask(self, question: str):
        if not self.llm: raise RuntimeError("Query answering requires an LLM provider. Configure OPENAI_API_KEY and load with use_llm=True.")
        t0=time.perf_counter(); self._last_adaptive={}; qtype=self._route(question)
        if qtype=="local":
            hits=self.index.search(question,self.config.top_k,method="hybrid")
            hits=self._rerank(question,hits)
            records,rejected=self._extract_evidence(question,hits)
            draft=self._generate_local(question,hits)
            verification=self._verify(question,draft,records,[])
            answer=self._finalize(question,draft,records,verification)
            return self._result(qtype,answer,hits,records,time.perf_counter()-t0,verification,rejected)
        entities=self._select_entities(question)
        hits=self._adaptive_retrieve(question,entities)
        if qtype in {"theme","sentiment"}:
            answer,records=self._map_reduce(question,hits,qtype)
            rejected=[]
        else:
            records,rejected=self._extract_evidence(question,hits)
            operation={"count":"count","rank":"rank","filter":"filter","conflict":"conflict"}.get(qtype)
            threshold=None; comparator="gte"
            if operation=="filter":
                parsed=self.llm.json("Extract the numeric threshold and comparison direction from the question. Return JSON {threshold:number|null, comparator:gte|gt|lte|lt|null}. Do not invent a threshold.",q)
                threshold=parsed.get("threshold"); comparator=parsed.get("comparator") or "gte"
                if threshold is None: operation=None
            aggregate=aggregate_records(records,operation,top_k=self.config.top_k,threshold=threshold,comparator=comparator) if operation and operation!="conflict" else None
            answer=self._generate_aggregate(question,records,aggregate,qtype)
        verification=self._verify(question,answer,records,entities,qtype)
        answer=self._finalize(question,answer,records,verification)
        return self._result(qtype,answer,hits,records,time.perf_counter()-t0,verification,rejected)

    def _route(self,q):
        value=self.llm.json("Classify the HR corpus question. Return JSON {type: local|count|rank|filter|theme|sentiment|conflict}. Use local for a fact answer confined to one/few passages; global aggregation across entities is count/rank/filter/theme/sentiment/conflict.",q).get("type","local").lower()
        return value if value in {"local","count","rank","filter","theme","sentiment","conflict"} else "local"

    def _select_entities(self,q):
        prompt={"question":q,"available_entities":self.entities}
        out=self.llm.json("Select all entities whose documents must be covered to answer. Never invent entities. Return JSON {entities:[exact entity names]}. For corpus-wide queries select all relevant entities.",json.dumps(prompt))
        chosen=set(out.get("entities",[])); valid=[e for e in self.entities if e["name"] in chosen]
        return valid or self.entities

    def _adaptive_retrieve(self,q,entities):
        all_hits={}; known_entities={e["name"] for e in entities}; frontier=list(entities)
        rounds=0; converged=False
        for round_no in range(self.config.adaptive_round_limit):
            if not frontier:
                converged=True; break
            rounds+=1
            new=[]
            for ent in frontier:
                country=ent.get("country_code")
                query=f"{q} {ent['name']}"
                batch=self.index.search(query,self.config.top_k,countries=[country] if country else None,method="hybrid")
                for c,s in batch:
                    if c.chunk_id in all_hits: continue
                    all_hits[c.chunk_id]=(c,s)
                    # Entity expansion is bounded to the known ingestion-time entity list.
                    # Discover cross-references only once per newly found passage.
                    discovered=self.llm.json("From this passage, identify any explicitly mentioned entities that exactly match names in the supplied inventory. Return JSON {entities:[names]}. Do not infer or invent.",json.dumps({"inventory":[e["name"] for e in self.entities],"passage":c.text})).get("entities",[])
                    for mention in discovered:
                        if mention not in known_entities:
                            match=next((e for e in self.entities if e["name"]==mention),None)
                            if match: known_entities.add(mention); new.append(match)
            frontier=new
        if not frontier: converged=True
        self._last_adaptive={"rounds":rounds,"converged":converged,"entity_count":len(known_entities),"hit_count":len(all_hits)}
        return sorted(all_hits.values(),key=lambda x:x[1],reverse=True)

    def _rerank(self,q,hits):
        if not hits or not self.config.use_reranker: return hits
        # Optional cross-encoder reranker; fall back transparently to hybrid ranking.
        try:
            from sentence_transformers import CrossEncoder
            if not hasattr(self,"_reranker"): self._reranker=CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            pairs=[(q,c.enriched_text) for c,_ in hits]; scores=self._reranker.predict(pairs)
            return sorted([(c,float(s)) for (c,_),s in zip(hits,scores)],key=lambda x:x[1],reverse=True)
        except Exception: return hits

    def _extract_evidence(self,q,hits):
        records=[]; rejected=[]
        for chunk,score in hits:
            obj=self.llm.json("Extract only explicit evidence answering the query. Return JSON {relevant:boolean, records:[{entity,attribute,value,evidence_span,doc_id,version,effective_date,period}]}. Use a JSON number for numeric values and keep units in a separate attribute if needed. evidence_span must be a verbatim substring of passage. Do not infer missing facts.",json.dumps({"query":q,"doc_id":chunk.doc_id,"version":chunk.version,"effective_date":chunk.effective_date,"period":chunk.period,"passage":chunk.text}))
            if obj.get("relevant"):
                for r in obj.get("records",[]):
                    r.setdefault("doc_id",chunk.doc_id); r.setdefault("version",chunk.version); r.setdefault("effective_date",chunk.effective_date); r.setdefault("period",chunk.period)
                    if r.get("evidence_span") and r["evidence_span"] in chunk.text: records.append(r)
                    else: rejected.append({"doc_id":chunk.doc_id,"reason":"evidence span not verbatim"})
        valid,bad=validate_evidence_records(records); rejected.extend(bad)
        return valid,rejected

    def _map_reduce(self,q,hits,kind):
        mapped=[]
        for chunk,_ in hits:
            out=self.llm.json("Map one passage to query-relevant themes or sentiment. Return JSON {labels:[short labels], sentiment:positive|negative|neutral|mixed|null, period:string|null, evidence_span:string|null}. Do not invent.",json.dumps({"query":q,"passage":chunk.text,"period":chunk.period,"doc_id":chunk.doc_id}))
            span=out.get("evidence_span") or ""
            if (out.get("labels") or out.get("sentiment")) and span and span in chunk.text:
                entity=(chunk.entities[0] if chunk.entities else chunk.country)
                item={"labels":out.get("labels",[]),"sentiment":out.get("sentiment"),"period":out.get("period") or chunk.period,"doc_id":chunk.doc_id,"evidence_span":span,"entity":entity,"version":chunk.version}
                mapped.append(item)
        grouped=reduce_labels(mapped)
        summary=self.llm.text("You are summarising labelled evidence. Describe dominant themes/sentiment and period changes; state coverage limitations and do not claim statistical representativeness beyond retrieved passages.",json.dumps({"question":q,"groups":grouped,"mapped_evidence":mapped}))
        records=[]
        for item in mapped:
            values=item.get("labels",[]) if kind=="theme" else ([item["sentiment"]] if item.get("sentiment") else [])
            for value in values:
                records.append({"entity":item["entity"],"attribute":kind,"value":value,"evidence_span":item["evidence_span"],"doc_id":item["doc_id"],"version":item.get("version",""),"period":item.get("period","")})
        return summary,records

    def _generate_local(self,q,hits):
        evidence=[{"doc_id":c.doc_id,"path":c.path,"version":c.version,"effective_date":c.effective_date,"text":c.text} for c,_ in hits]
        return self.llm.text("Answer only from supplied evidence. Cite every material claim using [doc_id]. If evidence is insufficient, say so. Mention conflicting versions.",json.dumps({"question":q,"evidence":evidence}))

    def _generate_aggregate(self,q,records,aggregate,qtype):
        return self.llm.text("Answer from extracted evidence and deterministic result only. Cite document IDs. State missing coverage and conflicts; never invent totals.",json.dumps({"question":q,"query_type":qtype,"records":records,"deterministic_aggregate":aggregate}))

    def _verify(self,q,answer,records,entities,qtype=None):
        expected=[e["name"] for e in entities]
        complete=completeness_report(records,expected) if records else {"expected_count":len(expected),"present_count":0,"missing_entities":expected,"complete":False}
        conflicts=[] if qtype in {"theme","sentiment"} else find_conflicts(records)
        judge=self.llm.json("Check whether each answer claim is supported by supplied evidence spans and doc IDs. Return JSON {supported:boolean, unsupported_claims:[], notes:string}. Be conservative.",json.dumps({"question":q,"answer":answer,"records":records}))
        return {"coverage":complete,"conflicts":conflicts,"claim_support":judge}

    def _finalize(self,q,answer,records,verification):
        return self.llm.text("Produce the final answer with concise citations [doc_id]. Explicitly disclose incomplete coverage, conflicts, or unsupported claims from verification. Do not hide uncertainty.",json.dumps({"question":q,"draft_answer":answer,"evidence_records":records,"verification":verification}))

    def _result(self,qtype,answer,hits,records,elapsed,verification=None,rejected=None):
        return {"query_type":qtype,"answer":answer,"retrieved_chunks":[{"chunk_id":c.chunk_id,"doc_id":c.doc_id,"score":s} for c,s in hits],"evidence_records":records,"verification":verification or {},"rejected_evidence":rejected or [],"adaptive_retrieval":getattr(self,"_last_adaptive",{}),"latency_ms":round(elapsed*1000,2)}

def build_entity_inventory(docs):
    seen={}
    for d in docs:
        name=d.country
        if name and name not in {"ALL",""}:
            if name not in seen:
                seen[name]={"name":name,"country_code":name,"document_count":0,"doc_types":set()}
            seen[name]["document_count"]+=1; seen[name]["doc_types"].add(d.doc_type)
    # Map common codes to canonical country names for query-facing inventory.
    from ..data import COUNTRIES
    out=[]
    for code,v in seen.items():
        out.append({"name":("Global policies" if code=="GLOBAL" else COUNTRIES.get(code,code)),"country_code":code,"document_count":v["document_count"],"doc_types":sorted(v["doc_types"])})
    return out
