import re
from typing import List, Tuple

DEBUG_MODE = True

class ReasoningAgent:
    def __init__(self):
        # Unified arc alias mapping (matches agentic_rag.py)
        self.priority_terms = {
            "Season0": ["season 0", "season zero", "jade chest", r"pati?ence"],
            "Season1": ["season 1", "lp guardians?"],
            "Season2": ["season 2", "artists?"],
            "Season3": ["season 3", "builders?"],
            "JadeChest": ["jade chest", "ceremony of the jade chest", r"7,?777,?777"],
            "Patience": ["patience", "proof of time"],
            "Rune3": ["rune3", "rune 3", "prophecy"],
        }

    def log(self, msg):
        if DEBUG_MODE:
            print(msg)

    def analyze_and_select(
        self,
        query: str,
        retrieved_scrolls: List[Tuple[str, str, float]],
        max_keep: int = 8
    ):
        """
        Selects the most relevant scrolls based on:
        - Arc keyword matches in query
        - Arc keyword matches in scroll text
        - FAISS vector similarity (lower distance = higher score)
        """
        matched_arcs = []
        for arc, terms in self.priority_terms.items():
            if any(re.search(term, query, re.IGNORECASE) for term in terms):
                matched_arcs.append(arc)

        scored = []
        for name, text, dist in retrieved_scrolls:
            score = 0

            # Arc name match
            if any(arc.lower() in name.lower() for arc in matched_arcs):
                score += 5

            # Term matches inside text
            for arc in matched_arcs:
                for term in self.priority_terms.get(arc, []):
                    if re.search(term, text, re.IGNORECASE):
                        score += 3

            # Slight bonus for QA scrolls
            if "QA" in name:
                score += 1

            # FAISS similarity: normalize and weight
            similarity_score = max(0.0, 1.0 - (dist / 10.0))  # normalize 0–1
            score += similarity_score * 8.0  # higher weight for relevance

            scored.append((score, name, text, dist))
            self.log(f"   📄 {name} | arcs: {matched_arcs if matched_arcs else None} | score: {score:.2f} | dist: {dist:.4f}")

        # Sort: score desc, then name asc
        scored.sort(key=lambda x: (-x[0], x[1]))

        # Keep only the best
        top_scrolls = [(name, text) for score, name, text, dist in scored[:max_keep]]
        return top_scrolls
