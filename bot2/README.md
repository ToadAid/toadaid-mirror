# 🐸 Toadaid Lore Guardian Bot 2

A Telegram bot for the Toby community.  
Retrieves Tobyworld lore from a FAISS index, maintains user memory, and responds using LM Studio.

## 🚀 Features
- Telegram Webhook powered by FastAPI
- Semantic Lore Retrieval using FAISS + Sentence Transformers
- In‑Memory User Profiles with symbolic tags
- Lore Tagging System for automatic conversation labeling
- Scroll Recording suggestions for new lore content
- LM Studio AI Integration — choose your own local LLM
- **Preloaded with official ToadAid Lore Scrolls — works out‑of‑the‑box**

## 📦 Setup

### 1. Clone the Repository
```bash
git clone https://github.com/ToadAid/toadaid-mirror.git
cd toadaid-mirror/bot2
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the example environment file:
```bash
cp .env2.example .env2
```
Edit `.env2` and add your Telegram bot token:
```env
BOT_TOKEN2=your_telegram_bot_token_here
```
⚠️ Keep `.env2` **private** — it is ignored in `.gitignore`.

### 4. Prepare Your Lore Scrolls
Bot 2 reads from the **shared** `../lore-scrolls` folder in the root of this repository.  
These official ToadAid scrolls are **already included**, so Bot 2 works out‑of‑the‑box.

To update:
- Add or replace `.md` / `.txt` files in `../lore-scrolls`.
- Rebuild the FAISS index:
```bash
python rag_indexer.py
```

📌 **No need to copy scrolls into `bot2/`** — they are shared with the main Mirror AI.

### 5. Host Your LLM in LM Studio
- Download & install [LM Studio](https://lmstudio.ai)  
- Load a **chat‑optimized** model such as:  
  - Meta LLaMA‑3 8B Instruct  
  - DeepSeek LLM 7B Chat  
- Start LM Studio API Server:  
  - Developer tab → Local Server  
  - URL: `http://localhost:1234`

### 6. Expose Your Bot to Telegram with ngrok
Telegram needs a public HTTPS URL for the webhook. Use [ngrok](https://ngrok.com/):

Start ngrok on port 8000:
```bash
ngrok http 8000
```
Example URL from ngrok:
```
https://abcd1234.ngrok.io
```

Create your Telegram webhook:
```bash
curl -F "url=<NGROK_URL>/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
```
Example:
```bash
curl -F "url=https://abcd1234.ngrok.io/webhook" https://api.telegram.org/bot1234567890:ABCDEF1234567890/setWebhook
```

Verify webhook:
```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

### 7. Run the Bot
```bash
uvicorn bot_server2:app --host 0.0.0.0 --port 8000
```

---

## 🧠 How It Works
1. User sends a Telegram message.  
2. Bot retrieves relevant lore scrolls from FAISS.  
3. LM Studio generates a lore‑based reply.  
4. Bot replies in Telegram.  
5. Memory stored in JSONL + RAM.

## 🔐 Security Notes
- Do not expose `.env2` or your bot token.  
- Keep LM Studio local unless you know the risks.  
- ngrok URLs expire — reset webhook when it changes.

## 🛠️ Advanced Users
- Replace `memory_bot2.py` with a DB backend.  
- Use bigger/smaller models in LM Studio.  
- Add custom lore tags.

## 🤝 Contributing
Pull requests welcome — follow lore style & symbolic consistency.

toadaid-mirror/                ← Main repo root
│
├── lore-scrolls/              ← Shared official scrolls (used by Mirror AI & Bot 2)
│   ├── TOBY_L001_...
│   ├── TOBY_L002_...
│   └── ...
│
├── bot2/                      ← Lore Guardian Bot 2
│   ├── bot_server2.py         ← Main bot server script (FastAPI + Telegram webhook)
│   ├── rag_indexer.py         ← Builds FAISS index from ../lore-scrolls
│   ├── requirements.txt       ← Dependencies for Bot 2
│   ├── README.md              ← Bot 2 setup + usage instructions
│   ├── .env2.example          ← Example environment config
│   │
│   └── utils/                 ← Helper scripts
│       ├── memory_bot2.py     ← In-memory user tracking for Bot 2
│
├── other-mirror-ai-files...   ← Main Mirror AI scripts, configs, and docs
│
└── README.md                  ← Main repo README

