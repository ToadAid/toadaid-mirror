# agentic_rag/canonical.py
import re

# ==== Canonical constants ====
TOBY_CONTRACT         = "0xb8D98a102b0079B69FFbc760C8d857A31653e56e"
TOBY_TOTAL_SUPPLY     = "420,000,000,000,000"  # 420 trillion

TABOSHI1_CONTRACT     = "0x5c0bf08936bcCfbb6af24B4648A9fb365cAa2F4e"
TABOSHI1_TOTAL_SUPPLY = "492,108,551"   # ERC-1155, 777 $TOBY burn mints

TABOSHI_CONTRACT      = "0x3A1a33cf4553Db61F0db2c1e1721CD480b02789f"
TABOSHI_TOTAL_SUPPLY  = "185,964"       # ERC-1155 + ERC-20

PATIENCE_CONTRACT     = "0x6d96f18f00b815b2109a3766e79f6a7ad7785624"
PATIENCE_TOTAL_SUPPLY = "7,777,777"

def _has(pattern: str, q: str) -> bool:
    return re.search(pattern, q) is not None

def canonical_shortcut(question: str) -> str | None:
    q = (question or "").strip().lower()

    # ========= crisp definitional intents =========
    if _has(r"\btaboshi\s*(?:v?1|i|one)\b", q):
        return ("Taboshi1 is an ERC-1155 NFT minted on Zora near the end of Epoch 2 by burning 777 $TOBY per mint. "
                "It’s a proof-of-sacrifice that unlocked Satoby eligibility via Proof of Time in Epoch 3. "
                "It is not an ERC-20 and is different from TABOSHI (which had a small ETH mint). "
                "For Satoby, eligibility is tied to the original minter wallet (non-transferable even if the NFT moves).")

    if _has(r"\btaboshi\b", q) and not _has(r"\b(v?1|i|one)\b", q):
        return ("TABOSHI is the 'Leaf of Yield' — an ERC-1155 + ERC-20 token with total supply 185,964. "
                "It was minted with a small ETH cost (~0.0001111 ETH). Distinct from Taboshi1, which required burning 777 $TOBY.")

    if "tobyworld" in q or _has(r"\btoby\s*world\b", q):
        return ("Tobyworld is the living lore and people-powered project of $TOBY on Base — a mirror of belief, patience, and presence — "
                "organized through epochs and scrolls to onboard the masses while guarding decentralization.")

    if "leaf of yield" in q:
        return ("“Leaf of Yield” refers to TABOSHI — the sprouting of yield/potential in Tobyworld. "
                "It symbolizes growth-through-time, not instant reward.")

    # ========= static supplies =========
    if "total supply" in q:
        if "$toby" in q or "toby token" in q or ("toby" in q and "taboshi" not in q):
            return f"$TOBY total supply is {TOBY_TOTAL_SUPPLY}."
        if "taboshi1" in q or _has(r"\btaboshi\s*(v?1|i|one)\b", q):
            return f"Taboshi1 total supply is {TABOSHI1_TOTAL_SUPPLY}."
        if "taboshi" in q and not _has(r"\b(v?1|i|one)\b", q):
            return f"TABOSHI has a fixed total supply of {TABOSHI_TOTAL_SUPPLY}."
        if "patience" in q or "$patience" in q:
            return f"$PATIENCE has a total supply of {PATIENCE_TOTAL_SUPPLY}."

    # ========= contract addresses =========
    if "contract" in q or "address" in q:
        if "$toby" in q or ("toby" in q and "taboshi" not in q):
            return f"$TOBY contract (Base): {TOBY_CONTRACT}"
        if "taboshi1" in q or _has(r"\btaboshi\s*(v?1|i|one)\b", q):
            return f"Taboshi1 contract: {TABOSHI1_CONTRACT} (ERC-1155, total supply {TABOSHI1_TOTAL_SUPPLY})."
        if "taboshi" in q and not _has(r"\b(v?1|i|one)\b", q):
            return f"TABOSHI contract: {TABOSHI_CONTRACT} (ERC-1155 + ERC-20, total supply {TABOSHI_TOTAL_SUPPLY})."
        if "patience" in q or "$patience" in q:
            return f"$PATIENCE contract: {PATIENCE_CONTRACT} (total supply {PATIENCE_TOTAL_SUPPLY})."

    # ========= guards / safety =========
    if "fallen frogs" in q and ("how many" in q or "names" in q or "who" in q):
        return "The scrolls do not specify that."
    if "fallen frogs" in q and "how many" in q:
        return "The scrolls do not specify a fixed count."
    if "recover" in q and "taboshi" in q:
        return ("Recovery depends on your custody and on-chain proofs. If the NFT is transferred, PoT/Satoby eligibility remains "
                "with the original minter wallet. Verify wallet history before action.")

    return None
