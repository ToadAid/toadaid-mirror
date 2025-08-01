"""
🐸 memory_bot2.py — Separate memory handler for Toadaid Bot 2
=============================================================
Stores in‑memory user profiles for Bot 2 sessions.

This simple in‑memory store keeps:
- User name
- User symbol (emoji identifier)

⚠️ Data is NOT persistent across restarts.
If persistence is needed, connect to a database or file‑based storage.
"""

# In-memory store for Bot 2 users
memory_db_bot2 = {}

def remember_user(chat_id: str, full_name: str, symbol: str = "🐸"):
    """
    Store or update a user's profile in memory.

    Args:
        chat_id (str): Unique chat/session identifier.
        full_name (str): User's display name.
        symbol (str): Optional emoji identifier (default 🐸).
    """
    memory_db_bot2[chat_id] = {
        "name": full_name,
        "symbol": symbol
    }

def get_combined_user_profile(chat_id: str):
    """
    Retrieve a user's stored profile from memory.

    Args:
        chat_id (str): Unique chat/session identifier.

    Returns:
        dict: Stored profile or default placeholder if not found.
    """
    return memory_db_bot2.get(chat_id, {"name": "Unknown", "symbol": "🐸"})
