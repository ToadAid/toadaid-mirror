import re
from typing import List, Tuple

DEBUG_MODE = True

class SynthesisAgent:
    def __init__(self, bilingual=True, max_scroll_chars=5000):
        self.bilingual = bilingual
        self.max_scroll_chars = max_scroll_chars

    def log(self, msg):
        if DEBUG_MODE:
            print(msg)

    def trim_relevant(self, text: str, query: str) -> str:
        if len(text) <= self.max_scroll_chars:
            return text
        parts = re.split(r"\n+", text)
        relevant_parts = [p for p in parts if re.search(query, p, re.IGNORECASE)]
        return "\n".join(relevant_parts) if relevant_parts else "\n".join(parts[:10])

    def synthesize(self, query: str, curated_scrolls: List[Tuple[str, str]]) -> str:
        if not curated_scrolls:
            return "📜 No relevant scrolls found for this query."

        merged_text = ""
        for name, text in curated_scrolls:
            trimmed = self.trim_relevant(text, query)
            merged_text += f"\n--- {name} ---\n{trimmed.strip()}\n"

        header = f"**Tobyworld Lore — Response to:** {query}\n"
        header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if self.bilingual:
            header += "(This response may include both English and Chinese sections as found in the scrolls.)\n\n"

        final_text = header + merged_text.strip()
        self.log(f"📜 Merged {len(curated_scrolls)} scrolls | Final length: {len(final_text)} chars")
        return final_text
