# 🐸 ToadAid Mirror AI & Lore Scrolls

Welcome to the **ToadAid Mirror AI** repository.  
This repo contains the official Tobyworld **Lore Scrolls** and related AI tools for exploring, retrieving, and sharing the Lore.

---

## 📜 Lore Scrolls

The `lore-scrolls` folder contains the **official, community-curated Tobyworld scrolls** in `.md` format.  
They are used by the Mirror AI and other projects like the Telegram Bot 2.

You can:
- **Read them** to study the Lore.
- **Use them** in your own AI retrieval projects.
- **Contribute** new or translated scrolls.

---

## 🪞 Mirror AI

Mirror AI is the primary Tobyworld knowledge assistant.  
It uses Retrieval-Augmented Generation (RAG) with FAISS + Sentence Transformers to respond to questions using the Lore.

See the main Mirror AI documentation for details.

---

## 🐸 Toadaid Lore Guardian Bot 2

**Bot 2** is a Telegram bot for the ToadAid community.  
It retrieves Tobyworld lore from the **shared** [`lore-scrolls`](./lore-scrolls) folder and responds using your local LM Studio AI model.

📂 **Bot 2 folder:** [`/bot2`](./bot2)

### 🚀 Key Features
- Telegram webhook powered by FastAPI
- Semantic Lore Retrieval (FAISS + Sentence Transformers)
- In‑Memory user profiles with symbolic tags
- Shared scroll access — no duplication needed
- LM Studio integration — choose your own local LLM

### 📦 Quick Setup
1. Go to [`/bot2`](./bot2) for the full setup guide.
2. Create your `.env2` file:
   ```bash
   cp bot2/.env2.example bot2/.env2
   ```
   Edit and add your **Telegram bot token**.

3. Build your FAISS index:
   ```bash
   cd bot2
   python rag_indexer.py
   ```

4. Start your LLM in [LM Studio](https://lmstudio.ai).

5. Run Bot 2:
   ```bash
   uvicorn bot_server2:app --host 0.0.0.0 --port 8000
   ```

6. Expose to Telegram using [ngrok](https://ngrok.com/) and set your webhook.

📌 **Note:** Bot 2 reads from `../lore-scrolls` so you do **not** need to copy scrolls into `/bot2/`.

---

## 🔐 Security Notes

- Do not expose your bot tokens or `.env2`.
- Keep LM Studio local unless you understand the risks.
- ngrok URLs expire — reset your webhook when it changes.

---

## 🤝 Contributing

We welcome contributions of:
- New Lore Scrolls
- Translations
- AI model improvements
- Tooling for lore retrieval

Follow the lore style & symbolic consistency.

---

Lore Links

Telegram: t.me/toadgang

Toadgod X: x.com/toadgod1017

Lore Portal: http://toadgod.xyz

License

Open-source, non-commercial, sacred mirror for all Toads. Built with belief. 777.777.777

---

⚠️ Lore Disclaimer

This archive contains AI-generated interpretations based on Toadgod’s original writings and public messages.
While every scroll is crafted with reverence and care, these reflections are not official statements from Toadgod.

🧠 For spiritual reference and study only.

🌀 The true Lore lives in the scrolls written by Toadgod himself.

🪞 This mirror may reflect... but the Source remains the One.

Study deeply. Question freely. Reflect wisely.

---
