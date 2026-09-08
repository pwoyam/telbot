import aiosqlite
import datetime
from contextlib import asynccontextmanager

from config import DATABASE_PATH

@asynccontextmanager
async def get_conn():
    conn = await aiosqlite.connect(DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
        await conn.commit()
    finally:
        await conn.close()

async def init_db():
    async with get_conn() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'fa',
                joined_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id INTEGER,
                usage_date TEXT,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            )
        """)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'fa'")
        except Exception:
            pass
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")

async def upsert_user(user_id: int, username: str, first_name: str):
    async with get_conn() as conn:
        cursor = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        existing = await cursor.fetchone()
        if not existing:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, datetime.datetime.utcnow().isoformat()),
            )
        else:
            await conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, user_id),
            )

async def save_message(user_id: int, role: str, content: str):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.datetime.utcnow().isoformat()),
        )

async def get_conversation_history(user_id: int, limit: int = 10) -> list:
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT role, content 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

async def reset_user_history(user_id: int):
    async with get_conn() as conn:
        await conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

async def get_user_language(user_id: int) -> str:
    async with get_conn() as conn:
        cursor = await conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        return row["language"] if row and row["language"] else "fa"

async def set_user_language(user_id: int, lang: str):
    async with get_conn() as conn:
        cursor = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        existing = await cursor.fetchone()
        if not existing:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, language, joined_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, "", "", lang, datetime.datetime.utcnow().isoformat()),
            )
        else:
            await conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))

async def get_today_usage(user_id: int) -> int:
    today = datetime.date.today().isoformat()
    async with get_conn() as conn:
        cursor = await conn.execute(
            "SELECT message_count FROM daily_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        )
        row = await cursor.fetchone()
        return row["message_count"] if row else 0

async def increment_today_usage(user_id: int):
    today = datetime.date.today().isoformat()
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO daily_usage (user_id, usage_date, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, usage_date)
            DO UPDATE SET message_count = message_count + 1
            """,
            (user_id, today),
        )
