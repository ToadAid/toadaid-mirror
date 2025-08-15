# Tobyworld Mirror Mini App — Linux / macOS Guide

A lightweight Tobyworld knowledge app with optional Agentic RAG.  
Runs on Linux and macOS directly from source code.

---

## 1. Install Requirements
```bash
sudo apt update && sudo apt install python3 python3-venv python3-pip
```
*(macOS: Use `brew install python` instead.)*

---

## 2. Clone and Setup
```bash
git clone https://github.com/ToadAid/toadaid-mirror.git
cd toadaid-mirror
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

---

## 3. Start the Server
```bash
export PYTHONPATH=$PWD:$PYTHONPATH
uvicorn backend.miniapp_server:app --host 0.0.0.0 --port 7777 --reload
```

- Open in browser: [http://localhost:7777](http://localhost:7777)

---

## 4. Environment Variables (Optional)
- `MIRROR_LOG_LEVEL` — default: `INFO`
- `MIRROR_LOG_DIR` — default: `./.logs`

---

## 📜 License
MIT License © 2025 ToadAid
