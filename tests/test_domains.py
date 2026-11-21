import json, re, tempfile, unittest
from pathlib import Path
from lensrag.domain import load_domain
from lensrag.data import load_folder, chunk_document
from lensrag.planning import build_inventory, plan_query, build_scopes, scope_filter
from lensrag.store import ChromaChunkStore, corpus_fingerprint
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.pipeline import LensRAGPipeline, PipelineConfig

LEGAL = Path(__file__).parent / "fixtures" / "legal_corpus"


class LegalDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.domain = load_domain("legal")
        cls.docs = load_folder(LEGAL, cls.domain)
        cls.chunks = [c for d in cls.docs for c in chunk_document(d, domain=cls.domain)]
        cls.inv = build_inventory(cls.docs, cls.domain)

    def test_folder_loading_reads_domain_fields(self):
        by_id = {d.doc_id: d for d in self.docs}
        self.assertEqual(len(by_id), 6)
        self.assertEqual(by_id["STD-CONTRACTING"].meta["jurisdiction"], "ALL")  # default applied
        self.assertEqual(by_id["MSA-ACME-1"].status, "superseded")
        header = next(c for c in self.chunks if c.doc_id == "NDA-GLOBEX").enriched_text.splitlines()[0]
        self.assertIn("Jurisdiction: UK-EW", header)
        self.assertIn("Entities: England and Wales", header)

    def test_inventory_has_domain_entity_types(self):
        names = {t: [e["name"] for e in items] for t, items in self.inv["entities"].items()}
        self.assertEqual(names["party"], ["Acme Corp", "Globex Ltd", "Initech Pte"])  # own company ignored
        self.assertEqual(names["jurisdiction"], ["Delaware", "England and Wales", "New York", "Singapore"])
        self.assertEqual(self.inv["versions"], ["1.0", "2.0"])

    def test_named_party_scopes_its_contracts_plus_global_documents(self):
        p = plan_query("Which contracts with Acme allow termination on less than 60 days notice?", self.inv)
        self.assertEqual((p.qtype, p.fanout, p.named), ("filter", "party", {"party": ["Acme Corp"]}))
        (scope,) = build_scopes(p, self.inv)
        ok = scope_filter(p, scope)
        kept = sorted({c.doc_id for c in self.chunks if ok(c)})
        # Superseded v1 and the case note are out of scope; the group-wide standard is in.
        self.assertEqual(kept, ["MSA-ACME-2", "STD-CONTRACTING"])

    def test_corpus_wide_question_fans_out_by_jurisdiction(self):
        p = plan_query("Which jurisdictions require at least 30 days termination notice?", self.inv)
        self.assertEqual((p.qtype, p.fanout, p.threshold, p.comparator), ("filter", "jurisdiction", 30.0, "gte"))
        self.assertEqual(len(build_scopes(p, self.inv)), 4)

    def test_amendment_question_includes_superseded_versions(self):
        p = plan_query("How did the Acme termination notice change between version 1.0 and version 2.0?", self.inv)
        self.assertEqual(p.qtype, "version_diff")
        scopes = build_scopes(p, self.inv)
        kept = {s.version: sorted({c.doc_id for c in self.chunks if scope_filter(p, s)(c)}) for s in scopes}
        self.assertEqual(kept["1.0"], ["MSA-ACME-1", "STD-CONTRACTING"])

    def test_case_notes_only_when_asked(self):
        p = plan_query("What did the court hold about notice in the Acme case?", self.inv)
        self.assertEqual(p.doc_types, ["case_note"])
        (scope,) = build_scopes(p, self.inv)
        self.assertEqual({c.doc_id for c in self.chunks if scope_filter(p, scope)(c)}, {"CASE-2024-17"})

    def test_store_round_trip_keeps_domain_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            store = ChromaChunkStore(td, "legal")
            store.write(self.chunks, corpus_fingerprint(self.chunks))
            loaded, _ = store.load()
            self.assertEqual([c.meta for c in loaded], [c.meta for c in self.chunks])


class StubLLM:
    """Rules-only planning; extracts 'N days' notice periods; fixed answer text."""
    def json(self, system, user):
        if system.startswith("Decide for each passage"):
            data = json.loads(user)
            out = []
            for p in data["passages"]:
                m = re.search(r"(\d+) days", p["passage"])
                out.append({"index": p["index"], "relevant": bool(m and "terminat" in p["passage"]),
                            "records": [{"entity": data["scope"].split(" / ")[0], "attribute": "termination notice days",
                                         "value": int(m[1]), "evidence_span": m[0]}] if m else []})
            return {"passages": out}
        if system.startswith("Check whether"):
            return {"supported": True, "unsupported_claims": [], "notes": ""}
        return {}

    def text(self, system, user):
        return "answer"


class LegalPipelineTests(unittest.TestCase):
    def test_end_to_end_with_legal_domain(self):
        domain = load_domain("legal")
        docs = load_folder(LEGAL, domain)
        chunks = [c for d in docs for c in chunk_document(d, domain=domain)]
        inv = build_inventory(docs, domain)
        pipe = LensRAGPipeline(PersistentHybridIndex(chunks, allow_lexical_fallback=True), inv, StubLLM(),
                               PipelineConfig(domain="legal", page_size=3))
        out = pipe.ask("Which vendors can terminate on the shortest notice?")
        self.assertEqual(out["query_type"], "extremum")
        self.assertEqual(out["deterministic_result"]["entity"], "Globex Ltd")
        # The superseded 60-day Acme term is excluded, so Acme resolves to its current 30 days.
        self.assertNotIn("MSA-ACME-1", {c["doc_id"] for c in out["retrieved_chunks"]})


class CustomDomainFileTests(unittest.TestCase):
    def test_json_domain_file(self):
        cfg = {"name": "research", "description": "papers", "defaults": {"lab": "ALL"},
               "entity_types": [{"name": "lab", "plural": "labs", "field": "lab", "default_fanout": True}],
               "header": "Document: {title_or_id} | Lab: {lab}"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "research.json"; path.write_text(json.dumps(cfg))
            corpus = Path(td) / "docs"; corpus.mkdir()
            (corpus / "a.md").write_text("---\nlab: Vision\n---\n# Paper A\nAccuracy is 91 percent.")
            (corpus / "b.md").write_text("# Paper B\nNo front matter at all.")
            domain = load_domain(str(path))
            docs = load_folder(corpus, domain)
            self.assertEqual(sorted(d.doc_id for d in docs), ["a", "b"])
            inv = build_inventory(docs, domain)
            self.assertEqual([e["name"] for e in inv["entities"]["lab"]], ["Vision"])
            self.assertEqual(chunk_document(docs[1], domain=domain)[0].enriched_text.splitlines()[0],
                             "Document: Paper B | Lab: ALL")
            p = plan_query("Which labs report accuracy above 90?", inv)
            self.assertEqual((p.qtype, p.fanout), ("filter", "lab"))


if __name__ == "__main__":
    unittest.main()
