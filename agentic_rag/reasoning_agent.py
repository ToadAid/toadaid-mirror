import re
from typing import List, Tuple, Union, Dict, Any
import math
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer

DEBUG_MODE = True

def _now_ymd():
    return datetime.utcnow()

def _log(msg: str):
    if DEBUG_MODE:
        print(msg)

def _extract_date_from_name(name: str) -> datetime | None:
    # Match YYYY-MM-DD in filenames like TOBY_L106_FourSeasonsOfPatience_2025-07-17_EN-ZH.md
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", name)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None

def _as_tuple_records(retrieved_scrolls: List[Any]) -> List[Tuple[str, str, float, str]]:
    """
    Normalize incoming results into tuples:
    (name, text, similarity_score_in_[0,1], arc_or_None)

    Supports:
      - dict style: {"title","content","similarity","arc"}  (from MultiArcRetriever updated)
      - tuple style: (name, text, dist)  or  (score, name, text, dist)
        We convert L2 distances to a soft similarity ~ max(0, 1 - dist/10)
    """
    normed = []
    for item in retrieved_scrolls:
        if isinstance(item, dict):
            name = item.get("title") or item.get("filename") or "Untitled"
            text = item.get("content") or item.get("text") or ""
            arc  = item.get("arc") or ""
            sim  = item.get("similarity")
            if sim is None:
                # fallback if someone passes "distance"
                dist = item.get("distance", None)
                sim = max(0.0, 1.0 - (float(dist) / 10.0)) if dist is not None else 0.0
            normed.append((name, text, float(sim), arc))
        elif isinstance(item, (list, tuple)):
            # Common shapes:
            # (name, text, dist) OR (score, name, text, dist)
            if len(item) == 4:
                _, name, text, dist = item
                sim = max(0.0, 1.0 - (float(dist) / 10.0))
                normed.append((name, text, sim, ""))
            elif len(item) == 3:
                name, text, dist = item
                sim = max(0.0, 1.0 - (float(dist) / 10.0))
                normed.append((name, text, sim, ""))
            else:
                # Best effort
                name = str(item[0]) if len(item) > 0 else "Untitled"
                text = str(item[1]) if len(item) > 1 else ""
                sim  = 0.0
                normed.append((name, text, sim, ""))
        else:
            # Unknown shape → skip
            continue
    return normed

class ReasoningAgent:
    """
    Curates the set of scrolls passed to the LLM:
      - Hybrid scoring: arc/term matches + (cosine/IP) similarity + QA bias + recency
      - MMR diversification to reduce redundancy
    """
    def __init__(self,
                 mmr: bool = True,
                 mmr_lambda: float = 0.65,
                 emb_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.mmr = mmr
        self.mmr_lambda = mmr_lambda
        self.model = SentenceTransformer(emb_model)

        # Arc priority terms (v1 split from TABOSHI)
        self.priority_terms = {
            # v1 (777-burn) gets its own cues so it outranks generic TABOSHI hits
            "Taboshi1": [
                "taboshi 1", "taboshi v1", "taboshi i", "taboshi one",
                "777 $toby", "proof of sacrifice", "minter wallet",
                "zora", "epoch 2", "proof of time", "satoby eligibility"
            ],

            # Seasons / ceremonies
            "Season0": ["season 0", "season zero", r"jade chest", r"pati?ence"],
            "Season1": ["season 1", "lp guardians?"],
            "Season2": ["season 2", "artists?"],
            "Season3": ["season 3", "builders?"],

            # Artifacts / themes
            "JadeChest": [r"jade chest", r"ceremony of the jade chest", r"7,?777,?777"],
            "Patience": ["patience", "proof of time", "stillness", "silence"],
            "Rune3": ["rune3", "rune 3", "prophecy", "final rune"],

            # Generic TABOSHI (Leaf of Yield: ETH mint + ERC-20)
            "Taboshi": [
                "taboshi", "leaf of yield", "erc-20",
                "185,964", "0.0001111", "eth mint"
            ],

            # Numbers / mechanisms
            "777Burn": ["777", "burn"],
            "ProofOfTime": ["proof of time", r"\bpot\b", "satoby"],
        }

    def log(self, msg):
        _log(msg)

    def _match_arcs(self, query: str) -> List[str]:
        matched = []
        for arc, terms in self.priority_terms.items():
            if any(re.search(term, query, re.IGNORECASE) for term in terms):
                matched.append(arc)
        return matched

    def _score_item(self, name: str, text: str, sim: float, matched_arcs: List[str]) -> float:
        score = 0.0

        # Similarity weight (already in [0,1])
        score += sim * 8.0

        # Arc/term boosts
        for arc in matched_arcs:
            for term in self.priority_terms.get(arc, []):
                if re.search(term, name, re.IGNORECASE):
                    score += 2.5
                if re.search(term, text, re.IGNORECASE):
                    score += 3.0

        # QA bias
        if "QA" in name:
            score += 1.5

        # Recency bonus (if date present)
        dt = _extract_date_from_name(name)
        if dt:
            days = max(1.0, (_now_ymd() - dt).days)
            # More recent → slightly higher score (bounded)
            rec = max(0.0, 1.0 / math.log10(days + 9.0))  # smooth taper
            score += min(1.5, rec)

        return score

    def _mmr(self,
             q_vec: np.ndarray,
             doc_vecs: np.ndarray,
             k: int,
             lambda_mmr: float = 0.65) -> List[int]:
        """
        Maximal Marginal Relevance for diversity.
        q_vec:  (d,) normalized
        doc_vecs: (n,d) normalized
        """
        n = doc_vecs.shape[0]
        if n <= k:
            return list(range(n))
        selected = []
        candidates = list(range(n))
        sim_to_query = (doc_vecs @ q_vec)  # cosine/IP
        # first: pick best wrt query
        first = int(np.argmax(sim_to_query[candidates]))
        selected.append(candidates.pop(first))

        while candidates and len(selected) < k:
            sel_vecs = doc_vecs[selected]  # (m,d)
            # diversity = max similarity to any selected
            diversity = np.max(sel_vecs @ doc_vecs[candidates].T, axis=0)
            mmr = lambda_mmr * sim_to_query[candidates] - (1.0 - lambda_mmr) * diversity
            idx = int(np.argmax(mmr))
            selected.append(candidates.pop(idx))

        return selected

    def analyze_and_select(
        self,
        query: str,
        retrieved_scrolls: List[Union[Tuple[str, str, float], Dict[str, Any]]],
        max_keep: int = 8
    ) -> List[Tuple[str, str]]:
        """
        Returns a curated list of (name, text) with diversity and strong grounding.
        """
        tuples = _as_tuple_records(retrieved_scrolls)
        if not tuples:
            return []

        matched_arcs = self._match_arcs(query)

        # Score each item
        scored = []
        for (name, text, sim, arc) in tuples:
            s = self._score_item(name, text, sim, matched_arcs)
            scored.append((s, name, text, sim, arc))
            self.log(f"   📄 {name} | arcs:{matched_arcs if matched_arcs else None} | sim:{sim:.3f} | score:{s:.2f}")

        # Sort by score desc
        scored.sort(key=lambda x: (-x[0], -x[3], x[1]))

        # If MMR is enabled, run diversification using embeddings
        top = scored[: max(20, max_keep * 3)]  # candidate pool for MMR
        texts = [t[2] for t in top]
        names = [t[1] for t in top]

        # Embed candidates + query for MMR
        try:
            doc_vecs = self.model.encode(texts, convert_to_numpy=True)
            # normalize
            doc_vecs = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)
            q_vec = self.model.encode([query], convert_to_numpy=True)[0]
            q_vec = q_vec / np.linalg.norm(q_vec, keepdims=True)

            if self.mmr:
                sel_idx = self._mmr(q_vec, doc_vecs, k=max_keep, lambda_mmr=self.mmr_lambda)
                selected = [top[i] for i in sel_idx]
            else:
                selected = top[:max_keep]
        except Exception as e:
            # If embeddings fail for any reason, fall back to top-k
            self.log(f"⚠️ MMR fallback due to: {e}")
            selected = top[:max_keep]

        curated = [(name, text) for _, name, text, _, _ in selected]
        return curated
