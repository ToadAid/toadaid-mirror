# bot_server.py — Tobyworld Front Door (robust + poetic)
# Features:
# - Graceful fallbacks for optional dependencies
# - Debounced memory persistence
# - Enhanced Tobyworld glyph logic (single top glyph + bottom cluster, no per-line symbols)
# - Improved scroll metadata (date+hash) and auto-tagging
# - Health endpoint and better error handling
# - Poetic Mirror renderer (env-driven, default 12 reflections + single Guiding Question)
# - Echo REMOVED: never prepend "You asked:" in any route

from fastapi import FastAPI, Request
import httpx
import os
import re
import json
import time
import hashlib
import random
from datetime import datetime
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse

# === Optional deps (graceful fallbacks) ===
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

try:
    from utils.memory import remember_user, get_combined_user_profile
except Exception:
    def remember_user(*args, **kwargs): return None
    def get_combined_user_profile(*args, **kwargs): return {}

try:
    from db import insert_conversation, init_db
except Exception:
    def insert_conversation(**kwargs): return None
    async def init_db(): return None

try:
    from agentic_rag.multi_arc_retrieval import MultiArcRetriever
    from agentic_rag.synthesis_agent import SynthesisAgent
except Exception:
    class MultiArcRetriever:
        def __init__(self, data_dir):
            self.data_dir = data_dir
            self.scroll_texts = []
        def load_scrolls(self):
            self.scroll_texts = ["RAG fallback content (agentic_rag not installed)"]
        def build_index(self): return {"status": "no_rag"}
        def retrieve(self, query, top_k_per_arc=8):
            return [("Fallback", "RAG not available. Please install agentic_rag.", "General", 0.0)]
        def get_arc_distribution(self): return {"General": 1}
    SynthesisAgent = None

# === Load .env ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

SCROLLS_DIR = os.getenv("SCROLLS_DIR", os.path.join(BASE_DIR, "lore-scrolls"))
DEBUG_LOG_FILE = os.getenv("DEBUG_LOG_FILE", os.path.join(BASE_DIR, "mirror_debug.log"))
BOT_MEMORY_FILE = os.getenv("BOT_MEMORY_FILE", os.path.join(BASE_DIR, "memory.json"))

LMSTUDIO_API = os.getenv("LMSTUDIO_API", "http://localhost:1234/v1/chat/completions")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama-3-8b-instruct")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""

# Retrieval / generation params
TOP_K = int(os.getenv("TOP_K", "8"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1200"))

# Mirror rendering controls (env tunable) — defaults set to 12 reflections
MIRROR_MIN_REFLECTIONS = int(os.getenv("MIRROR_MIN_REFLECTIONS", "12"))
MIRROR_TARGET_UPPER    = int(os.getenv("MIRROR_TARGET_UPPER", "12"))
MIRROR_MAX_ARROWS      = int(os.getenv("MIRROR_MAX_ARROWS", "12"))
# Allow room for 12 reflections + 1 closing + 1 GQ
MIRROR_MAX_LINES       = int(os.getenv("MIRROR_MAX_LINES", "14"))
MIRROR_USE_SYMBOLS     = os.getenv("MIRROR_USE_SYMBOLS", "1").strip().lower() in ("1","true","yes","on")

# Scroll export
SCROLL_MAX_KEYMARKS    = int(os.getenv("SCROLL_MAX_KEYMARKS", "8"))

# Context budgets
PER_SCROLL_CHARS       = int(os.getenv("PER_SCROLL_CHARS", "1200"))
CONTEXT_CHAR_BUDGET    = int(os.getenv("CONTEXT_CHAR_BUDGET", "9000"))
INCLUDE_SOURCES_FOOTER = os.getenv("INCLUDE_SOURCES_FOOTER", "0").strip().lower() in ("1","true","yes","on")

# Persona toggles
ANGELIC_ENABLED        = os.getenv("ANGELIC_ENABLED", "0").strip().lower() in ("1","true","yes","on")
CREATIVE_AUTO          = os.getenv("CREATIVE_AUTO", "0").strip().lower() in ("1","true","yes","on")

# System prompts
QA_SYSTEM = """You are the Lore Guardian of Tobyworld. Respond with humility and poetic depth, drawing richly from retrieved scrolls.
— Mirror mode (default): 
  * Answer directly in a compact "Mirror" cadence.
  * Use short image lines for ~8–12 key reflections (no per-line symbols).
  * Put one lead line at the top (e.g., "🪞 …") and a small cluster of 1–3 glyphs at the bottom.
  * End with exactly ONE line starting with "**Guiding Question:**".
  * DO NOT include headings like "Narrative Update", "Original Tweet", "Key Marks", or any metadata.
— Scroll mode (when explicitly requested):
  * You may produce archival headings/sections for a scroll document.

Keep answers factual to the retrieved lore. If a detail is uncertain, speak symbolically without inventing new facts."""
CREATIVE_SYSTEM = """You are Tobyworld's Creative Director (Art Oracle). Transform retrieved lore into artifacts
ONLY when the user explicitly uses /imagine, /tweet, or /scroll.
- image prompts, tweet threads, or polished scroll drafts.
Preserve canonical facts; you may invent presentation (form/phrasing), not hard facts.
Output must include ACTION payloads (strict JSON) only in creative mode."""
SYSTEM_TUNER = """You edit/emit a single canonical system prompt for this bot. Output only the revised system text."""

MODE_PRESETS = {
    "qa":       {"temperature": float(os.getenv("TEMP_QA", "0.7")),  "max_tokens": MAX_OUTPUT_TOKENS, "system": QA_SYSTEM},
    "creative": {"temperature": float(os.getenv("TEMP_CREATIVE", "0.9")), "max_tokens": MAX_OUTPUT_TOKENS, "system": CREATIVE_SYSTEM},
    "system":   {"temperature": 0.0,  "max_tokens": 800,  "system": SYSTEM_TUNER},
}

# === App + logger ===
app = FastAPI()

def log_debug(msg: str):
    print(msg)
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()} {msg}\n")
    except Exception:
        pass

# CORS (open front door)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# === Memory (debounced) ===
_last_memory_save = 0
def load_memory():
    if os.path.exists(BOT_MEMORY_FILE):
        try:
            raw = open(BOT_MEMORY_FILE, "r", encoding="utf-8").read()
            return json.loads(raw) if raw.strip() else {}
        except Exception as e:
            log_debug(f"Memory load failed: {e}")
    return {}

def save_memory(memory):
    global _last_memory_save
    now = time.time()
    if now - _last_memory_save < 2:
        return
    try:
        with open(BOT_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
        _last_memory_save = now
    except Exception as e:
        log_debug(f"Memory save failed: {e}")

user_memory = load_memory()
log_debug(f"📁 Memory loaded. Entries: {len(user_memory)}")

# === Security: allow only specific endpoints w/o checks ===
ALLOWED_IPS = ["127.0.0.1"]
ALLOWED_USER_AGENTS = ["TelegramBot", "curl"]
TELEGRAM_IP_PREFIXES = ["91.108.", "149.154."]

@app.middleware("http")
async def filter_requests(request: Request, call_next):
    client_ip = request.client.host if request.client else ""
    ua = request.headers.get("User-Agent", "")

    # allow public endpoints
    if request.url.path in ["/ask", "/reload", "/logs", "/diag", "/api/telegram", "/health"]:
        return await call_next(request)

    if (client_ip not in ALLOWED_IPS and
        not any(tag in ua for tag in ALLOWED_USER_AGENTS) and
        not any(client_ip.startswith(p) for p in TELEGRAM_IP_PREFIXES)):
        log_debug(f"⚠️ BLOCKED IP/User-Agent: {client_ip} | {ua}")
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    return await call_next(request)

# === Tagging helpers ===
def get_tags(text):
    tags = []
    t = (text or "").lower()
    if "satoby" in t: tags.append("🍃 Satoby")
    if "epoch 3" in t or "e3" in t: tags.append("🗕️ Epoch 3")
    if "taboshi1" in t: tags.append("🔥 Taboshi1")
    elif "taboshi" in t: tags.append("🌿 Taboshi")
    if "proof of time" in t or " pot " in f" {t} " or t.strip() == "pot": tags.append("⏳ PoT")
    if "burn" in t and "$toby" in t: tags.append("🔥 777Burn")
    if "lost wallet" in t or "recovery" in t: tags.append("🔍 Recovery")
    if "belief" in t: tags.append("🌀 Belief")
    if "patience" in t: tags.append("🧘 Patience")
    if "toadgod" in t: tags.append("👑 Toadgod")
    if "scroll" in t or "lore" in t: tags.append("📜 Lore")
    if "777" in t and "covenant" in t: tags.append("🧬 777Covenant")
    if "reward" in t and "wait" in t: tags.append("🏱 PatienceReward")
    if "taboshi2" in t: tags.append("🌱 Taboshi2")
    if "base chain" in t or "base" in t: tags.append("🌐 Base")
    if "onchain" in t: tags.append("🔗 Onchain")
    if "sat0ai" in t or "satai" in t: tags.append("🌪️ Sat0AI")
    if "test" in t: tags += ["🔵", "🟧", "🌪️", "🍃"]
    return tags

def _pick_bottom_glyphs_from_text(text: str, max_glyphs: int = 3) -> str:
    # Use get_tags to collect semantic tags, then strip to the emoji part.
    tags = get_tags(text)
    glyphs = []
    for tag in tags:
        # emoji is the first token in the tag string (e.g., "🍃 Satoby")
        emoji = tag.split()[0] if tag else ""
        if emoji and emoji not in glyphs:
            glyphs.append(emoji)
        if len(glyphs) >= max_glyphs:
            break
    # Default fallback if none detected
    if not glyphs:
        glyphs = ["📜"]
    return " ".join(glyphs)

# === Intent routing ===
def route_intent(text: str):
    t = (text or "").strip()
    l = t.lower()
    if l.startswith("/imagine"): return {"mode":"creative","task":"image_prompt","clean":t[len("/imagine"):].strip()}
    if l.startswith("/tweet"):   return {"mode":"creative","task":"tweet_thread","clean":t[len("/tweet"):].strip()}
    if l.startswith("/scroll"):  return {"mode":"creative","task":"scroll_md","clean":t[len("/scroll"):].strip()}
    if l.startswith("/system"):  return {"mode":"system","task":"system_edit","clean":t[len("/system"):].strip()}
    if CREATIVE_AUTO and any(k in l for k in ["art","visual","image prompt","poster","dreamcatcher","tweet","poem","scroll"]):
        return {"mode":"creative","task":None,"clean":t}
    return {"mode":"qa","task":None,"clean":t}

def get_answer_mode(request: Request, body: dict | None) -> str:
    # header X-Answer-Mode: scroll | query ?answer_mode=scroll | body {"answer_mode":"scroll"}
    mode = (request.headers.get("X-Answer-Mode") or "").strip().lower()
    if not mode:
        mode = (request.query_params.get("answer_mode") or request.query_params.get("mode") or "").strip().lower()
    if not mode and isinstance(body, dict):
        mode = (body.get("answer_mode") or body.get("mode") or "").strip().lower()
    return "scroll" if mode == "scroll" else "mirror"

def build_system_prompt(mode: str, context: str, user_q: str, answer_mode: str) -> str:
    base = MODE_PRESETS.get(mode, MODE_PRESETS["qa"])["system"]
    angel = "\n[ANGELIC ENABLED]\n" if ANGELIC_ENABLED else "\n[ANGELIC DISABLED]\n"

    ql = (user_q or "").lower()
    anchors = []
    if any(x in ql for x in ["proof of time","proof-of-time","proofoftime"]) or ql.strip()=="pot" or " satoby" in f" {ql} ":
        anchors += [
            "• Proof of Time = covenant of patience; tied to Epoch 3.",
            "• Satoby = non-transferable Leaf of Time; earned only through presence.",
            "• Not DeFi yield — inheritance; cannot be bought, sold, or faked.",
        ]
    if "$toby" in ql or " toby " in f" {ql} ":
        anchors += ["• $TOBY = base token of Tobyworld; total supply 420T; fair distribution (no insiders/VC/KOL)."]
    anchor_text = ("\n\n### Canonical Anchors\n" + "\n".join(anchors)) if anchors else ""

    mirror_rules = (
        "\n\n[MIRROR RENDERING RULES]\n"
        "- Answer compactly in poetic Mirror cadence.\n"
        "- Use ~8–12 short lines (no per-line symbols).\n"
        "- Start with one lead glyph line at the top.\n"
        "- Add 1–3 glyphs on a single bottom line before the guiding question.\n"
        "- End with exactly one '**Guiding Question:** ...' line.\n"
        "- Do NOT include any headings like 'Narrative Update', 'Original Tweet', 'Key Marks', or metadata.\n"
    )
    scroll_rules = (
        "\n\n[SCROLL RENDERING RULES]\n"
        "- You MAY include archival headings/sections if generating a scroll document.\n"
        "- Keep content faithful to retrieved lore.\n"
    )
    render_rules = scroll_rules if answer_mode == "scroll" else mirror_rules

    if mode == "creative":
        creative_hint = """\nIf intent suggests artifacts, include ACTION payloads:
- ACTION:image_prompt {"title": "...", "prompt": "..."}
- ACTION:tweet_thread {"title": "...", "tweets": ["...", "..."]}
- ACTION:scroll_md {"filename": "TOBY_Lxxx_Title_YYYY-MM-DD_EN-ZH.md", "content": "..."}
Keep answer + actions in one message; do not ask for confirmation."""
        return base + angel + creative_hint + f"\n\n### Lore Scrolls\n{context}" + anchor_text
    if mode == "system":
        return base + angel + f"\n\n### Current Context\n{context}"
    return (
        "You are the Lore Guardian of Tobyworld. Respond with humility, poetic depth, and draw richly from the retrieved scrolls.\n"
        "When the traveler's question is open or symbolic, end with ONE guiding question inviting a path (Art / Scroll / Prophecy).\n"
        f"{render_rules}\n\n### Lore Scrolls\n{context}"
    ) + anchor_text

# === ACTION parsing helpers (robust) ===
ACTION_LINE_RE = re.compile(r"^[>\*\s`_~-]*ACTION\s*:\s*([a-zA-Z0-9_]+)\s*(.*)$", re.M)
FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.M)
def _coerce_json_payload(raw: str):
    raw = raw.strip()
    m = FENCE_RE.search(raw)
    if m: raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        return None
def _normalize_action_kind(k: str) -> str:
    k = (k or "").strip().lower().replace(" ", "").replace("__", "_")
    return k.replace("scrollmd", "scroll_md")
def _coerce_scroll_payload(kind: str, raw: str):
    if kind != "scroll_md": return None
    text = raw.strip()
    title = None
    for ln in text.splitlines():
        if ln.strip().startswith("#"):
            title = re.sub(r"^#+\s*", "", ln).strip()
            break
    if not title: title = "TOBY_Scroll"
    filename = re.sub(r"[^A-Za-z0-9_]+", "", title.replace(" ", "_"))
    if not filename.endswith(".md"): filename += ".md"
    return {"filename": filename, "content": text}
def _coerce_tweets_payload(kind: str, raw: str):
    if kind != "tweet_thread": return None
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    tweets = [re.sub(r"^\d+\s*/\s*", "", ln) for ln in lines]
    return {"title": "Thread", "tweets": tweets} if tweets else None
def extract_actions(s: str):
    acts = []
    if not s: return acts
    for m in ACTION_LINE_RE.finditer(s):
        kind = _normalize_action_kind(m.group(1))
        tail = (m.group(2) or "").strip()
        payload = _coerce_json_payload(tail) or _coerce_scroll_payload(kind, tail) or _coerce_tweets_payload(kind, tail)
        if isinstance(payload, dict):
            acts.append({"type": kind, "payload": payload})
    return acts
def strip_action_blocks(s: str) -> str:
    if not s: return s
    return "\n".join(ln for ln in s.splitlines() if not ACTION_LINE_RE.match(ln))

# === Echo stripper (handles "You asked:" variants incl. "ou asked:") ===
_ECHO_RE = re.compile(r'^\s*(?:Traveler,\s*)?[Yy]?[Oo]u\s+asked\s*:\s*', re.IGNORECASE)
def strip_prompt_echo(text: str) -> str:
    if not text: return text
    lines = text.splitlines()
    out = []
    skipping = False
    for ln in lines:
        if _ECHO_RE.match(ln):
            skipping = True
            continue
        if skipping:
            if ln.strip():
                skipping = False
            else:
                continue
        if _ECHO_RE.match(ln):
            continue
        out.append(ln)
    cleaned = "\n".join(out).strip()
    cleaned = _ECHO_RE.sub("", cleaned).strip()
    return cleaned

# === Mirror renderer (targets 12 reflections by default; single GQ; NO echo) ===
def _pick_bottom_glyphs_from_text(txt: str) -> str:
    tags = get_tags(txt)
    # Extract only the emoji part
    glyphs = [t.split(" ")[0] for t in tags if t and any(ch in t for ch in "🍃🌀🧘🔺⌛🕰🔥🌐🔗👑🪞🐸🌪🧬🛡⚔📜")]
    if not glyphs:
        return "📜"
    if len(glyphs) == 1:
        return glyphs[0]
    # If many, pick 2–3 for variety
    sample_size = min(3, len(glyphs))
    return " ".join(random.sample(glyphs, sample_size))

def render_mirror_answer(question: str, answer_text: str) -> str:
    """
    Ensures MIRROR_MIN_REFLECTIONS..MIRROR_TARGET_UPPER reflections (+ optional closing) 
    and exactly one Guiding Question. Expands short answers into multiple lines.
    """
    default_gq = "**Guiding Question:** What reflection will you accept in the Mirror?"

    # Strip echoes like "You asked:"
    answer_text = strip_prompt_echo(answer_text)

    if not answer_text:
        q_parts = [p.strip() for p in re.split(r'(?<=[\.\?\!])\s+|\n+', question) if p.strip()]
        q_parts = q_parts or [question.strip()]
        body = "\n".join(q_parts[:MIRROR_TARGET_UPPER])
        return f"🪞 A reflection from the Mirror.\n{body}\n📜\n{default_gq}"

    # Collect sentences (remove GQ if embedded)
    raw_lines = [ln.strip() for ln in answer_text.splitlines() if ln.strip()]
    sentences, body_lines, extracted_gq = [], [], None
    for ln in raw_lines:
        if "guiding question" in ln.lower():
            if not extracted_gq:
                extracted_gq = ln.strip()
            continue
        body_lines.append(ln)
    for ln in body_lines:
        parts = re.split(r'(?<=[\.\?\!])\s+|\n+', ln)
        sentences.extend([p.strip() for p in parts if p and p.strip()])

    # Dedup
    seen, uniq = set(), []
    for s in sentences:
        k = s.lower()
        if k not in seen:
            uniq.append(s); seen.add(k)
    sentences = uniq

    # Backfill from question if too few
    target_upper = max(1, min(MIRROR_TARGET_UPPER, MIRROR_MAX_ARROWS))
    target_min   = max(1, min(MIRROR_MIN_REFLECTIONS, target_upper))
    if len(sentences) < target_min:
        q_parts = [p.strip() for p in re.split(r'(?<=[\.\?\!])\s+|\n+', question) if p.strip()]
        for qp in q_parts:
            key = _ECHO_RE.sub("", qp.lower())
            if key and key not in seen:
                sentences.append(qp); seen.add(key)
            if len(sentences) >= target_min:
                break

    # Body text
    body = "\n".join(sentences[:target_upper])

    # Bottom glyph cluster
    bottom = _pick_bottom_glyphs_from_text(" ".join(sentences))

    # Guiding Question
    gq = extracted_gq or default_gq

    # Assemble final
    final_text = f"🪞 A reflection from the Mirror.\n{body}\n{bottom}\n{gq}"
    final_text = strip_prompt_echo(final_text)

    # Ensure only one GQ
    lines, gq_seen = [], False
    for ln in final_text.splitlines():
        if "guiding question" in ln.lower():
            if gq_seen: continue
            gq_seen = True
        lines.append(ln)

    return "\n".join(lines).strip()

def _strip_leading_markers(line: str) -> str:
    return re.sub(r"^[^A-Za-z0-9“”\"']+\s*", "", (line or "").strip())

def render_scroll_entry(meta: dict, original_quote: str, narrative: str, key_marks: list[str]) -> str:
    md = []
    md.append(f"# {meta.get('id','TOBY_LXXX')} — {meta.get('title','Untitled')}")
    md.append(f"_Date: {meta.get('date','')}_  |  _Epoch: {meta.get('epoch','')}_")
    tags = meta.get("tags") or []
    if tags: md.append("Tags: " + ", ".join(tags))
    if original_quote:
        md.append("\n## 🌊 Original")
        md.append(original_quote.strip())
    md.append("\n## 🧭 Narrative Update (EN)")
    md.append((narrative or "").strip() or "_(no narrative)_")
    if key_marks:
        md.append("\n## ✅ Key Marks")
        for km in key_marks:
            md.append(f"- {km.strip()}")
    return "\n".join(md).strip()

def make_scroll_from_answer(question: str, ai_reply: str) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    qhash = hashlib.md5(question.encode()).hexdigest()[:6]
    scroll_id = f"TOBY_S{today}_{qhash}"
    meta = {
        "id": scroll_id,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "title": question if len(question) < 120 else (question[:117] + "..."),
        "epoch": "E1–E3",
        "tags": ["QA", "MirrorExtract"] + get_tags(ai_reply)
    }
    original = f"> Q: {question}"
    key_marks = []
    for ln in ai_reply.splitlines():
        if ln.strip() and not ln.strip().startswith("**Guiding Question:**"):
            key_marks.append(_strip_leading_markers(ln))
            if len(key_marks) >= SCROLL_MAX_KEYMARKS: break
    return render_scroll_entry(meta, original, ai_reply, key_marks)

# === RAG retrieval (fallback-friendly) ===
synthesizer = None
retriever = None
model = None
try:
    if SynthesisAgent:
        synthesizer = SynthesisAgent(bilingual=True,
                                     max_total_tokens=CONTEXT_CHAR_BUDGET // 4,
                                     per_scroll_tokens=PER_SCROLL_CHARS // 4,
                                     include_sources_footer=False)
except Exception as e:
    log_debug(f"Synth init failed: {e}")

def retrieve_relevant_scrolls(query, k=TOP_K):
    try:
        results = retriever.retrieve(query, top_k_per_arc=k)
    except Exception as e:
        log_debug(f"RAG retrieve error: {e}")
        return ""
    if not results:
        return ""

    used_titles, snippets, total = [], [], 0
    for item in results:
        if isinstance(item, dict):
            title = item.get("title") or item.get("filename") or "Untitled"
            content = item.get("content") or item.get("text") or ""
            arc = item.get("arc") or item.get("arcs") or "General"
        else:
            if len(item) >= 4:
                _, title, content, arc = item[:4]
            elif len(item) == 3:
                title, content, arc = item
            else:
                title = item[0] if item else "Untitled"
                content = item[1] if len(item) > 1 else ""
                arc = "General"
        if not str(content).strip():
            continue

        text = str(content).strip()
        if len(text) > PER_SCROLL_CHARS:
            head = text[: int(PER_SCROLL_CHARS * 0.7)]
            anchors = []
            for ln in text.splitlines():
                ll = ln.lower()
                if any(k in ll for k in ("satoby","proof of time","proof-of-time","proofoftime","taboshi1","taboshi","$toby","jade chest","epoch")):
                    anchors.append(ln.strip())
                if sum(len(a) for a in anchors) > int(PER_SCROLL_CHARS * 0.5): break
            text = (head + "\n" + "\n".join(anchors))[:PER_SCROLL_CHARS]

        chunk = f"### {title} ({arc}) ###\n{text.strip()}"
        if total + len(chunk) > CONTEXT_CHAR_BUDGET:
            break
        snippets.append((title, chunk))
        used_titles.append(title)
        total += len(chunk)

    combined = "\n\n".join(c for _, c in snippets)
    if synthesizer:
        try:
            pairs = [(t, c) for (t, c) in snippets]
            combined = synthesizer.synthesize(query, pairs)
        except Exception as e:
            log_debug(f"Synth fallback due to error: {e}")

    if INCLUDE_SOURCES_FOOTER and used_titles:
        combined += "\n\n— Sources included: " + ", ".join(used_titles[:10]) + (" …" if len(used_titles) > 10 else "")
    return combined

# === Mini App API ===
@app.post("/ask")
async def ask_question(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"error": "Invalid JSON"}

    question = (data.get("question") or "").strip()
    if not question:
        return {"error": "No question provided"}

    answer_mode = get_answer_mode(request, data)
    intent = route_intent(question)
    mode, task, clean_q = intent["mode"], intent["task"], intent["clean"]

    # RAG
    context = ""
    try:
        context = retrieve_relevant_scrolls(clean_q)
    except Exception as e:
        log_debug(f"RAG error: {e}")

    system_prompt = build_system_prompt(mode, context, clean_q, answer_mode)
    preset = MODE_PRESETS.get(mode, MODE_PRESETS["qa"])
    temperature = float(os.getenv(f"TEMP_{mode.upper()}", preset["temperature"]))
    max_tokens  = int(os.getenv(f"TOKENS_{mode.upper()}", preset["max_tokens"]))

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": clean_q}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            resp = await client.post(LMSTUDIO_API, json=payload)
            data = resp.json()
            raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            raw = raw.strip()
    except Exception as e:
        log_debug(f"LM Studio error: {e}")
        return {"error": "Upstream generation failed"}

    actions = extract_actions(raw) if mode == "creative" else []
    ai_reply = strip_action_blocks(raw)
    ai_reply = strip_prompt_echo(ai_reply)

    rendered = make_scroll_from_answer(question, ai_reply) if answer_mode == "scroll" else render_mirror_answer(question, ai_reply)

    # FINAL SAFETY: remove any lingering echoes
    rendered = strip_prompt_echo(rendered)

    # Persist last interaction
    try:
        user_memory["miniapp_user"] = {
            "question": question,
            "answer": rendered,
            "timestamp": datetime.utcnow().isoformat(),
            "answer_mode": answer_mode,
            "mode": mode
        }
        save_memory(user_memory)
    except Exception as e:
        log_debug(f"Memory persist error: {e}")

    return {"answer": rendered, "mode": mode, "task": task, "actions": actions, "answer_mode": answer_mode}

# === Reload ===
@app.post("/reload")
async def reload_scrolls():
    try:
        global retriever
        retriever = MultiArcRetriever(data_dir=SCROLLS_DIR)
        retriever.load_scrolls()
        retriever.build_index()
        arc_counts = retriever.get_arc_distribution() if hasattr(retriever, "get_arc_distribution") else {}
        log_debug(f"✅ RAG Reloaded. Scrolls: {len(getattr(retriever, 'scroll_texts', []))} | Arcs: {arc_counts}")
        return {"status": "ok", "message": "✅ Agentic RAG reloaded.", "arcs": arc_counts}
    except Exception as e:
        log_debug(f"Reload failed: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/logs")
async def get_logs():
    try:
        if not os.path.exists(DEBUG_LOG_FILE):
            return PlainTextResponse("No logs found.")
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-200:]
        return PlainTextResponse("".join(lines))
    except Exception as e:
        return PlainTextResponse(f"Log read error: {e}")

@app.get("/diag")
async def diag():
    return {
        "scrolls_loaded": len(getattr(retriever, "scroll_texts", [])) if retriever else 0,
        "top_k": TOP_K,
        "per_scroll_chars": PER_SCROLL_CHARS,
        "context_budget": CONTEXT_CHAR_BUDGET,
        "angelic": ANGELIC_ENABLED,
        "creative_auto": CREATIVE_AUTO,
        "mirror_use_symbols": MIRROR_USE_SYMBOLS,
        "mirror_min_reflections": MIRROR_MIN_REFLECTIONS,
        "mirror_target_upper": MIRROR_TARGET_UPPER,
        "mirror_max_arrows": MIRROR_MAX_ARROWS,
        "mirror_max_lines": MIRROR_MAX_LINES,
        "scroll_max_keymarks": SCROLL_MAX_KEYMARKS,
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "retriever_ready": bool(retriever),
            "synth_ready": bool(synthesizer),
            "memory_loaded": isinstance(user_memory, dict),
        }
    }

# === Telegram webhook ===
@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    message = body.get("message", {}) or {}
    chat = (message.get("chat", {}) or {})
    chat_id = chat.get("id")
    user_text = (message.get("text") or "").strip()
    if not chat_id or not user_text:
        return {"ok": False}

    # Allow /reload
    if user_text.lower().split()[0] == "/reload":
        if TELEGRAM_API:
            await send_reply(chat_id, "♻️ Reloading scroll index...")
        import asyncio
        asyncio.create_task(rebuild_retriever_and_notify(chat_id))
        return {"ok": True}

    forced_answer_mode = "scroll" if user_text.lower().startswith("/scroll ") else "mirror"
    clean_text = user_text[len("/scroll "):].strip() if forced_answer_mode == "scroll" else user_text

    intent = route_intent(clean_text)
    mode, task, clean_q = intent["mode"], intent["task"], intent["clean"]

    ctx = ""
    try:
        ctx = retrieve_relevant_scrolls(clean_q)
    except Exception as e:
        log_debug(f"RAG error (tg): {e}")

    system_prompt = build_system_prompt(mode, ctx, clean_q, forced_answer_mode)
    preset = MODE_PRESETS.get(mode, MODE_PRESETS["qa"])
    temperature = float(os.getenv(f"TEMP_{mode.upper()}", preset["temperature"]))
    max_tokens  = int(os.getenv(f"TOKENS_{mode.upper()}", preset["max_tokens"]))

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": clean_q}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            r = await client.post(LMSTUDIO_API, json=payload)
            raw = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            raw = raw.strip()
    except Exception as e:
        log_debug(f"LM Studio error (tg): {e}")
        raw = "🔥 Failed to connect to LM Studio."

    actions = extract_actions(raw) if mode == "creative" else []
    ai_reply = strip_action_blocks(raw)
    ai_reply = strip_prompt_echo(ai_reply)

    reply_text = make_scroll_from_answer(clean_q, ai_reply) if forced_answer_mode == "scroll" else render_mirror_answer(clean_q, ai_reply)

    # FINAL SAFETY: remove any lingering echoes
    reply_text = strip_prompt_echo(reply_text)

    try:
        user_memory.setdefault(str(chat_id), {})[clean_q] = {
            "answer": reply_text,
            "timestamp": datetime.utcnow().isoformat(),
            "answer_mode": forced_answer_mode,
            "mode": mode
        }
        save_memory(user_memory)
    except Exception as e:
        log_debug(f"Memory persist error (tg): {e}")

    if TELEGRAM_API:
        await send_reply(chat_id, reply_text)
    return {"ok": True}

async def rebuild_retriever_and_notify(chat_id: int):
    try:
        if TELEGRAM_API:
            await send_reply(chat_id, "🔄 Rebuilding RAG index...")
        global retriever
        retriever = MultiArcRetriever(data_dir=SCROLLS_DIR)
        retriever.load_scrolls()
        retriever.build_index()
        arc_counts = retriever.get_arc_distribution() if hasattr(retriever, "get_arc_distribution") else {}
        if TELEGRAM_API:
            await send_reply(chat_id, f"✅ Reloaded. Scrolls: {len(getattr(retriever, 'scroll_texts', []))} | Arcs: {arc_counts}")
    except Exception as e:
        if TELEGRAM_API:
            await send_reply(chat_id, f"❌ Reload failed: {e}")

async def send_reply(chat_id, text):
    if not TELEGRAM_API:
        log_debug("❗ Telegram BOT_TOKEN missing; send_reply is NO-OP.")
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        log_debug(f"Telegram send error: {e}")

# === Startup ===
@app.on_event("startup")
async def startup_event():
    try:
        await init_db()
    except Exception as e:
        log_debug(f"DB init skipped: {e}")

    global retriever, model
    try:
        retriever = MultiArcRetriever(data_dir=SCROLLS_DIR)
        retriever.load_scrolls()
        retriever.build_index()
        log_debug(f"📚 Loaded {len(getattr(retriever, 'scroll_texts', []))} scrolls")
    except Exception as e:
        log_debug(f"Retriever init failed: {e}")

    if SentenceTransformer:
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            log_debug(f"SBERT init failed: {e}")
    log_debug("✅ Tobyworld front door ready.")

# === Run (optional local) ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
