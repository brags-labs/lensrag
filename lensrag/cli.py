from __future__ import annotations
import argparse, zipfile, json
from pathlib import Path
from .data import ensure_extracted,read_manifest
from .experiment import run_experiment
from .reporting import build_report

def main():
    ap=argparse.ArgumentParser(prog="lensrag",description="LensRAG: benchmark runner and question answering over a document corpus")
    sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("inspect")
    run=sub.add_parser("run")
    run.add_argument("--tiers",nargs="+",default=["S","M","L"],choices=["S","M","L"])
    run.add_argument("--top-k",type=int,default=10)
    run.add_argument("--output",default="results")
    run.add_argument("--store",default="artifacts/chroma",help="ChromaDB directory for chunks/vectors; reused when the corpus is unchanged")
    run.add_argument("--no-store",action="store_true",help="Rebuild everything in memory; do not read or write ChromaDB")
    run.add_argument("--semantic",default="tfidf",choices=["tfidf","dense"],help="Second scorer fused with BM25")
    run.add_argument("--embedding-model",default="sentence-transformers/all-MiniLM-L6-v2")
    run.add_argument("--domain",default="hr",help="Domain config: built-in name (hr, legal) or path to a .yaml/.json file")
    run.add_argument("--rerank",action="store_true",help="Also run lensrag_rerank (cross-encoder reranking; needs sentence-transformers)")
    run.add_argument("--no-long-context",action="store_true",help="Skip the long-context baselines")
    run.add_argument("--judge-model",default="cross-encoder/ms-marco-MiniLM-L-6-v2",help="Cross-encoder used as the relevance judge (lensrag_rerank), e.g. BAAI/bge-reranker-v2-m3")
    run.add_argument("--judge-threshold",type=float,default=None,help="Minimum cross-encoder score for a chunk to count as relevant; default: the calibrated value for --judge-model (retrieval.JUDGE_THRESHOLDS)")
    hyp=sub.add_parser("hypotheses",help="Test H1-H3 from an experiment's metrics.csv (and answers.csv if present)")
    hyp.add_argument("--output",default="results")
    hyp.add_argument("--tex",default=None,help="Also write the results as a LaTeX document, e.g. docs/hypothesis_results.tex")
    ans=sub.add_parser("answers",help="Answer the gold questions with an LLM and score exact match / set F1 (H2)")
    ans.add_argument("--tier",default="L",choices=["S","M","L"]); ans.add_argument("--output",default="results")
    ans.add_argument("--methods",nargs="+",default=["rag_topk","long_context_128k","lensrag"],
                     choices=["rag_topk","long_context_128k","long_context_1m","lensrag"])
    ans.add_argument("--llm-model",default=None,help="Model id; default LENSRAG_LLM_MODEL, else claude-opus-5-5 (Claude) or gpt-4o-mini (OpenAI)")
    ans.add_argument("--llm-stack",default=None,help="Per-stage model preset, e.g. local-qwen (see lensrag/full/routing.py)")
    ans.add_argument("--llm-provider",default=None,choices=["auto","anthropic","openai","ollama"],
                     help="Default: Claude if ANTHROPIC_API_KEY is set, else OpenAI if OPENAI_API_KEY is set")
    ans.add_argument("--index-dir",default="artifacts/index_L",help="Index from build-index for the lensrag method, if present")
    ans.add_argument("--limit",type=int,help="Only the first N questions (for a quick check)")
    ans.add_argument("--qids",nargs="+",help="Only these question ids, e.g. Q001 Q070")
    ans.add_argument("--domain",default="hr")
    ans.add_argument("--no-resume",action="store_true",help="Start answers.csv afresh instead of skipping answers already in it")
    ans.add_argument("--reformat-estimates",action="store_true",help="Only re-derive and re-score LensRAG answers from their stored Mode B estimates (no LLM)")
    rep=sub.add_parser("report"); rep.add_argument("--input",default="results/metrics.csv"); rep.add_argument("--output",default="results/report.md")
    build=sub.add_parser("build-index",help="Build and persist the full LensRAG L-tier dense hybrid index")
    build.add_argument("--tier",default="L",choices=["S","M","L"]); build.add_argument("--index-dir",default="artifacts/index_L"); build.add_argument("--embedding-model",default="sentence-transformers/all-MiniLM-L6-v2")
    build.add_argument("--domain",default="hr",help="Domain config: built-in name (hr, legal) or path to a .yaml/.json file")
    build.add_argument("--corpus",help="Folder of .md/.txt documents to index instead of the BragsLabs corpus")
    osu=sub.add_parser("ollama-setup",help="Create the 32k-context Ollama model variants used by a local model stack")
    osu.add_argument("--stack",default="local-qwen"); osu.add_argument("--num-ctx",type=int,default=32768)
    pg=sub.add_parser("progress",help="Show the stage and progress of a running RUN_EXPERIMENT.sh")
    pg.add_argument("--output",default="results")
    lc=sub.add_parser("local-check",help="Report which open-source components of a local stack are ready (Table 3.1)")
    lc.add_argument("--stack",default="local-qwen")
    ent=sub.add_parser("entities",help="List the entity types and entities found in a corpus")
    ent.add_argument("--domain",default="hr",help="Domain config: built-in name (hr, legal) or path to a .yaml/.json file")
    ent.add_argument("--corpus",help="Folder of .md/.txt documents; default is the BragsLabs corpus")
    ent.add_argument("--tier",default="L",choices=["S","M","L"],help="BragsLabs corpus size tier")
    ent.add_argument("--index-dir",help="Read the inventory saved by build-index instead of scanning documents")
    ent.add_argument("--json",action="store_true",help="Print the full inventory as JSON")
    lab=sub.add_parser("label-records",help="Label the sentiment of every opinion record (exit notes, survey comments) once, at index time")
    lab.add_argument("--index-dir",default="artifacts/index_L"); lab.add_argument("--llm-stack",default=None)
    lab.add_argument("--domain",default="hr"); lab.add_argument("--workers",type=int,default=2); lab.add_argument("--limit",type=int,default=None)
    ask=sub.add_parser("ask",help="Ask a question using a persisted LensRAG index and configured LLM")
    ask.add_argument("question"); ask.add_argument("--index-dir",default="artifacts/index_L"); ask.add_argument("--llm-model",default=None,help="Model id; default claude-opus-5-5 (Claude) or gpt-4o-mini (OpenAI)");
    ask.add_argument("--llm-provider",default=None,choices=["auto","anthropic","openai","ollama"]);
    ask.add_argument("--llm-stack",default=None,help="Per-stage model preset, e.g. local-qwen (see lensrag/full/routing.py)"); ask.add_argument("--page-size",type=int,default=5,help="Chunks fetched per entity scope per retrieval round")
    args=ap.parse_args()
    base=Path(__file__).resolve().parents[1]
    zip_path=base/"data"/"bragslabs_corpus.zip"
    extracted=base/"data"/"extracted"
    if args.cmd=="inspect":
        c=ensure_extracted(zip_path,extracted); m=read_manifest(c)
        from collections import Counter
        print(json.dumps({"archive":str(zip_path),"manifest_entries":len(m),
          "tier_entries":dict(Counter(x["tier"] for x in m)),
          "retrieval_excluded":sum(bool(x.get("retrieval_exclude")) for x in m),
          "gold_questions":len((c/"gold"/"questions.jsonl").read_text().splitlines())},indent=2))
    elif args.cmd=="run":
        df,summary,config=run_experiment(zip_path,extracted,args.tiers,args.top_k,base/args.output,rerank=args.rerank,domain=args.domain,
            store_dir=None if args.no_store else base/args.store,semantic=args.semantic,embedding_model=args.embedding_model,
            long_context=not args.no_long_context,judge_model=args.judge_model,judge_threshold=args.judge_threshold)
        print(summary.to_string(index=False))
        build_report(base/args.output/"metrics.csv",base/args.output/"report.md")
        from .hypotheses import analyse
        analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}")
    elif args.cmd=="hypotheses":
        from .hypotheses import analyse
        result=analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}")
        if args.tex:
            from .hypotheses_tex import write_tex
            write_tex(result,base/args.output,base/args.tex); print(f"LaTeX: {base/args.tex}")
    elif args.cmd=="answers":
        from .answers import run_answers
        from .hypotheses import analyse
        if args.reformat_estimates:
            from .answers import reformat_estimates
            from .data import ensure_extracted, load_gold
            for c in reformat_estimates(base/args.output/"answers.csv",load_gold(ensure_extracted(zip_path,extracted))):
                print(f"{c['qid']}: {c['before']} -> {c['after']} (gold {c['gold']}, exact match {c['exact_match'][0]} -> {c['exact_match'][1]})")
            analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}"); return
        df=run_answers(zip_path,extracted,base/args.output,tier=args.tier,methods=args.methods,llm_model=args.llm_model,llm_provider=args.llm_provider,llm_stack=args.llm_stack,
                       domain=args.domain,index_dir=base/args.index_dir,limit=args.limit,qids=args.qids,store_dir=base/"artifacts/chroma",resume=not args.no_resume)
        print(df.groupby(["method","scope"])[["exact_match","set_f1","total_tokens"]].mean().to_string())
        analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}")
    elif args.cmd=="report":
        print(build_report(Path(args.input),Path(args.output)))
    elif args.cmd=="build-index":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(tier=args.tier,index_dir=args.index_dir,embedding_model=args.embedding_model,
                           domain=args.domain,corpus_dir=args.corpus)
        pipe=LensRAGPipeline.build(zip_path,extracted,cfg,use_llm=False)
        print(json.dumps({"status":"built","index_dir":args.index_dir,"domain":pipe.domain.name,"chunks":len(pipe.index.chunks),
                          "documents":len({c.doc_id for c in pipe.index.chunks}),"embedding_kind":pipe.index.embedding_kind,
                          "entities":{t:len(v) for t,v in pipe.inventory["entities"].items()}},indent=2))
    elif args.cmd=="ollama-setup":
        ollama_setup(args.stack,args.num_ctx)
    elif args.cmd=="progress":
        show_progress(base/args.output)
    elif args.cmd=="local-check":
        ok=local_check(args.stack)
        raise SystemExit(0 if ok else 1)
    elif args.cmd=="entities":
        print_entities(args,zip_path,extracted)
    elif args.cmd=="label-records":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(index_dir=args.index_dir,domain=args.domain,llm_stack=args.llm_stack)
        pipe=LensRAGPipeline.load(args.index_dir,cfg,use_llm=True)
        if args.limit:   # a trial run on the first N opinion records
            recs,_=pipe._records(); keep={id(r) for r in [r for r in recs if r.doc_type in pipe.domain.opinion_record_types][:args.limit]}
            pipe._record_index=([r for r in recs if id(r) in keep],None)
        labels=pipe.label_records(workers=args.workers)
        from collections import Counter
        print(json.dumps({"labelled":len(labels),"labels":Counter(labels.values())},indent=2))
    elif args.cmd=="ask":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(index_dir=args.index_dir,llm_model=args.llm_model,llm_provider=args.llm_provider,llm_stack=args.llm_stack,page_size=args.page_size)
        pipe=LensRAGPipeline.load(args.index_dir,cfg,use_llm=True)
        print(json.dumps(pipe.ask(args.question),ensure_ascii=False,indent=2))

def ollama_setup(stack, num_ctx):
    """Create each "lensrag-" variant (base weights + num_ctx) with `ollama create`, then list digests."""
    import subprocess, tempfile
    from .full.routing import ollama_variants
    for name, modelfile in sorted(ollama_variants(stack, num_ctx).items()):
        with tempfile.NamedTemporaryFile("w", suffix=".Modelfile", delete=False) as f:
            f.write(modelfile)
        print(f"creating {name}: {modelfile.strip().replace(chr(10), '; ')}")
        subprocess.run(["ollama", "create", name, "-f", f.name], check=True, capture_output=True)
        Path(f.name).unlink(missing_ok=True)
    out = subprocess.run(["ollama", "list"], check=True, capture_output=True, text=True).stdout
    print("\nRecord these model IDs in the report:\n" + out)


def print_entities(args, zip_path, extracted):
    """Show each entity type, where its values come from, and the entities found."""
    from .domain import load_domain
    from .data import load_documents,load_folder
    from .planning import build_inventory
    if args.index_dir:
        inv=json.loads((Path(args.index_dir)/"entities.json").read_text(encoding="utf-8"))
        domain=load_domain(inv.get("domain_source") or inv.get("domain"))
    else:
        domain=load_domain(args.domain)
        docs=load_folder(Path(args.corpus),domain) if args.corpus else load_documents(ensure_extracted(zip_path,extracted),args.tier,domain)
        inv=build_inventory(docs,domain)
    if args.json:
        print(json.dumps(inv,indent=2,ensure_ascii=False)); return
    print(f"Domain: {domain.name} ({domain.source})")
    for t in domain.entity_types:
        items=inv["entities"].get(t.name,[])
        src=f"metadata field '{t.field}'" if t.field else f"titles of {', '.join(t.from_title.get('doc_types',[]))} documents" if t.from_title else "-"
        extra=" [default fan-out]" if t.default_fanout else ""
        extra+=f" [scoped by parent: {t.parent}]" if t.parent else ""
        print(f"\n{t.name} ({len(items)}), from {src}{extra}")
        for e in items:
            bits=[e["name"]]+([f"value={e['value']}"] if e["value"]!=e["name"] else [])
            bits+=[f"parent={e['parent']}"] if e.get("parent") else []
            bits+=[f"{e['document_count']} docs"] if "document_count" in e else []
            print("  - "+", ".join(bits))
    print(f"\nversions ({len(inv['versions'])}): {', '.join(inv['versions']) or '-'}")
    print(f"periods ({len(inv['periods'])}): {', '.join(inv['periods']) or '-'}")

def show_progress(out):
    """Stage of the experiment script, answers done, and an estimated finish time."""
    import datetime as _dt, re as _re
    import pandas as pd
    log=out/"run.log"
    text=log.read_text(errors="replace") if log.exists() else ""
    tiers=_re.findall(r"^\[(S|M|L)\] documents",text,_re.M)
    if not text: stage="not started (no results/run.log)"
    elif "Ran " in text and ("OK" in text.splitlines()[-1] or "FAILED" in text): stage="finished"
    elif "LaTeX:" in text or "Hypothesis report" in text and (out/"answers.csv").exists() and "answers" in text: stage="analysis / tests"
    elif (out/"answers.csv").exists() or "build-index" in text or '"status": "built"' in text: stage="answer evaluation"
    elif tiers: stage=f"retrieval benchmark (tiers done: {', '.join(tiers)} of S, M, L)"
    else: stage="retrieval benchmark (starting)"
    print(f"Stage:   {stage}")
    cfg=out/"answers_config.json"; ans=out/"answers.csv"
    if ans.exists():
        import json as _json
        meta=_json.loads(cfg.read_text()) if cfg.exists() else {}
        total=meta.get("questions",0)*len(meta.get("methods",[])) or None
        d=pd.read_csv(ans)
        ok=d[d.error.isna()|(d.error.astype(str)=="")] if "error" in d else d
        print(f"Answers: {len(ok)} done" + (f" of {total} ({100*len(ok)/total:.0f}%)" if total else "")
              + (f", {len(d)-len(ok)} failed (retried on rerun)" if len(d)>len(ok) else ""))
        for m,g in d.groupby("method"):
            print(f"  {m:10} {len(g):3} answered, mean {g.latency_s.mean()/60:.1f} min each, exact match so far {g.exact_match.mean():.2f}")
        if total and len(d):
            per_method={m:g.latency_s.mean() for m,g in d.groupby("method")}
            left=sum((meta["questions"]-(d.method==m).sum())*per_method.get(m,max(per_method.values()))
                     for m in meta.get("methods",[]))
            eta=_dt.datetime.now()+_dt.timedelta(seconds=left)
            print(f"Remaining: about {left/3600:.1f} h (finish around {eta:%a %H:%M}), estimated from the answers so far")
    last=[l for l in text.splitlines() if l.strip() and "it/s]" not in l][-1:] 
    if last: print(f"Last log line: {last[0][:150]}")


def local_check(stack="local-qwen"):
    """Print the readiness of each model in a local stack; True when everything is ready."""
    import json as _json, os, urllib.request
    from .full.routing import STACKS, stack_components
    from .full.providers import OLLAMA_URL
    spec=STACKS[stack]; rows=[]
    base=os.getenv("OLLAMA_OPENAI_URL",OLLAMA_URL).replace("/v1","")
    try:
        with urllib.request.urlopen(base+"/api/tags",timeout=3) as r:
            served={m["name"].split(":latest")[0] for m in _json.load(r).get("models",[])}
        rows.append(("Ollama server",base,"ready"))
    except Exception:
        served=None; rows.append(("Ollama server",base,"not running: run `ollama serve`"))
    for role,model in spec["roles"].items():
        state="unknown (server down)" if served is None else "ready" if model in served else "missing: run `python -m lensrag.cli ollama-setup`"
        rows.append((f"LLM: {role}",model,state))
    from huggingface_hub import try_to_load_from_cache
    for name,model in stack_components(stack).items():
        if not model:
            rows.append((name,"-","off")); continue
        if name=="spacy_model":
            try:
                import spacy; spacy.load(model); state="ready"
            except Exception:
                state=f"missing: pip install the {model} wheel (see docs/LOCAL_MODELS.md)"
        else:
            cached=try_to_load_from_cache(model,"config.json")
            state="ready" if isinstance(cached,str) else "missing: downloads on first use, or see docs/LOCAL_MODELS.md"
        rows.append((name,model,state))
    width=max(len(r[0]) for r in rows); mw=max(len(r[1]) for r in rows)
    for a,b,c in rows: print(f"{a:<{width}}  {b:<{mw}}  {c}")
    return all(r[2] in ("ready","off") for r in rows)


if __name__=="__main__": main()
