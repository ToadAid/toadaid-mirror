"""
retriever.py — Glue layer for MultiArcRetriever + rag_map helpers

Usage (server):
    from agentic_rag import retriever
    retriever.init(scroll_dir="lore-scrolls")  # once at startup
    ranked = retriever.get_ranked("What is Satoby?")
    docs   = retriever.load_docs(ranked[:6])   # fetch bodies/paths for the top docs

This file keeps your FAISS code (multi_arc_retrieval.py) separate from higher-level
navigation (neighbors, arcs, time-aware scoring).
"""

import os
import json
import threading
from collections import Counter
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# --- Flexible imports (supports running as a module or script) ---
try:
    from agentic_rag.multi_arc_retrieval import MultiArcRetriever  # normal package import
except Exception:  # pragma: no cover
    from multi_arc_retrieval import MultiArcRetriever  # fallback if placed in same folder

try:
    from agentic_rag.rag_map import load_maps, arcs_from_query, expand_ids, score_pool
except Exception:  # pragma: no cover
    from rag_map import load_maps, arcs_from_query, expand_ids, score_pool

# ---------------- Config ----------------
DEFAULT_SCROLL_DIR = "lore-scrolls"
GLOBAL_TOP_K       = 12     # final number of docs to consider
EXPANSION_HOPS     = 1      # graph expansion hops
EXPANSION_CAP      = 32     # max docs after expansion
FINAL_RETURN_K     = 12     # what we return to caller

# Optional: set a default reference date for time-weighting if desired
# e.g., Rune3 Ceremony date window; set to None to disable
DEFAULT_REF_DATE: Optional[datetime] = None  # e.g., datetime(2025, 7, 17)

# ----------------------------------------

_lock = threading.Lock()
_state: Dict[str, object] = {
    "inited": False,
    "scroll_dir": None,
    "entries": None,     # dict[str, Entry] from rag_map.load_maps()
    "adjacency": None,   # dict[str, set[str]] from rag_map.load_maps()
    "retriever": None,   # MultiArcRetriever instance
}

def init(scroll_dir: str = DEFAULT_SCROLL_DIR,
         global_top_k: int = GLOBAL_TOP_K,
         sim_threshold: float = 0.25):
    """
    Initialize once at startup.
    - Loads rag maps (tagged master + adjacency)
    - Loads and indexes scrolls via MultiArcRetriever
    """
    with _lock:
        if _state["inited"] and _state["scroll_dir"] == scroll_dir:
            return

        # Load maps (for arcs/time/graph)
        entries, adjacency = load_maps(scroll_dir)
        _state["entries"]   = entries
        _state["adjacency"] = adjacency

        # Setup FAISS retriever
        mr = MultiArcRetriever(scroll_folder=scroll_dir, global_top_k=global_top_k, sim_threshold=sim_threshold)
        mr.load_scrolls()
        mr.build_index()

        _state["retriever"] = mr
        _state["scroll_dir"] = scroll_dir
        _state["inited"] = True

def _ensure_init():
    if not _state["inited"]:
        init()

def get_ranked(query: str,
               final_k: int = FINAL_RETURN_K,
               ref_date: Optional[datetime] = DEFAULT_REF_DATE,
               query_lang: str = "auto") -> List[Tuple[str, float]]:
    """
    Full pipeline:
      1) Use FAISS retriever to get arc-balanced seeds + similarities
      2) Expand with graph neighbors
      3) Re-rank with arc overlap + time weighting
      4) Return [(doc_id, score), ...]
    """
    _ensure_init()
    mr: MultiArcRetriever = _state["retriever"]  # type: ignore[assignment]
    ents: Dict[str, object] = _state["entries"]  # type: ignore[assignment]
    adj: Dict[str, object]  = _state["adjacency"]  # type: ignore[assignment]

    # 1) FAISS results (already arc-balanced)
    faiss_results = mr.retrieve(query, top_k_per_arc=5)
    if not faiss_results:
        return []

    # Pack seeds and initial embedding scores
    seeds: List[str] = []
    emb_scores: Dict[str, float] = {}
    for r in faiss_results:
        doc_id = r["title"]   # we used basename file names as ids
        seeds.append(doc_id)
        emb_scores[doc_id] = float(r.get("similarity", 0.0))

    # 2) Graph expansion (chrono + per-series) using adjacency
    expanded_ids = expand_ids(seeds, adj, hops=EXPANSION_HOPS, cap=EXPANSION_CAP)

    # 3) Re-rank using arcs + time weighting (keeps emb scores as base signal)
    ranked = score_pool(expanded_ids, ents, arcs_from_query(query), emb_scores,
                        ref_date=ref_date, query_lang=query_lang)

    # 4) Return top-k
    return ranked[:final_k]

def load_docs(doc_pairs: List[Tuple[str, float]]) -> List[Dict]:
    """
    Given ranked [(doc_id, score), ...], load paths and content.
    Returns a list of dicts: {id, score, path, title, date, series, arcs, content}
    """
    _ensure_init()
    ents: Dict[str, object] = _state["entries"]  # type: ignore[assignment]

    out: List[Dict] = []
    for doc_id, score in doc_pairs:
        ent = ents.get(doc_id)  # type: ignore[index]
        if not ent:
            continue
        try:
            with open(ent.path, "r", encoding="utf-8") as f:  # type: ignore[attr-defined]
                content = f.read()
        except Exception:
            content = ""
        out.append({
            "id": ent.id,                # type: ignore[attr-defined]
            "score": float(score),
            "path": ent.path,            # type: ignore[attr-defined]
            "relpath": ent.relpath,      # type: ignore[attr-defined]
            "title": ent.title,          # type: ignore[attr-defined]
            "date": ent.date,            # type: ignore[attr-defined]
            "series": ent.series,        # type: ignore[attr-defined]
            "number": ent.number,        # type: ignore[attr-defined]
            "arcs": ent.arcs,            # type: ignore[attr-defined]
            "content": content,
        })
    return out

# Optional helper: one-call retrieval for server endpoints
def get_context(query: str, top_n: int = 8) -> List[Dict]:
    """
    Returns the top_n documents with content for answering the query.
    """
    ranked = get_ranked(query, final_k=top_n)
    return load_docs(ranked)

# ---------- NEW: status / stats helpers for /reload ----------

def get_all_entries() -> List[object]:
    """
    Return the list of Entry objects held in memory.
    Each Entry typically has: id, title, path, relpath, arcs (list|str|None), ...
    """
    _ensure_init()
    ents = _state["entries"]
    if isinstance(ents, dict):
        return list(ents.values())
    return []

def get_doc_count() -> int:
    """
    Total number of loaded documents.
    """
    return len(get_all_entries())

def get_arc_distribution() -> Dict[str, int]:
    """
    Count how many docs belong to each arc.
    Looks for 'arcs' (list/str) on every entry; ignores empty.
    Sorted by count desc.
    """
    counts = Counter()
    for ent in get_all_entries():
        arcs = getattr(ent, "arcs", None)
        if not arcs:
            continue
        if isinstance(arcs, str):
            arcs = [arcs]
        for a in arcs or []:
            if a:
                counts[a] += 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

def get_graph_size() -> int:
    """
    Return number of nodes in the adjacency mapping (best-effort).
    """
    _ensure_init()
    adj = _state["adjacency"]
    try:
        return len(adj)  # type: ignore[arg-type]
    except Exception:
        return 0
