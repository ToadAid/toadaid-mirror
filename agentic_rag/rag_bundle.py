# agentic_rag/rag_bundle.py
import json, numpy as np
from pathlib import Path
from typing import List, Dict

class RagBundleRetriever:
    def __init__(self, bundle_dir="rag_index_bundle", global_top_k=12):
        self.bundle_dir = Path(bundle_dir)
        self.global_top_k = global_top_k
        self.vocab = None
        self.idf = None
        self.indptr = None
        self.indices = None
        self.data = None
        self.docs = None

    def load_bundle(self):
        B = self.bundle_dir
        self.vocab = json.loads((B/"vocab.json").read_text())
        self.idf = np.load(B/"idf.npy")
        self.indptr = np.load(B/"indptr.npy")
        self.indices = np.load(B/"indices.npy")
        self.data = np.load(B/"data.npy")
        self.docs = [json.loads(line) for line in (B/"docs.jsonl").read_text().splitlines()]

    def retrieve(self, query: str, top_k_per_arc: int = 5) -> List[Dict]:
        # copy query_vector + cosine logic from rag_search.py
        # return [{"title": d["doc_id"], "similarity": score} ...] like MultiArcRetriever does
        ...
