import tempfile, unittest
import numpy as np
from lensrag.data import Chunk, Document
from lensrag.store import ChromaChunkStore, corpus_fingerprint, document_fingerprint
from lensrag.experiment import tier_index


def chunk(cid, text, country="IN"):
    return Chunk(cid, cid.split("::")[0], cid, "policy", country, "v1", "2025-01-01", "current", "2025",
                 ("India", "Germany"), "Leave", text, "Document: " + text)


class ChromaStoreTests(unittest.TestCase):
    def test_round_trip_keeps_order_metadata_and_vectors(self):
        chunks = [chunk("b::C0001", "second"), chunk("a::C0000", "first", "DE"), chunk("c::C0000", "third")]
        vecs = np.eye(3, 4, dtype=np.float32)
        with tempfile.TemporaryDirectory() as td:
            store = ChromaChunkStore(td, "test")
            fp = corpus_fingerprint(chunks)
            store.write(chunks, fp, vecs, "test-model")
            self.assertTrue(store.is_current(fp, "test-model"))
            self.assertFalse(store.is_current("other", "test-model"))
            self.assertFalse(store.is_current(fp, "other-model"))
            # A fresh client on the same directory sees the persisted data.
            got, got_vecs = ChromaChunkStore(td, "test").load(with_embeddings=True)
            self.assertEqual([c.chunk_id for c in got], [c.chunk_id for c in chunks])
            self.assertEqual(got[1].country, "DE")
            self.assertEqual(got[0].entities, ("India", "Germany"))
            np.testing.assert_allclose(got_vecs, vecs)

    def test_tier_index_reuses_store_until_documents_change(self):
        docs = [Document("POL-1", "p.md", "policy", "IN", "1.0", "", "", "current", "S", "# Leave\nIndia leave is 20 days.")]
        with tempfile.TemporaryDirectory() as td:
            _, chunks1, info1 = tier_index(docs, "S", td)
            _, chunks2, info2 = tier_index(docs, "S", td)
            self.assertEqual(info1["source"], "built+stored")
            self.assertEqual(info2["source"], "chroma")
            self.assertEqual([c.enriched_text for c in chunks1], [c.enriched_text for c in chunks2])
            docs[0].text += "\nUpdated."
            _, _, info3 = tier_index(docs, "S", td)
            self.assertEqual(info3["source"], "built+stored")
            self.assertNotEqual(document_fingerprint(docs, {}), "")


if __name__ == "__main__":
    unittest.main()
