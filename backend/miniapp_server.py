import os, sys, time, json, hashlib, asyncio
from datetime import datetime
from collections import defaultdict, deque

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse  

# ---- Resource path helper (dev + PyInstaller EXE)
def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# Ensure bundled modules are importable in the EXE
RUNTIME_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RUNTIME_BASE)
sys.path.insert(0, os.path.join(RUNTIME_BASE, "agentic_rag"))

# Try to import Agentic RAG; if faiss is missing, run with RAG disabled
HAVE_RAG = True
MultiArcRetriever = None
try:
    from agentic_rag.multi_arc_retrieval import MultiArcRetriever  # requires faiss-cpu/gpu + sentence-transformers
except Exception as e:
    HAVE_RAG = False
    RAG_IMPORT_ERROR = e

# === Load .env and paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, "..", ".env"))

# --- Config: allow overrides via mirror_config.json (same folder as EXE) or env var
def _load_config():
    cfg_path = os.environ.get("MIRROR_CONFIG")
    if not cfg_path:
        cfg_path = os.path.join(os.getcwd(), "mirror_config.json")
        if not os.path.exists(cfg_path):
            cfg_path = os.path.join(BASE_DIR, "mirror_config.json")
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f), cfg_path
    except Exception as e:
        print(f"[config] Failed to read {cfg_path}: {e}")
    return {}, cfg_path

CONFIG, CONFIG_PATH = _load_config()

def _resolve_lmstudio_api():
    url = os.getenv("LMSTUDIO_URL") or CONFIG.get("lmstudio_url") or "http://127.0.0.1:1234/v1"
    url = url.rstrip("/")
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url

def resolve_scrolls_dir() -> str:
    """
    Prefer a local 'lore-scrolls' folder next to mirror.exe (current working directory).
    If it doesn't exist, create it. Otherwise, fall back to the bundled path.
    """
    # 1) If env var provided, honor it
    env_dir = os.getenv("SCROLLS_DIR", "").strip()
    if env_dir:
        try:
            os.makedirs(env_dir, exist_ok=True)
        except Exception:
            pass
        return env_dir

    # 2) Prefer local folder next to the EXE / working dir
    cwd_dir = os.path.join(os.getcwd(), "lore-scrolls")
    try:
        os.makedirs(cwd_dir, exist_ok=True)
        return cwd_dir
    except Exception:
        pass

    # 3) Fallback to bundled path (read-only in EXE temp)
    return os.path.join(BASE_DIR, "lore-scrolls")

SCROLLS_DIR       = resolve_scrolls_dir()
DEBUG_LOG_FILE    = os.getenv("DEBUG_LOG_FILE", os.path.join(os.getcwd(), "mirror_debug.log"))
BOT_MEMORY_FILE   = os.getenv("BOT_MEMORY_FILE", os.path.join(os.getcwd(), "memory.json"))
LMSTUDIO_API      = _resolve_lmstudio_api()
MODEL_NAME        = os.getenv("MODEL_NAME", "meta-llama-3-8b-instruct")

TOP_K                 = int(os.getenv("TOP_K", "8"))
MAX_OUTPUT_TOKENS     = int(os.getenv("MAX_OUTPUT_TOKENS", "1000"))
CACHE_TTL_SECONDS     = int(os.getenv("CACHE_TTL_SECONDS", "300"))
MAX_CONCURRENCY       = int(os.getenv("MAX_CONCURRENCY", "3"))
MAX_QUEUE             = int(os.getenv("MAX_QUEUE", "20"))
USER_BURST            = int(os.getenv("USER_BURST", "3"))
USER_REFILL_SECONDS   = float(os.getenv("USER_REFILL_SECONDS", "8"))
GLOBAL_LIMIT_COUNT    = int(os.getenv("GLOBAL_LIMIT_COUNT", "10"))
GLOBAL_LIMIT_WINDOW   = float(os.getenv("GLOBAL_LIMIT_WINDOW", "10"))

# --- Personal build: Busy Mode disabled entirely
BUSY_MODE = False
BUSY_MODE_UNTIL = 0.0

ALLOWLIST_IDS = set([s.strip() for s in os.getenv("ALLOWLIST_IDS", "").split(",") if s.strip()])

print("🐸 Tobyworld Mirror — Developed by ToadAid")
print("🔗 https://github.com/toadaid/Toadaid-mirror")
app = FastAPI(title="Toby Mirror Mini-App")

# --- CORS for local browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static web UI mounted at /ui (so API routes like /reload work)
WEB_DIR = resource_path("web")
os.makedirs(WEB_DIR, exist_ok=True)
app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="web")

# Redirect / to /ui/ for convenience
@app.get("/")
def root_redirect():
    return RedirectResponse(url="/ui/")

# --- Globals
retriever = None
user_memory = {}
sem = asyncio.Semaphore(MAX_CONCURRENCY)
waiters = 0
wait_lock = asyncio.Lock()
buckets = defaultdict(lambda: {"tokens": USER_BURST, "ts": time.time()})
global_window = deque()
ans_cache = {}

# === Utils ===
def log_debug(msg: str):
    print(msg)
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass

def load_memory():
    if os.path.exists(BOT_MEMORY_FILE):
        with open(BOT_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(BOT_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

user_memory = load_memory()
log_debug(f"📁 Memory loaded. Entries: {len(user_memory)}")

# --- Retrieval
def retrieve_relevant_scrolls(query: str, k: int = TOP_K) -> str:
    if not HAVE_RAG or not retriever or not hasattr(retriever, "retrieve"):
        return ""
    log_debug(f"🔎 Using SCROLLS_DIR={SCROLLS_DIR}; retriever has {len(getattr(retriever, 'scroll_texts', []))} scrolls loaded")
    results = retriever.retrieve(query, top_k_per_arc=k)
    if not results:
        log_debug("🔎 RAG results: empty")
        return ""
    out, total, cap = [], 0, 4000
    for item in results:
        if isinstance(item, dict):
            name = item.get("title") or item.get("filename") or "Untitled"
            text = item.get("content") or item.get("text") or ""
        else:
            if len(item) >= 4:
                _, name, text, _ = item[:4]
            elif len(item) == 3:
                name, text, _ = item
            else:
                name = item[0] if len(item) > 0 else "Untitled"
                text = item[1] if len(item) > 1 else ""
        chunk = f"### {name} ###\n{text}"
        if total + len(chunk) > cap:
            break
        out.append(chunk)
        total += len(chunk)
    log_debug(f"🔍 Agentic RAG returned {len(results)} items; used {len(out)}")
    return "\n\n".join(out)

# --- Rate limiting / cache
def norm_q(q: str) -> str: return " ".join(q.lower().strip().split())
def cache_get(q: str):
    key = hashlib.sha256(norm_q(q).encode()).hexdigest()
    v = ans_cache.get(key)
    if not v: return None
    if v["exp"] < time.time():
        ans_cache.pop(key, None)
        return None
    return v["data"]
def cache_set(q: str, data):
    key = hashlib.sha256(norm_q(q).encode()).hexdigest()
    ans_cache[key] = {"data": data, "exp": time.time() + CACHE_TTL_SECONDS}
def user_rate_ok(user_key: str) -> bool:
    now = time.time()
    b = buckets[user_key]
    b["tokens"] = min(USER_BURST, b["tokens"] + (now - b["ts"]) / USER_REFILL_SECONDS)
    b["ts"] = now
    if b["tokens"] < 1.0:
        return False
    b["tokens"] -= 1.0
    return True
def global_rate_ok() -> bool:
    now = time.time()
    while global_window and now - global_window[0] > GLOBAL_LIMIT_WINDOW:
        global_window.popleft()
    if len(global_window) >= GLOBAL_LIMIT_COUNT:
        return False
    global_window.append(now)
    return True

async def guarded_llm_call(fn):
    global waiters
    async with wait_lock:
        if waiters >= MAX_QUEUE:
            raise HTTPException(status_code=429, detail="Busy pond, please try again in a moment.")
        waiters += 1
    try:
        async with sem:
            return await fn()
    finally:
        async with wait_lock:
            waiters -= 1

# (PERSONAL BUILD) Removed gpu_watchdog + Busy Mode fallback

# --- Schemas
class AskRequest(BaseModel):
    question: str
    user: str | None = "miniapp_user"

# --- Routes
@app.post("/ask")
async def ask_question(req: AskRequest):
    user_key = req.user or "miniapp_user"
    if ALLOWLIST_IDS and user_key not in ALLOWLIST_IDS:
        return {"error": "Closed beta access. Ask an admin to be allowlisted."}
    q = (req.question or "").strip()
    if not q:
        return {"error": "No question provided"}

    if not user_rate_ok(user_key):
        return JSONResponse(status_code=429, content={"error": "Rate limit: slow down a little."})
    if not global_rate_ok():
        return JSONResponse(status_code=429, content={"error": "The pond is busy. Please try again shortly."})

    log_debug(f"🌐 MiniApp Ask: {q}")
    cached = cache_get(q)
    if cached:
        log_debug("🗄️ MiniApp cache hit")
        return {"answer": cached}

    relevant_scrolls = retrieve_relevant_scrolls(q)

    # (PERSONAL BUILD) Always full-generation; no Busy Mode light reply

    rag_note = ""
    if not HAVE_RAG:
        rag_note = "\n\n[Note: RAG is disabled (FAISS/SentenceTransformers not installed). Answering from model only.]"

    system_prompt = (
        "You are the Lore Guardian of Tobyworld. "
        "Respond with humility, poetic depth, and draw richly from the retrieved scrolls.\n\n"
        f"### Lore Scrolls\n{relevant_scrolls}{rag_note}"
    )
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": q},
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.7,
    }

    async def llm():
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            r = await client.post(LMSTUDIO_API, json=payload)
            data = r.json()
            return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""

    try:
        ai_reply = (await guarded_llm_call(llm)).strip()
        log_debug(f"📜 MiniApp Output:\n{ai_reply}")
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        log_debug(f"❌ LM Studio error: {e}")
        return {"error": "Failed to connect to LM Studio."}

    user_memory[user_key] = {"question": q, "answer": ai_reply, "timestamp": datetime.utcnow().isoformat()}
    save_memory(user_memory)
    cache_set(q, ai_reply)
    return {"answer": ai_reply}

@app.post("/reload")
async def reload_scrolls():
    if not HAVE_RAG:
        return {"status": "error", "message": f"RAG disabled: {RAG_IMPORT_ERROR}. Install 'faiss-cpu' and 'sentence-transformers' and restart."}
    try:
        global retriever
        retriever = MultiArcRetriever(data_dir=SCROLLS_DIR)
        retriever.load_scrolls()
        retriever.build_index()
        arc_counts = getattr(retriever, "get_arc_distribution", lambda: {})()
        log_debug(f"✅ MiniApp Reloaded. Scrolls: {len(getattr(retriever, 'scroll_texts', []))} | Arcs: {arc_counts}")
        return {"status": "ok", "message": "✅ Agentic RAG reloaded.", "arcs": {k: int(v) for k, v in (arc_counts or {}).items()}}
    except Exception as e:
        log_debug(f"❌ MiniApp reload failed: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/logs")
async def get_logs():
    if not os.path.exists(DEBUG_LOG_FILE):
        return PlainTextResponse("No logs found.")
    with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-200:]
    return PlainTextResponse("".join(lines))

@app.get("/healthz")
async def healthz():
    ok = True
    issues = []
    try:
        _ = len(getattr(retriever, 'scroll_texts', [])) if retriever else 0
    except Exception as e:
        ok = False
        issues.append(f"retriever:{e}")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
            await client.get(LMSTUDIO_API.replace("/v1/chat/completions", "/"), timeout=3)
    except Exception:
        issues.append("lmstudio:unreachable")
    if not HAVE_RAG:
        issues.append("rag:disabled(faiss-or-sentencetransformers-not-installed)")
    return {"ok": ok, "busy": False, "queue": waiters, "issues": issues, "scrolls_dir": SCROLLS_DIR}

@app.get("/diag")
async def diag():
    return {
        "busy_mode": False,
        "busy_until": 0.0,
        "queue": waiters,
        "semaphore": MAX_CONCURRENCY,
        "user_burst": USER_BURST,
        "user_refill_seconds": USER_REFILL_SECONDS,
        "global_rate": {"count": len(global_window), "window_sec": GLOBAL_LIMIT_WINDOW},
        "cache_size": len(ans_cache),
        "scrolls_loaded": len(getattr(retriever, 'scroll_texts', [])) if retriever else 0,
        "rag_enabled": HAVE_RAG,
        "scrolls_dir": SCROLLS_DIR
    }

@app.get("/api/config")
async def get_config():
    return {
        "config_path": CONFIG_PATH,
        "lmstudio_api": LMSTUDIO_API,
        "raw_config": CONFIG,
        "env_override": os.getenv("LMSTUDIO_URL", None),
    }

class ConfigUpdate(BaseModel):
    lmstudio_url: str | None = None

@app.post("/api/config")
async def set_config(update: ConfigUpdate):
    global CONFIG, LMSTUDIO_API
    if update.lmstudio_url:
        CONFIG["lmstudio_url"] = update.lmstudio_url
        path = CONFIG_PATH or os.path.join(os.getcwd(), "mirror_config.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(CONFIG, f, indent=2)
        except Exception as e:
            return {"status": "error", "message": f"Failed to save config: {e}"}
        LMSTUDIO_API = _resolve_lmstudio_api()
        return {"status": "ok", "lmstudio_api": LMSTUDIO_API, "config_path": path}
    return {"status": "no_change", "message": "No fields provided."}

# --- Startup
@app.on_event("startup")
async def startup_event():
    log_debug(f"🚀 Startup CWD={os.getcwd()} | SCROLLS_DIR={SCROLLS_DIR}")
    global retriever
    if HAVE_RAG:
        try:
            retriever = MultiArcRetriever(data_dir=SCROLLS_DIR)
            retriever.load_scrolls()
            retriever.build_index()
            log_debug(f"📚 Loaded {len(getattr(retriever, 'scroll_texts', []))} scrolls")
            log_debug("✅ Agentic RAG retriever initialized.")
        except Exception as e:
            log_debug(f"❌ RAG init failed: {e}")
    else:
        log_debug(f"⚠️ RAG disabled: {RAG_IMPORT_ERROR}. Install 'faiss-cpu' + 'sentence-transformers' to enable retrieval.")
    # (PERSONAL BUILD) Busy watchdog is disabled
    # asyncio.create_task(gpu_watchdog())

if __name__ == "__main__":
    import os, uvicorn
    os.environ.setdefault("UVICORN_NO_COLOR", "1") 

    port = int(os.getenv("PORT", "777"))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        loop="asyncio",
        lifespan="on",
        workers=1,
        reload=False,
        log_config=None,     
        access_log=False    
    )

