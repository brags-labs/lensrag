import tempfile, unittest
from pathlib import Path
from lensrag.data import Chunk
from lensrag.full.index import PersistentHybridIndex
from lensrag.full.pipeline import build_entity_inventory
from lensrag.data import Document

class FullRuntimeTests(unittest.TestCase):
    def chunk(self, cid, text, country='IN'):
        return Chunk(cid,cid.split('::')[0],cid,'policy',country,'v1','2025-01-01','active','2025',('India',),'Leave',text,'Document: '+text)
    def test_lexical_dev_index_search_and_persist(self):
        chunks=[self.chunk('d1::1','India annual leave entitlement is 20 days'),self.chunk('d2::1','US payroll tax procedure')]
        idx=PersistentHybridIndex(chunks,allow_lexical_fallback=True)
        hits=idx.search('annual leave India',top_k=1)
        self.assertEqual(hits[0][0].doc_id,'d1')
        with tempfile.TemporaryDirectory() as td:
            idx.save(td,'abc')
            loaded,meta=PersistentHybridIndex.load(td,'abc')
            self.assertEqual(meta['chunks'],2)
            self.assertEqual(loaded.search('annual leave',1)[0][0].doc_id,'d1')
    def test_stale_fingerprint_rejected(self):
        idx=PersistentHybridIndex([self.chunk('d1::1','leave policy')],allow_lexical_fallback=True)
        with tempfile.TemporaryDirectory() as td:
            idx.save(td,'abc')
            with self.assertRaises(ValueError): PersistentHybridIndex.load(td,'different')
    def test_entity_inventory_counts_documents(self):
        docs=[Document('1','a','policy','IN','v1','','','active','L',''),Document('2','b','addendum','IN','v2','','','active','L',''),Document('3','c','policy','US','v1','','','active','L','')]
        inv=build_entity_inventory(docs)
        india=next(x for x in inv if x['name']=='India')
        self.assertEqual(india['document_count'],2)
        self.assertEqual(india['doc_types'],['addendum','policy'])

if __name__=='__main__': unittest.main()
