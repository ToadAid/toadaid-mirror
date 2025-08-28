
"""
rag_map.py — Helper utilities for Tobyworld Agentic RAG
-------------------------------------------------------
Drop this file next to your RAG backend code and import it.

Core features:
- Load master maps (tagged index + adjacency) from `lore-scrolls/`
- Parse YAML-ish front matter from individual scrolls
- Arc-aware query routing (extract arcs from query)
- Neighbor expansion (chrono + per-series)
- Time-aware scoring helper
- Simple rank combiner for embeddings + arc boost + time weight
"""

from __future__ import annotations
import os, re, json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# -------------------------
# Data structures
# -------------------------

@dataclass
class DocEntry:
    id: str
    path: str
    relpath: str
    title: Optional[str]
    date: Optional[str]
    series: Optional[str]
    number: Optional[str]
    arcs: List[str]
    # neighbor ids
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    prev_L_id: Optional[str] = None
    next_L_id: Optional[str] = None
    prev_E_id: Optional[str] = None
    next_E_id: Optional[str] = None
    prev_R_id: Optional[str] = None
    next_R_id: Optional[str] = None
    prev_M_id: Optional[str] = None
    next_M_id: Optional[str] = None

# -------------------------
# Loading maps
# -------------------------

def load_maps(base_dir: str = "lore-scrolls") -> Tuple[Dict[str, DocEntry], Dict[str, List[str]]]:
    """
    Load the tagged master index and adjacency map.
    Returns:
        (entries_by_id, adjacency)
    """
    base = Path(base_dir)
    idx_path = base / "Master_Index_for_AgenticRAG_tagged.json"
    adj_path = base / "Adjacency_for_AgenticRAG.json"

    with open(idx_path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)
    with open(adj_path, "r", encoding="utf-8") as f:
        adjacency = json.load(f)

    by_id: Dict[str, DocEntry] = {}
    for e in raw_list:
        by_id[e["id"]] = DocEntry(
            id=e["id"],
            path=str(base / e["relpath"]),
            relpath=e["relpath"],
            title=e.get("title"),
            date=e.get("date"),
            series=e.get("series"),
            number=e.get("number"),
            arcs=e.get("arcs", []),
            prev_id=e.get("prev_id"),
            next_id=e.get("next_id"),
            prev_L_id=e.get("prev_L_id"),
            next_L_id=e.get("next_L_id"),
            prev_E_id=e.get("prev_E_id"),
            next_E_id=e.get("next_E_id"),
            prev_R_id=e.get("prev_R_id"),
            next_R_id=e.get("next_R_id"),
            prev_M_id=e.get("prev_M_id"),
            next_M_id=e.get("next_M_id"),
        )
    return by_id, adjacency

# -------------------------
# Front matter parser
# -------------------------

def parse_front_matter(text: str) -> Tuple[Dict, str]:
    """
    Parse minimal YAML-like front matter:
    ---
    key: value
    list: [a, b, c]
    ---
    Returns (dict, body)
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end+4:].lstrip("\n")
            data = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v.startswith("[") and v.endswith("]"):
                        vals = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                        data[k] = vals
                    else:
                        data[k] = v.strip().strip("'\"")
            return data, body
    return {}, text

# -------------------------
# Arc router
# -------------------------

ARC_HINTS = {
    "satoby": "Satoby",
    "proof of time": "ProofOfTime",
    "pot": "ProofOfTime",
    "taboshi": "Taboshi",
    "rune 3": "Rune3",
    "rune3": "Rune3",
    "jade chest": "JadeChest",
    "season 0": "Season0",
    "season0": "Season0",
    "s0": "Season0",
    "season 1": "Season1",
    "s1": "Season1",
    "season 2": "Season2",
    "s2": "Season2",
    "season 3": "Season3",
    "s3": "Season3",
    "epoch 1": "Epoch1",
    "e1": "Epoch1",
    "epoch 2": "Epoch2",
    "e2": "Epoch2",
    "epoch 3": "Epoch3",
    "e3": "Epoch3",
    "epoch 4": "Epoch4",
    "e4": "Epoch4",
    "epoch 5": "Epoch5",
    "e5": "Epoch5",
    "777": "777Burn",
    "base": "BaseChain",
    "coinbase": "BaseChain",
    "lily pad": "LilyPad",
    "patience": "PatienceToken",
    "$patience": "PatienceToken",
    "artist": "Artists",
    "artists": "Artists",
}

def arcs_from_query(query: str) -> Set[str]:
    q = query.lower()
    arcs: Set[str] = set()
    for k, v in ARC_HINTS.items():
        if k in q:
            arcs.add(v)
    return arcs

# -------------------------
# Neighbor expansion
# -------------------------

def expand_ids(seed_ids: List[str], adjacency: Dict[str, List[str]], hops: int = 1, cap: int = 12) -> List[str]:
    """
    BFS-like neighbor expansion using our adjacency map.
    hops=1 will add immediate neighbors; increase if you want a wider stroll.
    """
    seen: Set[str] = set(seed_ids)
    frontier: List[str] = list(seed_ids)
    for _ in range(max(0, hops)):
        nxt: List[str] = []
        for doc_id in frontier:
            for nb in adjacency.get(doc_id, []):
                if nb not in seen:
                    seen.add(nb)
                    nxt.append(nb)
                    if len(seen) >= cap:
                        return list(seen)
        frontier = nxt
        if not frontier:
            break
    return list(seen)

# -------------------------
# Time utilities
# -------------------------

def parse_date(d: Optional[str]) -> Optional[datetime]:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def time_weight(doc_date: Optional[str], ref_date: Optional[datetime], sigma_days: float = 60.0) -> float:
    """
    Gaussian-ish decay around ref_date (if provided). If no ref_date or no doc_date -> weight 1.0
    """
    if not ref_date:
        return 1.0
    dt = parse_date(doc_date)
    if not dt:
        return 1.0
    delta = abs((dt - ref_date).days)
    # exp(- (delta^2) / (2 * sigma^2) )
    return float(__import__("math").exp(- (delta * delta) / (2.0 * sigma_days * sigma_days)))

# -------------------------
# Rank combiner
# -------------------------

def combine_score(emb_score: float, arc_overlap: int, time_w: float,
                  w_emb: float = 1.0, w_arc: float = 0.25, w_time: float = 0.25) -> float:
    """
    Combine embedding similarity with arc overlap count and time weight.
    Tune w_* as needed.
    """
    return w_emb * emb_score + w_arc * float(arc_overlap) + w_time * time_w

# -------------------------
# Language hint (very light)
# -------------------------

def prefer_language(relpath: str, query_lang: str = "auto") -> float:
    """
    Return a small multiplier (1.0..1.1) to lightly favor EN or EN-ZH files.
    """
    lp = relpath.lower()
    if query_lang == "zh":
        return 1.1 if ("_zh" in lp or "en-zh" in lp or "zh-en" in lp) else 1.0
    if query_lang == "en":
        return 1.05 if ("_en" in lp or "en-zh" in lp or "zh-en" in lp) else 1.0
    return 1.0

# -------------------------
# Convenience: score a pool
# -------------------------

def score_pool(doc_ids: List[str],
               entries: Dict[str, DocEntry],
               query_arcs: Set[str],
               emb_scores: Dict[str, float],
               ref_date: Optional[datetime] = None,
               query_lang: str = "auto") -> List[Tuple[str, float]]:
    """
    Given a set of candidate doc ids + embedding scores, compute final ranking.
    """
    ranked: List[Tuple[str, float]] = []
    for did in doc_ids:
        e = entries.get(did)
        if not e:
            continue
        emb = emb_scores.get(did, 0.0)
        overlap = len(set(e.arcs or []) & set(query_arcs))
        tw = time_weight(e.date, ref_date)
        lang_w = prefer_language(e.relpath, query_lang)
        final = combine_score(emb, overlap, tw) * lang_w
        ranked.append((did, final))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked

# -------------------------
# Example usage
# -------------------------

if __name__ == "__main__":
    base = "lore-scrolls"
    entries, adjacency = load_maps(base)

    # Simulated retrieval
    query = "Explain Satoby and Proof of Time during Epoch 3"
    query_arcs = arcs_from_query(query)
    # pretend the embedder returned top-3
    seeds = ["TOBY_L083_LegacyOfMemechains_2025-02-19_EN.md",
             "TOBY_L110_SolasAndTheWatcher_2025-07-16_EN-ZH.md",
             "TOBY_E000_Index_Epochs_2025-08-22_EN.md"]
    expanded = expand_ids(seeds, adjacency, hops=1, cap=12)

    # Dummy embedding scores
    emb = {sid: 0.8 for sid in seeds}
    for did in expanded:
        emb.setdefault(did, 0.5)

    ref = datetime(2025, 7, 17)  # e.g., Rune3 / S0 timing
    ranked = score_pool(expanded, entries, query_arcs, emb, ref_date=ref, query_lang="en")
    for did, score in ranked[:5]:
        print(f"{did} -> {score:.3f}")
