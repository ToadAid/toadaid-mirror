from fastapi import FastAPI, Request
import httpx
import os
import re
import json
import hashlib
import random
import time
from collections import OrderedDict
from datetime import datetime
from starlette.responses import JSONResponse
from db import insert_conversation, init_db
from agentic_rag.multi_arc_retrieval import MultiArcRetriever
from agentic_rag.reasoning_agent import ReasoningAgent
from agentic_rag.synthesis_agent import SynthesisAgent

# === Memory Map (User Identity Tracker) ===
MEMORY_MAP_PATH = "memory_map.json"

def load_memory_map():
    if not os.path.exists(MEMORY_MAP_PATH):
        return {"users": []}
    with open(MEMORY_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory_map(data):
    with open(MEMORY_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_user_memory(user_id):
    data = load_memory_map()
    for user in data["users"]:
        if user["id"] == user_id:
            return user
    return None

def remember_user(user_id, name, symbol, titles=None):
    data = load_memory_map()
    if get_user_memory(user_id):
        return
    data["users"].append({
        "id": user_id,
        "name": name,
        "symbol": symbol,
        "titles": titles or [],
        "introduced": datetime.utcnow().isoformat()
    })
    save_memory_map(data)

# === Config ===
TELEGRAM_TOKEN = "Token"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
LMSTUDIO_API = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "meta-llama-3-8b-instruct"
SCROLLS_DIR = "lore-scrolls"
MEMORY_FILE = "memory_dataset.jsonl"
user_memory = {}

app = FastAPI()

# === Security Settings ===
ALLOWED_IPS = ["127.0.0.1"]
ALLOWED_USER_AGENTS = ["TelegramBot", "curl"]
TELEGRAM_IP_PREFIXES = ["91.108.", "149.154."]

# === Agentic RAG Components ===
retriever = MultiArcRetriever("lore-scrolls")
reasoner = ReasoningAgent()
synthesizer = SynthesisAgent(bilingual=True)

@app.middleware("http")
async def filter_requests(request: Request, call_next):
    client_ip = request.client.host
    user_agent = request.headers.get("User-Agent", "")
    if (
        client_ip not in ALLOWED_IPS and
        not any(ua in user_agent for ua in ALLOWED_USER_AGENTS) and
        not any(client_ip.startswith(prefix) for prefix in TELEGRAM_IP_PREFIXES)
    ):
        print(f"⚠️ BLOCKED IP/User-Agent: {client_ip} | {user_agent}")
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

# === Cache ===
CACHE = OrderedDict()
CACHE_TTL = 3600
CACHE_MAX = 200

def get_cached_answer(question):
    now = time.time()
    expired = [q for q, (ts, _) in CACHE.items() if now - ts > CACHE_TTL]
    for q in expired:
        CACHE.pop(q, None)
    return CACHE.get(question.lower(), (None, None))[1]

def save_to_cache(question, answer):
    if len(CACHE) >= CACHE_MAX:
        CACHE.popitem(last=False)
    CACHE[question.lower()] = (time.time(), answer)

# === Rate limiting ===
LAST_REQUEST = {}
RATE_LIMIT_SECONDS = 5

def is_rate_limited(ip):
    now = time.time()
    last_time = LAST_REQUEST.get(ip, 0)
    if now - last_time < RATE_LIMIT_SECONDS:
        return True
    LAST_REQUEST[ip] = now
    return False

# === Core AI Query ===
async def process_lore_query(user_text: str, is_chinese: bool):
    retrieved = retriever.retrieve(user_text, top_k_per_arc=5)
    curated = reasoner.analyze_and_select(user_text, retrieved)
    relevant_scrolls = synthesizer.synthesize(user_text, curated)
    try:
        with open(os.path.join(SCROLLS_DIR, "TOBY_P100_NaturalToneRules.md"), "r", encoding="utf-8") as f:
            personality_rules = f.read()
    except:
        personality_rules = ""
    if not relevant_scrolls:
        scroll_text_for_prompt = "No direct scrolls found. Still, speak deeply from the spirit of Tobyworld lore."
    else:
        scroll_text_for_prompt = relevant_scrolls
    if is_chinese:
        system_prompt = (
            f"你是托比世界的守护者。必须用中文完整、深入地回答，不混用英文，除非明确要求。\n\n"
            f"### 调性规则\n{personality_rules}\n\n### 圣卷\n{scroll_text_for_prompt}"
        )
    else:
        system_prompt = (
            f"You are the Lore Guardian of Tobyworld. Respond only in English. "
            f"Ignore any Chinese unless explicitly asked.\n\n"
            f"### Tone Rules\n{personality_rules}\n\n### Lore Scrolls\n{scroll_text_for_prompt}"
        )
    prompt_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LMSTUDIO_API, json=prompt_payload, timeout=60)
            data = response.json()
            ai_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            ai_reply = re.sub(r"<think>.*?</think>", "", ai_reply, flags=re.DOTALL).strip()
            if not ai_reply:
                ai_reply = "🧘 The winds are silent, but I remain."
    except Exception as e:
        print("❌ LM Studio error:", str(e))
        ai_reply = "🔥 Failed to connect to LM Studio."
    symbols = get_tags(ai_reply.lower())
    if symbols:
        ai_reply += "\n\n" + " ".join(symbols)
    scroll_suggestion = suggest_scroll_creation(user_text)
    if scroll_suggestion:
        ai_reply += f"\n\n{scroll_suggestion}"
    return ai_reply

# === Mini-app endpoint ===
@app.post("/ask")
async def handle_ask(request: Request):
    data = await request.json()
    user_message = data.get("user_message") or data.get("question", "")
    client_ip = request.client.host
    if is_rate_limited(client_ip):
        return {"answer": "⏳ Please wait before asking again."}
    cached = get_cached_answer(user_message)
    if cached:
        return {"answer": cached}
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", user_message))
    ai_reply = await process_lore_query(user_message, is_chinese)
    save_to_cache(user_message, ai_reply)
    return {"answer": ai_reply}

# === Helper functions ===
def get_tags(text):
    tags = []
    if "satoby" in text: tags.append("🍃 Satoby")
    if "epoch 3" in text or "e3" in text: tags.append("🗕️ Epoch 3")
    if "taboshi1" in text: tags.append("🔥 Taboshi1")
    elif "taboshi" in text: tags.append("🌿 Taboshi")
    if "proof of time" in text: tags.append("⏳ PoT")
    if "burn" in text and "$toby" in text: tags.append("🔥 777Burn")
    if "belief" in text: tags.append("🌀 Belief")
    if "patience" in text: tags.append("🧘 Patience")
    if "toadgod" in text: tags.append("👑 Toadgod")
    if "scroll" in text: tags.append("📜 Lore")
    if "777" in text: tags.append("🧬 777Covenant")
    if "onchain" in text: tags.append("🔗 Onchain")
    if "sat0ai" in text: tags.append("🌪️ Sat0AI")
    return tags

def suggest_scroll_creation(user_text):
    if any(x in user_text.lower() for x in ["my theory", "i believe", "i think", "what if", "could it be", "let me explain"]):
        return "📜 This sounds profound... shall we record it in the Lore?"
    return None

def log_memory(user_text, ai_reply):
    combined_text = (user_text + " " + ai_reply).lower()
    tags = get_tags(combined_text)
    timestamp = datetime.utcnow().isoformat()
    unique_id = hashlib.sha256((user_text + ai_reply).encode()).hexdigest()
    entry = {
        "tags": tags,
        "messages": [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": ai_reply}
        ],
        "timestamp": timestamp,
        "id": unique_id
    }
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            if any(json.loads(line).get("id") == unique_id for line in f):
                return
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# === Telegram bot endpoint ===
@app.post("/api/telegram")
async def telegram_webhook(req: Request):
    body = await req.json()
    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text", "").strip()
    chat_type = message.get("chat", {}).get("type", "")
    client_ip = req.client.host
    bot_username_mentions = ["@LoreGuardianBot", "@Toby"]
    if chat_type in ["group", "supergroup"]:
        mentioned = any(bot_username.lower() in user_text.lower() for bot_username in bot_username_mentions)
        reply_to = message.get("reply_to_message", {})
        is_reply_to_bot = reply_to.get("from", {}).get("is_bot", False)
        if not mentioned and not is_reply_to_bot:
            return {"ok": True}
        for bot_username in bot_username_mentions:
            user_text = user_text.replace(bot_username, "").strip()
    remember_user(str(chat_id), message.get("from", {}).get("first_name", "") or message.get("from", {}).get("username", ""), "🐸")
    if not chat_id or not user_text:
        return {"ok": False}
    if is_rate_limited(client_ip):
        await send_reply(chat_id, "⏳ Please wait before asking again.")
        return {"ok": True}
    cached = get_cached_answer(user_text)
    if cached:
        await send_reply(chat_id, cached)
        return {"ok": True}
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", user_text))
    ai_reply = await process_lore_query(user_text, is_chinese)
    save_to_cache(user_text, ai_reply)
    log_memory(user_text, ai_reply)
    await insert_conversation(str(chat_id), "user", user_text)
    await insert_conversation(str(chat_id), "bot", ai_reply)
    await send_reply(chat_id, ai_reply)
    return {"ok": True}

async def send_reply(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text
        })

@app.on_event("startup")
async def startup_event():
    retriever.load_scrolls()
    retriever.build_index()
    await init_db()
