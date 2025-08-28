# Agentic RAG v2 — Developer Guide

This is the technical guide for the Tobyworld “Mirror / Lore Guardian” server. If you’re looking for the vision and philosophy, see the project’s root `README.md`.

- 🔎 **Agentic Retrieval**: multi-arc retriever with neighbor expansion and lightweight rerankers  
- 🧠 **Reasoning + Synthesis**: small agents compose context into answers  
- 📚 **Corpus-first**: `lore-scrolls/` is the canonical source of truth  
- ⚙️ **Drop-in**: FastAPI app; run with LM Studio or any OpenAI-compatible endpoint  
- 🔁 **Hot reload**: `/reload` picks up new/edited scrolls without restart

---

## Quickstart

```bash
git clone https://github.com/ToadAid/toadaid-mirror.git
cd toadaid-mirror
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn bot_server:app --host 0.0.0.0 --port 8080 --reload
```

Test it:
```bash
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/ask -H 'Content-Type: application/json'   -d '{"user":"demo","question":"What is Tobyworld?"}'
```

---

## Requirements

- Python **3.10+** (tested on 3.11)
- Text-gen endpoint: **LM Studio** (local) or any **OpenAI-compatible** API
- `faiss-cpu` for vector search (GPU optional)
- The Tobyworld corpus in `./lore-scrolls`

---

## Environment variables

Copy `.env.example` → `.env` and adjust:
```ini
LMSTUDIO_API=http://localhost:1234/v1/chat/completions   # or use LLM_API_BASE
LLM_API_BASE=                                             # OpenAI-compatible base (optional)
MODEL_NAME=meta-llama-3-8b-instruct@q4_k_m

SCROLLS_DIR=./lore-scrolls

MAX_CONCURRENCY=3
MAX_QUEUE=20
TOP_K=8
MAX_OUTPUT_TOKENS=1500
DEBUG_LOG_FILE=./mirror_debug.log
BOT_MEMORY_FILE=./memory.json

BOT_TOKEN=                                                # optional (Telegram)
DATABASE_URL=postgresql://postgres:password@localhost:5432/tobybot
```

---

## Project structure

```
.
├─ bot_server.py
├─ agentic_rag/
│  ├─ multi_arc_retrieval.py
│  ├─ retriever.py
│  ├─ reasoning_agent.py
│  ├─ synthesis_agent.py
│  ├─ rag_map.py
│  ├─ rag_bundle.py
│  ├─ canonical.py
│  └─ __init__.py
├─ utils/
│  └─ memory.py
├─ lore-scrolls/
├─ rag_indexer.py
├─ db.py
├─ requirements.txt
├─ .env.example
└─ .gitignore
```

---

## How it works

```
User → Router (/ask)
        ├─ MultiArcRetriever
        │   ├─ Build/refresh index from SCROLLS_DIR
        │   ├─ Multi-path search + neighbor expansion
        │   └─ Rerank (lightweight)
        ├─ ReasoningAgent
        └─ SynthesisAgent
```

The app scans `SCROLLS_DIR` at boot, builds a FAISS index, and caches chunk metadata. Use `/reload` after adding/editing scrolls.

---

## API

- `GET /healthz` — server status
- `POST /ask` — ask a question (`{"user": "...", "question": "..."}`)
- `POST /reload` — rebuild index from `SCROLLS_DIR`
- `GET /diag` — diagnostics (no secrets)
- `POST /api/telegram` — optional webhook if `BOT_TOKEN` is set

---

## Optional: serve a minimal miniapp

```python
# in bot_server.py
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
```
Then open `http://localhost:8080/` to use a tiny front door UI.

---

## Troubleshooting

- **Missing corpus**: ensure `SCROLLS_DIR=./lore-scrolls`
- **FAISS install**: use `faiss-cpu`; on some systems `conda` may be easier
- **Model not responding**: verify `LMSTUDIO_API`/`LLM_API_BASE` is reachable
- **Slow first call**: embedding model downloads on first run

---

## Contributing

- Keep `lore-scrolls/` as the canonical corpus  
- Use Git LFS for large media (png/jpg/pdf)  
- PRs: include a brief note on retrieval/quality impacts if you change retriever/agents
