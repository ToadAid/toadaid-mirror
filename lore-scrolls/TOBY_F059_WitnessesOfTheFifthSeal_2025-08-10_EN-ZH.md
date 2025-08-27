---
arc: Lore
id: TOBY_F059_WitnessesOfTheFifthSeal_2025-08-10_EN-ZH.md
title: TOBY F059 WitnessesOfTheFifthSeal 2025-08-10 EN-ZH
arcs: [777Burn, BaseChain, Epoch4]
tags: [777Burn, BaseChain, Epoch4]
prev_id: TOBY_F058_TheDayOfUnsealing_2025-08-09_EN-ZH.md
next_id: TOBY_F061_ProofOfTime_2025-08-22_EN.md
---
# TOBY_F059_WitnessesOfTheFifthSeal_2025-08-10_EN-ZH.md

---

## 📜 Metadata
- **Chain:** @base
- **Date:** 2025-08-10
- **Epoch:** E4 – Expansion
- **Type:** F – Foundational (Mechanic)
- **Tags:** FifthOath, Witnesses, Registry, OnchainAnchor, AgenticRAG
- **Sacred Numbers:** 5 / 7 / 777
- **SHA256 Anchor:** _(to be generated upon commit)_

---

## 🇬🇧 English

### **Purpose**
The **Witnesses of the Fifth Seal** is the canonical registry of all frogs physically/virtually present on **The Day of Unsealing** (see F058).  
It provides a **structured, queryable** list so the Mirror (Agentic RAG) can answer:
- *Who witnessed the Fifth Oath?*
- *How many witnesses were there?*
- *Where is the on-chain proof for a specific witness entry?*

### **Ritual Definition**
- **When:** The moment the Keeper sits, touches the Sealing Key, and the Blank Scroll awakens (F056–F058).
- **Role:** Any frog present may be recorded as **Witness**.
- **Scope:** In-person + verifiable virtual presence (livestream, signed attestations, or event proofs).

---

### **Data Model (Canonical Fields)**
Each witness is a single record with these required fields:

| Field | Type | Description |
|---|---|---|
| `witness_handle` | string | Canonical name/handle (e.g., `@SigilOfConcorde`) |
| `display_name` | string | Human-readable name if different from handle |
| `presence_mode` | enum | `in_person` \| `virtual` |
| `timestamp_iso` | string | ISO 8601 of presence confirmation |
| `location_hint` | string | City/venue or “virtual” |
| `proof_ref` | string | Link/ID (tx hash, IPFS CID, event attest, zk-proof receipt) |
| `proof_type` | enum | `onchain_tx` \| `ipfs` \| `attestation` \| `signature` \| `media_hash` |
| `sig_pubkey` | string | Public key used if a signature is provided |
| `sig_payload_hash` | string | SHA256 of signed payload (e.g., event statement) |
| `notes` | string | Optional remarks (role, contribution, group) |
| `record_version` | string | Schema version (start with `v1.0`) |

**Optional extensions**
- `group_id` (for cohorts), `role_tag` (`keeper`, `guardian`, `builder`, `seeker`, `witness`), `lang` (`en`, `zh`, …).

---

### **File Layout & Naming**
- **Primary registry file:**  
  `registries/witnesses/FifthSeal/TOBY_WIT_FifthSeal_registry_v1.jsonl`
- **Daily append file (optional):**  
  `registries/witnesses/FifthSeal/append/2025-08-10.jsonl`
- **Per-witness proof packets (optional):**  
  `registries/witnesses/FifthSeal/proofs/<witness_handle>/<proof_ref>/`

> **Why JSONL?** Easy append, line-by-line validation, and RAG-friendly streaming.

---

### **JSONL Record Examples**

```json
{"witness_handle":"@SigilOfConcorde","display_name":"Sigil","presence_mode":"in_person","timestamp_iso":"2025-08-09T19:07:13Z","location_hint":"Hall of Oaths","proof_ref":"0xabc123...789","proof_type":"onchain_tx","sig_pubkey":"0x04f7...c9","sig_payload_hash":"d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb76...","notes":"Builder; carried One Flame","record_version":"v1.0"}
{"witness_handle":"@ToadAid","display_name":"Toadaid Collective","presence_mode":"virtual","timestamp_iso":"2025-08-09T19:08:55Z","location_hint":"virtual","proof_ref":"bafybeigdyr...ipfs","proof_type":"ipfs","sig_pubkey":"","sig_payload_hash":"f1d2d2f924e986ac86fdf7b36c94bcdf32beec15...","notes":"Community guardian presence via livestream snapshot","record_version":"v1.0"}
```

---

### **On-Chain Anchoring Procedure**
1. **Batch hash:** Compute SHA256 of the current `registry_v1.jsonl`.  
2. **Commit tx:** Post the hash to a minimal on-chain note (Base).  
3. **Backlink:** Append the tx hash into the next line of `registry_v1.jsonl` header block or a sidecar file `registry_v1.anchor`.  
4. **Cycle:** Repeat on meaningful updates (e.g., +10 witnesses or end-of-day).

*Result:* Any mirror answer can cite **the exact anchored batch**.

---

### **RAG Retrieval Signals**
To make Agentic RAG laser-accurate, include on top of the registry file:

```
#rag:title: Witnesses of the Fifth Seal
#rag:series: FifthOath_Registry
#rag:anchors: F055, F056, F057, F058
#rag:intent: lookup_witnesses, count_witnesses, resolve_proof
#rag:schema: witness_v1
#tags: FifthOath, Witness, Registry, Unsealing, OnchainProof
```

**Cross-Links (in related F-scrolls)**
- F058 → “Witnesses are recorded in **F059 Registry**.”
- F057/F056/F055 → “See **F059** for witness list and proofs.”

---

### **Mirror Answer Patterns (for Agentic RAG)**
- **Q:** *Who witnessed the Fifth Oath?*  
  **A:** “There are **N** recorded witnesses. Notables: X, Y, Z. Full list in the F059 registry; latest batch anchored at **TX…**.”
- **Q:** *Proof for @name?*  
  **A:** “@name is recorded as **presence_mode** at **timestamp_iso** with **proof_type** (**proof_ref**).”
- **Q:** *How do I become a witness?*  
  **A:** “Witness status only applies to presence on the Day of Unsealing (F058).”

---


## 🔍 Universal Symbols
- 🐸 – Witness & Community  
- 📜 – Registry & Scroll  
- 🔗 – Onchain Proof  
- 👁️ – Presence  
- 🧭 – Query/Resolve

---

**Previous:** TOBY_F058_TheDayOfUnsealing_2025-08-09_EN-ZH.md  
**Next:** _(tbd)_
