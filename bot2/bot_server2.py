"""
🐸 Toadaid Lore Guardian Bot 2 — Public GitHub Release (No DB Version)
=====================================================================
This is the public release of the Toadaid Lore Guardian Bot 2.

🔹 Features:
- Telegram webhook handling
- Semantic search with FAISS + sentence-transformers
- In‑memory user profile tracking
- JSONL memory logging
- Lore tagging system
- LM Studio API integration

🔹 Changes from private version:
- All database features removed for public release
- No PostgreSQL dependency
- No external DB logging — memory is in JSONL + RAM only

🔐 Secrets:
- BOT_TOKEN2 must be set in `.env2`
"""

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
import httpx
import os
import faiss
import pickle
import re
import json
import sys
import hashlib
from dotenv import load_dotenv
from datetime import datetime
from sentence_transformers import SentenceTransformer
from utils.memory_bot2 import remember_user, get_combined_user_profile
import subprocess

# === Config ===
load_dotenv(dotenv_path=".env2")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN2")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
LMSTUDIO_API = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "meta-llama-3-8b-instruct"

INDEX_FILE = "rag_index_bot2.faiss"
META_FILE = "rag_meta_bot2.pkl"
SCROLLS_DIR = "../lore-scrolls"
MEMORY_FILE = "memory_dataset_bot2.jsonl"
BOT_MEMORY_FILE = "bot2_memory.json"
TOP_K = 8

app = FastAPI()
model = SentenceTransformer("all-MiniLM-L6-v2")
index = None
scroll_filenames = []
scroll_content = {}
user_memory = {}

# === IP & User-Agent restrictions for webhook ===
ALLOWED_IPS = ["127.0.0.1"]
ALLOWED_USER_AGENTS = ["TelegramBot", "curl"]
TELEGRAM_IP_PREFIXES = ["91.108.", "149.154."]

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

# === Memory handling ===
def load_memory():
    global user_memory
    try:
        with open(BOT_MEMORY_FILE, "r", encoding="utf-8") as f:
            user_memory = json.load(f)
    except FileNotFoundError:
        user_memory = {}

def save_memory():
    with open(BOT_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(user_memory, f, indent=2, ensure_ascii=False)

# === Tagging system ===
def get_tags(text):
    tags = []
    if "satoby" in text: tags.append("🍃 Satoby")
    if "epoch 3" in text or "e3" in text: tags.append("🗕️ Epoch 3")
    if "taboshi1" in text: tags.append("🔥 Taboshi1")
    elif "taboshi" in text: tags.append("🌿 Taboshi")
    if "proof of time" in text or "pot" in text: tags.append("⏳ PoT")
    if "burn" in text and "$toby" in text: tags.append("🔥 777Burn")
    if "lost wallet" in text or "recovery" in text: tags.append("🔍 Recovery")
    if "belief" in text: tags.append("🌀 Belief")
    if "patience" in text: tags.append("🧘 Patience")
    if "toadgod" in text: tags.append("👑 Toadgod")
    if "scroll" in text or "lore" in text: tags.append("📜 Lore")
    if "777" in text and "covenant" in text: tags.append("🧬 777Covenant")
    if "reward" in text and "wait" in text: tags.append("🏱 PatienceReward")
    if "taboshi2" in text: tags.append("🌱 Taboshi2")
    if "base chain" in text or "base" in text: tags.append("🌐 Base")
    if "onchain" in text: tags.append("🔗 Onchain")
    if "sat0ai" in text or "satai" in text: tags.append("🌪️ Sat0AI")
    return tags

# === RAG index loading ===
def load_rag_index():
    global index, scroll_filenames, scroll_content
    print("📦 Loading FAISS index + scrolls...")
    index = faiss.read_index(INDEX_FILE)
    with open(META_FILE, "rb") as f:
        scroll_filenames = pickle.load(f)
    scroll_content.clear()
    for fname in scroll_filenames:
        path = os.path.join(SCROLLS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                scroll_content[fname] = f.read()
        except Exception as e:
            print(f"⚠️ Could not load {fname}: {e}")

# === RAG retrieval ===
def retrieve_relevant_scrolls(query, k=TOP_K):
    query_embedding = model.encode([query])
    scores, indices = index.search(query_embedding, k)
    results = []
    total_chars = 0
    max_chars = 4000
    for i in indices[0]:
        if i < len(scroll_filenames):
            fname = scroll_filenames[i]
            if fname in scroll_content:
                scroll_text = f"### {fname} ###\n{scroll_content[fname]}"
                if total_chars + len(scroll_text) > max_chars:
                    break
                results.append(scroll_text)
                total_chars += len(scroll_text)
    return "\n\n".join(results)

# === Memory logging ===
def log_memory(user_text, ai_reply):
    combined_text = (user_text + " " + ai_reply).lower()
    messages = [{"role": "user", "content": user_text}, {"role": "assistant", "content": ai_reply}]
    tags = get_tags(combined_text)
    timestamp = datetime.utcnow().isoformat()
    unique_id = hashlib.sha256((user_text + ai_reply).encode()).hexdigest()
    entry = {"tags": tags, "messages": messages, "timestamp": timestamp, "id": unique_id}
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# === Telegram webhook ===
@app.post("/webhook")
async def telegram_webhook(req: Request):
    body = await req.json()
    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_text = message.get("text", "").strip()
    chat_type = message.get("chat", {}).get("type", "")

    # Ignore group messages unless mentioned/replied to
    if chat_type in ["group", "supergroup"]:
        if not any(bot in user_text.lower() for bot in ["@tobyworld_bot", "@lorebot", "@lore_bot"]):
            return {"ok": True}

    # Remember user profile
    user_info = message.get("from", {})
    full_name = user_info.get("first_name") or user_info.get("username") or "Unknown"
    remember_user(str(chat_id), full_name, "🐸")

    # Get relevant lore
    relevant_scrolls = retrieve_relevant_scrolls(user_text)

    # Build system prompt
    system_prompt = f"You are the Lore Guardian of Tobyworld.\n\n### Lore Scrolls\n{relevant_scrolls}"

    prompt_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
    }

    # Call LM Studio API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LMSTUDIO_API, json=prompt_payload, timeout=60)
            data = response.json()
            ai_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print("❌ LM Studio error:", str(e))
        ai_reply = "🔥 Failed to connect to LM Studio."

    # Log + save
    log_memory(user_text, ai_reply)
    save_memory()

    # Reply to Telegram
    await send_reply(chat_id, ai_reply)
    return {"ok": True}

# === Send reply helper ===
async def send_reply(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text
        })

# === Startup ===
load_rag_index()
load_memory()
