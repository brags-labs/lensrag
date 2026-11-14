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
    hyp=sub.add_parser("hypotheses",help="Test H1-H3 from an experiment's metrics.csv (and answers.csv if present)")
    hyp.add_argument("--output",default="results")
    ans=sub.add_parser("answers",help="Answer the gold questions with an LLM and score exact match / set F1 (H2)")
    ans.add_argument("--tier",default="L",choices=["S","M","L"]); ans.add_argument("--output",default="results")
    ans.add_argument("--methods",nargs="+",default=["rag_topk","long_context_128k","lensrag"],
                     choices=["rag_topk","long_context_128k","long_context_1m","lensrag"])
    ans.add_argument("--llm-model",default=None,help="Model id; default LENSRAG_LLM_MODEL, else claude-opus-5-5 (Claude) or gpt-4o-mini (OpenAI)")
    ans.add_argument("--llm-provider",default=None,choices=["auto","anthropic","openai"],
                     help="Default: Claude if ANTHROPIC_API_KEY is set, else OpenAI if OPENAI_API_KEY is set")
    ans.add_argument("--index-dir",default="artifacts/index_L",help="Index from build-index for the lensrag method, if present")
    ans.add_argument("--limit",type=int,help="Only the first N questions (for a quick check)")
    ans.add_argument("--domain",default="hr")
    rep=sub.add_parser("report"); rep.add_argument("--input",default="results/metrics.csv"); rep.add_argument("--output",default="results/report.md")
    build=sub.add_parser("build-index",help="Build and persist the full LensRAG L-tier dense hybrid index")
    build.add_argument("--tier",default="L",choices=["S","M","L"]); build.add_argument("--index-dir",default="artifacts/index_L"); build.add_argument("--embedding-model",default="sentence-transformers/all-MiniLM-L6-v2")
    build.add_argument("--domain",default="hr",help="Domain config: built-in name (hr, legal) or path to a .yaml/.json file")
    build.add_argument("--corpus",help="Folder of .md/.txt documents to index instead of the BragsLabs corpus")
    ent=sub.add_parser("entities",help="List the entity types and entities found in a corpus")
    ent.add_argument("--domain",default="hr",help="Domain config: built-in name (hr, legal) or path to a .yaml/.json file")
    ent.add_argument("--corpus",help="Folder of .md/.txt documents; default is the BragsLabs corpus")
    ent.add_argument("--tier",default="L",choices=["S","M","L"],help="BragsLabs corpus size tier")
    ent.add_argument("--index-dir",help="Read the inventory saved by build-index instead of scanning documents")
    ent.add_argument("--json",action="store_true",help="Print the full inventory as JSON")
    ask=sub.add_parser("ask",help="Ask a question using a persisted LensRAG index and configured LLM")
    ask.add_argument("question"); ask.add_argument("--index-dir",default="artifacts/index_L"); ask.add_argument("--llm-model",default=None,help="Model id; default claude-opus-5-5 (Claude) or gpt-4o-mini (OpenAI)");
    ask.add_argument("--llm-provider",default=None,choices=["auto","anthropic","openai"]); ask.add_argument("--page-size",type=int,default=5,help="Chunks fetched per entity scope per retrieval round")
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
            long_context=not args.no_long_context)
        print(summary.to_string(index=False))
        build_report(base/args.output/"metrics.csv",base/args.output/"report.md")
        from .hypotheses import analyse
        analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}")
    elif args.cmd=="hypotheses":
        from .hypotheses import analyse
        analyse(base/args.output); print(f"Hypothesis report: {base/args.output/'hypotheses.md'}")
    elif args.cmd=="answers":
        from .answers import run_answers
        from .hypotheses import analyse
        df=run_answers(zip_path,extracted,base/args.output,tier=args.tier,methods=args.methods,llm_model=args.llm_model,llm_provider=args.llm_provider,
                       domain=args.domain,index_dir=base/args.index_dir,limit=args.limit,store_dir=base/"artifacts/chroma")
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
    elif args.cmd=="entities":
        print_entities(args,zip_path,extracted)
    elif args.cmd=="ask":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(index_dir=args.index_dir,llm_model=args.llm_model,llm_provider=args.llm_provider,page_size=args.page_size)
        pipe=LensRAGPipeline.load(args.index_dir,cfg,use_llm=True)
        print(json.dumps(pipe.ask(args.question),ensure_ascii=False,indent=2))

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

if __name__=="__main__": main()
