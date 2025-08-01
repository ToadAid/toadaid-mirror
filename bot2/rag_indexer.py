"""
🐸 Toadaid Lore Guardian Bot 2 — FAISS Index Builder
====================================================
This script indexes all lore scrolls in `lore-scrolls-bot2/`
into a FAISS vector store for semantic search.

📦 What it does:
- Loads all `.md` or `.txt` scrolls
- Generates sentence embeddings using `all-MiniLM-L6-v2`
- Builds a FAISS index for fast retrieval
- Saves index to `rag_index_bot2.faiss`
- Saves metadata (filenames) to `rag_meta_bot2.pkl`

⚠️ Requirements:
- sentence-transformers
- faiss-cpu (or faiss-gpu)
- pickle (Python standard lib)

🔧 Usage:
    python rag_indexer.py
"""

import os
import faiss
import pickle
from sentence_transformers import SentenceTransformer

# === Config for BOT 2 ===
SCROLLS_DIR = "../lore-scrolls"
INDEX_FILE = "rag_index_bot2.faiss"
META_FILE = "rag_meta_bot2.pkl"

def build_index():
    # Load embedding model
    model = SentenceTransformer("all-MiniLM-L6-v2")  # Efficient + accurate

    # Prepare data
    documents = []
    metadata = []

    print("🔍 Indexing scrolls from:", SCROLLS_DIR)

    if not os.path.exists(SCROLLS_DIR):
        print(f"🚫 Scrolls folder '{SCROLLS_DIR}' not found.")
        return

    for filename in sorted(os.listdir(SCROLLS_DIR)):
        if filename.lower().endswith((".md", ".txt")):
            filepath = os.path.join(SCROLLS_DIR, filename)
            print(f"📖 Loading: {filename}")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(content)
                    metadata.append(filename)
            except UnicodeDecodeError as e:
                print(f"❌ Unicode error in {filename}: {e}")

    if not documents:
        print("🚫 No valid scrolls found. Exiting.")
        return

    # Embed all scrolls
    print("🧠 Embedding scrolls...")
    embeddings = model.encode(documents, show_progress_bar=True)

    # Build FAISS index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    # Save index + metadata
    faiss.write_index(index, INDEX_FILE)
    with open(META_FILE, "wb") as f:
        pickle.dump(metadata, f)

    print(f"✅ Successfully indexed {len(documents)} scrolls to {INDEX_FILE}")

if __name__ == "__main__":
    build_index()
