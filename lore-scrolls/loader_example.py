#!/usr/bin/env python3
import os, json, re

BASE = os.path.dirname(__file__)
MANIFEST = os.path.join(BASE, "manifest.json")

def read_manifest(path=MANIFEST):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_docs(m):
    docs = []
    for fn in m["files"]:
        p = os.path.join(BASE, fn)
        with open(p, "r", encoding="utf-8") as f:
            docs.append((fn, f.read()))
    return docs

def split_into_chunks(text, chunk_chars=6000, overlap_chars=600):
    # Simple char-based chunker (token-agnostic); use your tokenizer in production.
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_chars)
        chunks.append(text[start:end])
        start = max(start + chunk_chars - overlap_chars, end)
    return chunks

def heading_aware_chunks(text, pattern=r"^#\s+LG-\d+", chunk_chars=6000, overlap_chars=600):
    # Keep LG sections intact; then sub-chunk if necessary.
    blocks = re.split(pattern, text, flags=re.M)
    heads = re.findall(pattern, text, flags=re.M)
    # Re-attach headings
    sections = []
    for i, block in enumerate(blocks):
        if not block and i == 0:  # leading split before first heading
            continue
        head = heads[i-1] if i > 0 else ""
        sec = (head + "\n" + block).strip()
        if not sec:
            continue
        if len(sec) <= chunk_chars:
            sections.append(sec)
        else:
            sections.extend(split_into_chunks(sec, chunk_chars, overlap_chars))
    return sections

if __name__ == "__main__":
    m = read_manifest()
    docs = load_docs(m)
    total_chunks = 0
    for fn, text in docs:
        sections = heading_aware_chunks(text)
        total_chunks += len(sections)
        print(f"{fn}: {len(sections)} chunks")
    print(f"Total chunks: {total_chunks}")
