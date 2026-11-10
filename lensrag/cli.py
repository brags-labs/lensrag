from __future__ import annotations
import argparse, zipfile, json
from pathlib import Path
from .data import ensure_extracted,read_manifest
from .experiment import run_experiment
from .reporting import build_report

def main():
    ap=argparse.ArgumentParser(prog="lensrag",description="BragsLabs LensRAG experiment runner")
    sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("inspect")
    run=sub.add_parser("run")
    run.add_argument("--tiers",nargs="+",default=["S","M","L"],choices=["S","M","L"])
    run.add_argument("--top-k",type=int,default=10)
    run.add_argument("--output",default="results")
    rep=sub.add_parser("report"); rep.add_argument("--input",default="results/metrics.csv"); rep.add_argument("--output",default="results/report.md")
    build=sub.add_parser("build-index",help="Build and persist the full LensRAG L-tier dense hybrid index")
    build.add_argument("--tier",default="L",choices=["S","M","L"]); build.add_argument("--index-dir",default="artifacts/index_L"); build.add_argument("--embedding-model",default="sentence-transformers/all-MiniLM-L6-v2")
    ask=sub.add_parser("ask",help="Ask a question using a persisted LensRAG index and configured LLM")
    ask.add_argument("question"); ask.add_argument("--index-dir",default="artifacts/index_L"); ask.add_argument("--llm-model",default="gpt-4o-mini"); ask.add_argument("--top-k",type=int,default=12)
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
        df,summary,config=run_experiment(zip_path,extracted,args.tiers,args.top_k,base/args.output)
        print(summary.to_string(index=False))
        build_report(base/args.output/"metrics.csv",base/args.output/"report.md")
    elif args.cmd=="report":
        print(build_report(Path(args.input),Path(args.output)))
    elif args.cmd=="build-index":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(tier=args.tier,index_dir=args.index_dir,embedding_model=args.embedding_model)
        pipe=LensRAGPipeline.build(zip_path,extracted,cfg,use_llm=False)
        print(json.dumps({"status":"built","index_dir":args.index_dir,"chunks":len(pipe.index.chunks),"documents":len({c.doc_id for c in pipe.index.chunks}),"embedding_kind":pipe.index.embedding_kind},indent=2))
    elif args.cmd=="ask":
        from .full.pipeline import LensRAGPipeline,PipelineConfig
        cfg=PipelineConfig(index_dir=args.index_dir,llm_model=args.llm_model,top_k=args.top_k)
        pipe=LensRAGPipeline.load(args.index_dir,cfg,use_llm=True)
        print(json.dumps(pipe.ask(args.question),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
