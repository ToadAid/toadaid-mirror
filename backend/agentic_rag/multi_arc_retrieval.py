import os
import re
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DEBUG_MODE = True

# 🌿 Arc alias mapping — covers all Tobyworld domains from your 608 scrolls
arc_aliases = {
    # Core Mechanics
    "ProofOfTime": [r"proof\s+of\s+time", r"\bPoT\b"],
    "777Burn": [r"\b777\b", r"777\s+burn"],

    # Artifacts & Yield
    "Taboshi": [r"\btaboshi\b"],
    "Satoby": [r"\bsatoby\b"],
    "JadeChest": [r"jade\s*chest", r"ceremony\s+of\s+the\s+jade\s+chest", r"PATIENCE\s+grains", r"7,?777,?777"],
    "Rune3": [r"rune\s*3", r"rune\s+iii", r"rune3\s+prophecy"],

    # Epochs / Seasons
    "Season0": [r"season\s*0", r"season\s*zero", r"\bS0\b"],
    "Season1": [r"season\s*1", r"season\s*one", r"\bS1\b"],
    "Season2": [r"season\s*2", r"season\s*two", r"\bS2\b"],
    "Season3": [r"season\s*3", r"season\s*three", r"\bS3\b", r"builders?", r"PoT builders?"],
    "Epoch1": [r"epoch\s*1", r"\bE1\b"],
    "Epoch2": [r"epoch\s*2", r"\bE2\b"],
    "Epoch3": [r"epoch\s*3", r"\bE3\b"],
    "Epoch4": [r"epoch\s*4", r"\bE4\b"],

    # Themes
    "Belief": [r"belief", r"faith", r"信念"],
    "Bushido": [r"bushido", r"武士道"],
    "Patience": [r"patience", r"pati?ence\s+arc", r"why\s+is\s+patience"],

    # Entities
    "Toby": [r"\btoby\b"],
    "Toadgod": [r"toadgod"],
}

# 🔗 Concept expansion — ensures related concepts connect
concept_expansion = {
    "ProofOfTime": ["ProofOfTime", "777Burn", "Satoby", "Taboshi"],
    "777Burn": ["ProofOfTime", "777Burn", "Taboshi", "Satoby"],
    "Taboshi": ["Taboshi", "777Burn", "ProofOfTime"],
    "Satoby": ["Satoby", "ProofOfTime"],
    "JadeChest": ["JadeChest", "Season0", "Patience"],
    "Patience": ["Patience", "Season0", "ProofOfTime"],
    "Rune3": ["Rune3", "Prophecy", "Epoch4"],
    "Season0": ["Season0", "JadeChest", "Patience"],
    "Season1": ["Season1", "LPGuardian"],
    "Season2": ["Season2", "Artists"],
    "Season3": ["Season3", "Builders", "ProofOfTime"],
}

class MultiArcRetriever:
    def __init__(self, scroll_folder="lore-scrolls", data_dir=None):
        # Allow old code to pass data_dir
        if data_dir and not scroll_folder:
            scroll_folder = data_dir
        self.scroll_folder = scroll_folder
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.index = None
        self.embeddings = None
        self.scroll_texts = []
        self.scroll_names = []
        self.file_arc_map = {}
        self.query_cache = {}

    def log(self, msg):
        if DEBUG_MODE:
            print(msg)

    def extract_metadata_arc(self, text):
        """Extract arc from metadata header if present."""
        meta_match = re.search(r"---\s*arc:\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
        if meta_match:
            return meta_match.group(1).strip()
        return None

    def detect_arc(self, filename, text):
        # 1️⃣ Metadata arc first
        arc_from_meta = self.extract_metadata_arc(text)
        if arc_from_meta:
            return arc_from_meta

        # 2️⃣ Alias match in content
        for arc, patterns in arc_aliases.items():
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return arc

        # 3️⃣ Fallback: filename regex mapping
        if re.search(r"QA319", filename): return "JadeChest"
        if re.search(r"QA320B|QA320D", filename): return "Season0"
        if re.search(r"QA320C|QA320E", filename): return "Season1"
        if re.search(r"QA321B|QA321D", filename): return "Season2"
        if re.search(r"QA321C|QA321E", filename): return "Season3"
        if re.search(r"QA317|QA318|QA322|QA323", filename): return "Rune3"
        if re.search(r"QA316", filename): return "Patience"
        return "Other"

    def load_scrolls(self):
        for root, _, files in os.walk(self.scroll_folder):
            for file in files:
                if file.endswith(".md"):
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                    self.scroll_texts.append(text)
                    self.scroll_names.append(file)
                    arc_detected = self.detect_arc(file, text)
                    self.file_arc_map[file] = arc_detected
                    self.log(f"📜 {file} → arc: {arc_detected}")
        self.log(f"✅ Loaded {len(self.scroll_names)} scrolls.")

    def build_index(self):
        self.embeddings = self.model.encode(self.scroll_texts, convert_to_numpy=True)
        dim = self.embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(self.embeddings)
        self.log("✅ FAISS index built.")

    def expand_query_arc_fuzzy(self, query: str):
        matches = []
        for arc, patterns in arc_aliases.items():
            for pat in patterns:
                if re.search(pat, query, re.IGNORECASE):
                    matches.append(arc)
                    break
        expanded = set()
        for m in matches:
            expanded.update(concept_expansion.get(m, []))
        return list(expanded) if expanded else ["General"]

    def retrieve(self, query, top_k_per_arc=5):
        arcs = self.expand_query_arc_fuzzy(query)
        self.log(f"🔍 Query arcs detected: {arcs}")

        # Cache query embedding
        if query not in self.query_cache:
            self.query_cache[query] = self.model.encode([query], convert_to_numpy=True)
        q_emb = self.query_cache[query]

        scores, idxs = self.index.search(q_emb, len(self.scroll_names))
        results = []
        seen = set()

        for arc in arcs:
            arc_files = [i for i, name in enumerate(self.scroll_names)
                         if self.file_arc_map[name] == arc or arc == "General"]
            arc_ranked = [(i, scores[0][i]) for i in arc_files if i in idxs[0]]
            arc_ranked.sort(key=lambda x: x[1])  # lower distance = better match
            for i, dist in arc_ranked[:top_k_per_arc]:
                if self.scroll_names[i] not in seen:
                    seen.add(self.scroll_names[i])
                    results.append({
                        "title": self.scroll_names[i],
                        "content": self.scroll_texts[i],
                        "distance": float(dist),
                        "arc": self.file_arc_map[self.scroll_names[i]]
                    })
        if DEBUG_MODE:
            for r in results:
                self.log(f"   ↳ {r['title']} (arc: {r['arc']}, FAISS dist: {r['distance']:.4f})")
        return results

    def get_arc_distribution(self):
        """Returns a count of scrolls by arc."""
        dist = {}
        for arc in self.file_arc_map.values():
            dist[arc] = dist.get(arc, 0) + 1
        return dist
