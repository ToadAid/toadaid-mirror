# memory.py — handles user memory

memory_db = {}

def remember_user(chat_id: str, full_name: str, symbol: str = "🐸"):
    memory_db[chat_id] = {
        "name": full_name,
        "symbol": symbol
    }

def get_combined_user_profile(chat_id: str):
    return memory_db.get(chat_id, {"name": "Unknown", "symbol": "🐸"})
