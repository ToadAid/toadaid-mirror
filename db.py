# db.py
import asyncpg
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

# PostgreSQL URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:yourpassword@localhost:5432/tobybot")

# Global connection pool
pool = None

# === Initialize DB and Table ===
async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            role TEXT,  -- 'user', 'bot', 'guardian', 'toby'
            message TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        );
        """)
        print("✅ PostgreSQL connected and table ensured.")

# === Insert a message ===
async def insert_conversation(user_id: str, role: str, message: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversations (user_id, role, message) VALUES ($1, $2, $3);",
                user_id, role, message
            )
    except Exception as e:
        print(f"❌ Failed to insert conversation: {e}")
