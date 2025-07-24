ToadAid Mirror Project

---

Overview

Welcome to the ToadAid Mirror Project — a gift to the believers.

This repository helps you build your own Lore-powered AI assistant using AnythingLLM with a local LLM backend (Ollama or LM Studio).

You’ll be able to:

Query the Tobyworld Lore

Reflect on deep philosophy like Proof of Time

Contribute your own scrolls

Help new Toads understand the deeper meaning

---

Requirements

Local machine (Windows / macOS / Linux)

At least 2GB RAM (8GB+ recommended)

AnythingLLM Desktop (recommended)

Ollama or LM Studio

Recommended models: deepseek-coder, phi-2, llama3, or mistral

Python 3.10+ (if using CLI)

Docker (optional but useful)

---

File Structure

mirror-project/
│
├── lore-scrolls/            # All structured scrolls (.md)
│   ├── TOBY_L###_*.md       # Lore files
│   ├── TOBY_QA###_*.md      # QA files
│   ├── TOBY_F###_*.md       # Fact files
│   └── TOBY_P000_Principles.md
│
├── mirror-template/         # Pre-built AnythingLLM structure
│
└── README.md

---

Quick Start (AnythingLLM Desktop)

1. Clone the repo

git clone https://github.com/ToadAid/mirror-project.git
cd mirror-project

2. Install AnythingLLM Desktop

Download from: https://github.com/Mintplex-Labs/anything-llm/releases

Unzip and open the desktop app.

3. Run a local model (Ollama / LM Studio)


Ollama:

ollama run llama3

LM Studio:

Launch LM Studio

Load a model (e.g. mistral, deepseek)

Enable Local Server API on port 1234


4. Add the scrolls


Inside AnythingLLM:

Create a new workspace

Upload everything inside lore-scrolls/

Run embeddings (select all-MiniLM-L6-v2 for best performance)


5. Chat with your Mirror


Ask questions like:

“What is Taboshi?”

“What does Proof of Time mean?”

“Who is the Toadgod?”

“What is the Sacred Number 777?”


---

Contribute Scrolls

To add your own lore:

1. Follow the naming format:
TOBY_L###_YourTitle_YYYY-MM-DD_EN.md


2. Use structured sections:

Metadata

Poetic Narrative

Key Marks

Oracles

Operations

Symbols

Anchors


3. Make a pull request or fork this repo.


---

Lore Links

Telegram: t.me/toadgang

Toadgod X: x.com/toadgod1017

Lore Portal: http://toadgod.xyz


---

License

Open-source, non-commercial, sacred mirror for all Toads.
Built with belief. 777.777.777


---

⚠️ Lore Disclaimer

    This archive contains AI-generated interpretations based on Toadgod’s original writings and public messages.
    While every scroll is crafted with reverence and care, these reflections are not official statements from Toadgod.

    🧠 For spiritual reference and study only.

    🌀 The true Lore lives in the scrolls written by Toadgod himself.

    🪞 This mirror may reflect... but the Source remains the One.

    Study deeply. Question freely. Reflect wisely.

    ---
