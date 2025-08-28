import re
from typing import List, Tuple, Union, Dict, Any

DEBUG_MODE = True

def _log(msg: str):
    if DEBUG_MODE:
        print(msg)

def _estimate_tokens(s: str) -> int:
    # Rough: ~4 characters per token (English + mixed EN/ZH scrolls)
    return max(1, len(s) // 4)

def _split_paragraphs(text: str) -> List[str]:
    # Keep paragraphs meaningful; collapse long blank runs
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]

def _query_terms(query: str) -> List[str]:
    # Simple keyword extraction (lowercased words > 2 chars)
    q = re.sub(r"[^A-Za-z0-9一-龥]+", " ", query.lower())
    toks = [t for t in q.split() if len(t) > 2]
    # de-dup while preserving order
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]  # cap

def _para_score(para: str, terms: List[str]) -> float:
    if not terms:
        return 0.0
    p = para.lower()
    score = 0.0
    for t in terms:
        # weight phrase frequency lightly
        score += 1.0 * len(re.findall(rf"\b{re.escape(t)}\b", p))
    # prefer shorter, denser paragraphs
    score *= 1.0 + min(0.5, 300.0 / max(30.0, len(para)))
    return score

def _select_relevant_paragraphs(text: str, query: str, per_scroll_token_budget: int = 500) -> str:
    """
    Choose the most relevant paragraphs up to a per-scroll token budget.
    """
    parts = _split_paragraphs(text)
    if not parts:
        return text.strip()

    terms = _query_terms(query)
    scored = [( _para_score(p, terms), p ) for p in parts]
    # Sort by score desc; keep some context diversity by taking top N then clipping to budget
    scored.sort(key=lambda x: -x[0])

    out, tok = [], 0
    for sc, p in scored:
        ptoks = _estimate_tokens(p)
        if tok + ptoks > per_scroll_token_budget:
            continue
        out.append(p)
        tok += ptoks
        if tok >= per_scroll_token_budget:
            break

    # If nothing matched strongly, take the first 2–3 paragraphs as a gentle default
    if not out:
        out = parts[:3]

    return "\n\n".join(out)

class SynthesisAgent:
    def __init__(self,
                 bilingual: bool = True,
                 max_total_tokens: int = 2000,
                 per_scroll_tokens: int = 500,
                 include_sources_footer: bool = True):
        self.bilingual = bilingual
        self.max_total_tokens = max_total_tokens
        self.per_scroll_tokens = per_scroll_tokens
        self.include_sources_footer = include_sources_footer

    def log(self, msg):
        _log(msg)

    def _normalize_curated(self, curated_scrolls: List[Union[Tuple[str, str], Dict[str, Any]]]) -> List[Tuple[str, str]]:
        """
        Accepts either (name, text) tuples or dicts with "title"/"content".
        Returns list of (name, text).
        """
        out = []
        for item in curated_scrolls:
            if isinstance(item, (list, tuple)):
                if len(item) >= 2:
                    out.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict):
                name = item.get("title") or item.get("filename") or "Untitled"
                text = item.get("content") or item.get("text") or ""
                out.append((name, text))
        return out

    def synthesize(self, query: str, curated_scrolls: List[Union[Tuple[str, str], Dict[str, Any]]]) -> str:
        """
        Merge the best pieces from curated scrolls under a global token budget.
        Token-aware, relevance-trimmed, with optional bilingual note and sources footer.
        """
        items = self._normalize_curated(curated_scrolls)
        if not items:
            return "📜 No relevant scrolls found for this query."

        header = f"**Tobyworld Lore — Response to:** {query}\n"
        header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if self.bilingual:
            header += "(This response may include both English and Chinese sections as found in the scrolls.)\n\n"

        # Build body within max_total_tokens
        tokens_used = _estimate_tokens(header)
        body_chunks = []
        used_sources = []

        for name, text in items:
            if tokens_used >= self.max_total_tokens:
                break

            trimmed = _select_relevant_paragraphs(text, query, per_scroll_token_budget=self.per_scroll_tokens)
            if not trimmed.strip():
                continue

            section = f"--- {name} ---\n{trimmed.strip()}\n"
            section_tokens = _estimate_tokens(section)

            if tokens_used + section_tokens > self.max_total_tokens:
                # try to squeeze by halving the per-scroll budget once
                squeezed = _select_relevant_paragraphs(text, query, per_scroll_token_budget=max(120, self.per_scroll_tokens // 2))
                section = f"--- {name} ---\n{squeezed.strip()}\n"
                section_tokens = _estimate_tokens(section)
                if tokens_used + section_tokens > self.max_total_tokens:
                    continue  # still too big, skip

            body_chunks.append(section)
            used_sources.append(name)
            tokens_used += section_tokens

        final_text = header + "\n".join(body_chunks).strip()

        if self.include_sources_footer and used_sources:
            final_text += "\n\n— **Sources included:** " + ", ".join(used_sources)

        self.log(f"📜 Merged {len(used_sources)} scrolls | ~{tokens_used} tokens")
        return final_text
