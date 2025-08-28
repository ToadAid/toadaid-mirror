# agentic_rag/multi_arc_retrieval.py — normalized embeddings + IP + thresholds + global top-k

import os
import re
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DEBUG_MODE = True

# ---------- Normalization & Ignore Rules ----------

def _normalize_query(q: str) -> str:
    """
    Canonicalize common punctuation/variants so matching and embeddings behave.
    """
    q = (q or "").replace("—", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")
    q = re.sub(r"\s+", " ", q).strip()
    # canonicalize common variants
    q = re.sub(r"\btoby\s*world\b", "tobyworld", q, flags=re.I)
    q = re.sub(r"\btaboshi\s*v\s*([12])\b", r"taboshi \1", q, flags=re.I)  # "taboshi v1" -> "taboshi 1"
    return q

# Ignore training/eval folders & files so they don't pollute RAG
IGNORED_DIRS = {"training", "mirror_train", "datasets", ".git", ".github", "__pycache__"}
IGNORE_FILE_RE = re.compile(r"(eval|dataset|prompt|system_prompt)\.(md|txt)$", re.I)

# ---------- Arc Aliases ----------

arc_aliases = {
    # Core Mechanics
    "ProofOfTime": [r"proof\s+of\s+time", r"\bpot\b"],
    "777Burn":     [r"\b777\b", r"777\s+burn"],

    # Artifacts & Yield (split Taboshi1 from TABOSHI)
    "Taboshi1": [
        r"\btaboshi[-_ ]?1\b",
        r"\btaboshi\s*v?1\b",
        r"\btaboshi\s*i\b",
        r"\btaboshi\s*one\b"
    ],
    "Taboshi": [
        r"\btaboshi\b",               # generic TABOSHI (ERC-1155/20, Leaf of Yield)
        r"\btaboshi[-_ ]?2\b",
        r"\btaboshi\s*v?2\b",
        r"\btaboshi\s*ii\b",
        r"\bleaf\s+of\s+yield\b"      # phrase routes to TABOSHI
    ],
    "Satoby":   [r"\bsatoby\b", r"\bleaf\s+that\s+remembers\b"],
    "JadeChest":[r"jade\s*chest", r"ceremony\s+of\s+the\s+jade\s+chest", r"PATIENCE\s+grains", r"7,?777,?777"],
    "Rune3":    [r"rune\s*3", r"rune\s+iii", r"rune3\s+prophecy"],

    # Epochs / Seasons
    "Season0": [r"season\s*0", r"season\s*zero", r"\bs0\b"],
    "Season1": [r"season\s*1", r"season\s*one",  r"\bs1\b"],
    "Season2": [r"season\s*2", r"season\s*two",  r"\bs2\b"],
    "Season3": [r"season\s*3", r"season\s*three", r"\bs3\b", r"builders?", r"pot\s+builders?" ],
    "Epoch1":  [r"epoch\s*1", r"\be1\b"],
    "Epoch2":  [r"epoch\s*2", r"\be2\b"],
    "Epoch3":  [r"epoch\s*3", r"\be3\b"],
    "Epoch4":  [r"epoch\s*4", r"\be4\b"],

    # Themes (include Lore)
    "Lore": [
        r"\blore\b", r"\bcanon(?:ical)?\b", r"\bmythos\b",
        r"\bworld\s*building|worldbuilding\b",
        r"\bprophec(?:y|ies)\b", r"\bscrolls?\b", r"\brunes?\b",
        r"\bfallen\s+frogs?\b"
    ],
    "Belief":   [r"\bbelief\b", r"\bfaith\b", r"信念"],
    "Bushido":  [r"\bbushido\b", r"武士道"],
    "Patience": [r"\bpatience\b", r"pati?ence\s+arc", r"why\s+is\s+patience"],

    # Entities
    "Toby": [
        r"\btoby\b",
        r"\btobyworld\b", r"\btoby[-_ ]*world\b", r"\btobyverse\b"
    ],
    "Toadgod": [r"\btoadgod\b"],

    # Optional utility arcs if you use them in indexing
    "Recovery": [r"lost\s+wallet", r"\brecover(y|ing)\b", r"verify\s+lost\s+taboshi"],
    "Base":     [r"\bbase\b", r"base\s*chain", r"\bonchain\b"],
    "Sat0AI":   [r"\bsat0ai\b", r"\bsatai\b", r"sat0\s*ai"],
}

# ---------- Concept expansion (soft) ----------

concept_expansion = {
    "ProofOfTime": ["ProofOfTime", "777Burn", "Satoby", "Taboshi1", "Taboshi"],
    "777Burn":     ["ProofOfTime", "777Burn", "Taboshi1", "Satoby"],
    "Taboshi1":    ["Taboshi1", "777Burn", "ProofOfTime", "Satoby"],
    "Taboshi":     ["Taboshi", "Lore"],
    "Satoby":      ["Satoby", "ProofOfTime"],
    "JadeChest":   ["JadeChest", "Season0", "Patience"],
    "Patience":    ["Patience", "Season0", "ProofOfTime"],
    "Rune3":       ["Rune3", "Prophecy", "Epoch4"],
    "Season0":     ["Season0", "JadeChest", "Patience"],
    "Season1":     ["Season1"],
    "Season2":     ["Season2"],
    "Season3":     ["Season3", "ProofOfTime"],
    "Lore":        ["Lore", "Toby", "Toadgod", "Patience"],
}

class MultiArcRetriever:
    def __init__(self, scroll_folder="lore-scrolls", data_dir=None, global_top_k=12, sim_threshold=0.25):
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
        self.GLOBAL_TOP_K = global_top_k
        self.SIM_THRESHOLD = sim_threshold

    def log(self, msg):
        if DEBUG_MODE:
            print(msg)

    def extract_metadata_arc(self, text):
        meta_match = re.search(r"---\s*arc:\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
        if meta_match:
            return meta_match.group(1).strip()
        return None

    def detect_arc(self, filename, text):
        arc_from_meta = self.extract_metadata_arc(text)
        if arc_from_meta:
            return arc_from_meta
        for arc, patterns in arc_aliases.items():
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return arc
        # filename fallbacks
        if re.search(r"QA319", filename): return "JadeChest"
        if re.search(r"QA320B|QA320D", filename): return "Season0"
        if re.search(r"QA320C|QA320E", filename): return "Season1"
        if re.search(r"QA321B|QA321D", filename): return "Season2"
        if re.search(r"QA321C|QA321E", filename): return "Season3"
        if re.search(r"QA317|QA318|QA322|QA323", filename): return "Rune3"
        if re.search(r"QA316", filename): return "Patience"
        return "Other"

    def load_scrolls(self):
        self.scroll_texts = []
        self.scroll_names = []
        self.file_arc_map = {}

        ignored_dirs_lower = {d.lower() for d in IGNORED_DIRS}

        for root, dirs, files in os.walk(self.scroll_folder):
            # prune directories in-place (case-insensitive + hidden/underscored)
            dirs[:] = [
                d for d in dirs
                if d.lower() not in ignored_dirs_lower and not d.startswith((".","_"))
            ]

            for file in files:
                if not file.endswith(".md"):
                    continue
                if IGNORE_FILE_RE.search(file):
                    # e.g., mirror_eval_checks.md, mirror_dataset.md, system_prompt.txt, etc.
                    continue

                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception as e:
                    self.log(f"⚠️ Skipping {file}: {e}")
                    continue

                self.scroll_texts.append(text)
                self.scroll_names.append(file)  # keep basename for stable logs
                arc_detected = self.detect_arc(file, text)
                self.file_arc_map[file] = arc_detected
                self.log(f"📜 {file} → arc: {arc_detected}")

        self.log(f"✅ Loaded {len(self.scroll_names)} scrolls.")

    def build_index(self):
        if not self.scroll_texts:
            self.log("⚠️ No scrolls loaded; index not built.")
            self.embeddings = None
            self.index = None
            return
        self.embeddings = self.model.encode(self.scroll_texts, convert_to_numpy=True)
        # Normalize for cosine/IP
        self.embeddings = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        dim = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(self.embeddings)
        self.log("✅ FAISS index (IP) built.")

    def expand_query_arc_fuzzy(self, query: str):
        q = _normalize_query(query)
        matches = []
        for arc, patterns in arc_aliases.items():
            for pat in patterns:
                if re.search(pat, q, re.IGNORECASE):
                    matches.append(arc)
                    break
        expanded = set()
        for m in matches:
            expanded.update(concept_expansion.get(m, []))
        return list(expanded) if expanded else ["General"]

    def retrieve(self, query, top_k_per_arc=5):
        arcs = self.expand_query_arc_fuzzy(query)
        self.log(f"🔍 Query arcs detected: {arcs}")

        q_norm = _normalize_query(query)
        if q_norm not in self.query_cache:
            q = self.model.encode([q_norm], convert_to_numpy=True)
            q = q / np.linalg.norm(q, axis=1, keepdims=True)
            self.query_cache[q_norm] = q
        q_emb = self.query_cache[q_norm]

        if not self.index or not self.scroll_names:
            self.log("⚠️ Index not ready or no scrolls.")
            return []

        scores, idxs = self.index.search(q_emb, len(self.scroll_names))
        results = []
        leftovers = []

        # balance per-arc selection first
        per_arc = max(2, self.GLOBAL_TOP_K // max(1, len(arcs)))
        taken = set()

        for arc in arcs:
            arc_files = [i for i, name in enumerate(self.scroll_names)
                         if self.file_arc_map.get(name) == arc or arc == "General"]
            arc_ranked = [(i, scores[0][i]) for i in arc_files if i in idxs[0]]
            # IP: higher is better
            arc_ranked.sort(key=lambda x: x[1], reverse=True)
            picked = 0
            for i, sim in arc_ranked:
                if sim < self.SIM_THRESHOLD:  # drop weak hits
                    continue
                if self.scroll_names[i] in taken:
                    continue
                results.append({
                    "title": self.scroll_names[i],
                    "content": self.scroll_texts[i],
                    "similarity": float(sim),
                    "arc": self.file_arc_map.get(self.scroll_names[i], "Other")
                })
                taken.add(self.scroll_names[i])
                picked += 1
                if picked >= per_arc:
                    break
            # collect leftovers for later fill
            for i, sim in arc_ranked:
                if sim >= self.SIM_THRESHOLD and self.scroll_names[i] not in taken:
                    leftovers.append((i, sim))

        # fill up to GLOBAL_TOP_K from leftovers (best-first)
        leftovers.sort(key=lambda x: x[1], reverse=True)
        for i, sim in leftovers:
            if len(results) >= self.GLOBAL_TOP_K:
                break
            if self.scroll_names[i] in taken:
                continue
            results.append({
                "title": self.scroll_names[i],
                "content": self.scroll_texts[i],
                "similarity": float(sim),
                "arc": self.file_arc_map.get(self.scroll_names[i], "Other")
            })
            taken.add(self.scroll_names[i])

        if DEBUG_MODE:
            for r in results:
                self.log(f"   ↳ {r['title']} (arc: {r['arc']}, sim: {r['similarity']:.4f})")
        return results

    def get_arc_distribution(self):
        dist = {}
        for arc in self.file_arc_map.values():
            dist[arc] = dist.get(arc, 0) + 1
        return dist
