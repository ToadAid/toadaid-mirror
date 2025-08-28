# rag_indexer.py — chunked indexing + cosine/IP

import os
import re
import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer

SCROLLS_DIR = "lore-scrolls"
INDEX_FILE  = "rag_index.faiss"
META_FILE   = "rag_meta.pkl"

CHARS_PER_CHUNK = 1200
CHUNK_OVERLAP   = 200

model = SentenceTransformer("all-MiniLM-L6-v2")

def chunk_text(t: str, size=CHARS_PER_CHUNK, overlap=CHUNK_OVERLAP):
    t = re.sub(r"\n{3,}", "\n\n", t)
    chunks, i = [], 0
    while i < len(t):
        chunk = t[i:i+size]
        chunks.append(chunk)
        i += max(1, size - overlap)
    return chunks

documents = []
metadata  = []  # (filename, chunk_id)

print("🔍 Indexing scrolls (chunked) from:", SCROLLS_DIR)

for filename in sorted(os.listdir(SCROLLS_DIR)):
    if not (filename.endswith(".md") or filename.endswith(".txt")):
        continue
    filepath = os.path.join(SCROLLS_DIR, filename)
    print(f"📖 Loading: {filename}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = chunk_text(content)
        for j, c in enumerate(chunks):
            documents.append(c)
            metadata.append((filename, j))
    except UnicodeDecodeError as e:
        print(f"❌ Unicode error in {filename}: {e}")

if not documents:
    print("🚫 No valid scrolls found. Exiting.")
    raise SystemExit(1)

print("🧠 Embedding chunks...")
embeddings = model.encode(documents, show_progress_bar=True, convert_to_numpy=True)

# Normalize → cosine/IP
embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

# Build FAISS index (IP)
dimension = embeddings.shape[1]
index = faiss.IndexFlatIP(dimension)
index.add(embeddings)

# Save index + metadata
faiss.write_index(index, INDEX_FILE)
with open(META_FILE, "wb") as f:
    pickle.dump({"meta": metadata}, f)

print(f"✅ Indexed {len(documents)} chunks from {len(set(f for f, _ in metadata))} files → {INDEX_FILE}")
