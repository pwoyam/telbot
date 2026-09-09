"""
Database layer with connection pooling and atomic rate limiting.
"""
import aiosqlite
import datetime
import logging
from contextlib import asynccontextmanager

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_connection: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    """Get or create the global database connection."""
    global _connection
    if _connection is None:
        _connection = await aiosqlite.connect(DATABASE_PATH)
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA synchronous=NORMAL")
        await _connection.execute("PRAGMA cache_size=-64000")
        logger.info("Database connection established")
    return _connection


@asynccontextmanager
async def get_conn():
    """
    Safe context manager for the shared singleton connection.
    Commits on success / rolls back on error, but NEVER closes the
    underlying connection (it's a long-lived singleton reused across
    the whole app's lifetime).

    IMPORTANT: Do NOT use `async with get_connection() as conn:` anywhere
    in the codebase — aiosqlite.Connection.__aexit__ calls close() on the
    connection, which would kill the shared singleton for the entire app.
    Always use either `conn = await get_connection()` (read-only queries)
    or `async with get_conn() as conn:` (writes that need commit/rollback).
    """
    conn = await get_connection()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise


async def init_db():
    """Initialize database schema with safe migrations."""
    async with get_conn() as conn:
        # Create tables
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
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT
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
        
        # جدول کاربران بلاک‌شده
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id INTEGER PRIMARY KEY,
                blocked_at TEXT,
                reason TEXT
            )
        """)
        
        # Safe migration: add language column if missing
        cursor = await conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "language" not in columns:
            try:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'fa'"
                )
                logger.info("Migration: added 'language' column to users")
            except Exception as e:
                logger.error("Migration failed: %s", e)
                raise  # Don't silently ignore migration failures
        
        # Create index for performance
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)"
        )


async def upsert_user(user_id: int, username: str, first_name: str):
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username=?, first_name=?
            """,
            (
                user_id, username, first_name,
                datetime.datetime.utcnow().isoformat(),
                username, first_name,
            ),
        )


async def save_message(user_id: int, role: str, content: str):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.datetime.utcnow().isoformat()),
        )


async def get_conversation_history(user_id: int, limit: int = 20, max_tokens: int = 3000) -> list:
    """Get conversation history with token-based truncation."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        def count_tokens(text: str) -> int:
            return len(enc.encode(text))
    except Exception:
        def count_tokens(text: str) -> int:
            return len(text) // 3
    
    async with get_conn() as conn:
        cursor = await conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
    
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    
    # Trim oldest messages if over token budget
    total = sum(count_tokens(m["content"]) + 4 for m in messages)
    while total > max_tokens and messages:
        removed = messages.pop(0)
        total -= count_tokens(removed["content"]) + 4
    
    return messages


async def reset_user_history(user_id: int):
    async with get_conn() as conn:
        await conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))


async def get_user_language(user_id: int) -> str:
    async with get_conn() as conn:
        cursor = await conn.execute(
            "SELECT language FROM users WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row["language"] if row and row["language"] else "fa"


async def set_user_language(user_id: int, lang: str):
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, language, joined_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language=?
            """,
            (user_id, lang, datetime.datetime.utcnow().isoformat(), lang),
        )


async def try_increment_usage(user_id: int, limit: int) -> tuple:
    """
    Atomic rate limit check-and-increment.
    Returns (allowed: bool, current_count: int)
    """
    today = datetime.date.today().isoformat()
    async with get_conn() as conn:
        # Try atomic increment: only succeeds if under limit
        cursor = await conn.execute(
            """
            INSERT INTO daily_usage (user_id, usage_date, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, usage_date)
            DO UPDATE SET message_count = message_count + 1
            WHERE message_count < ?
            """,
            (user_id, today, limit),
        )
        affected = cursor.rowcount
        
        # Get current count
        cursor = await conn.execute(
            "SELECT message_count FROM daily_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        )
        row = await cursor.fetchone()
        current = row["message_count"] if row else 0
        
        return affected > 0, current


# ===== مدیریت بلاک کاربران =====
async def block_user(user_id: int, reason: str = ""):
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO blocked_users (user_id, blocked_at, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET blocked_at=?, reason=?
            """,
            (
                user_id, datetime.datetime.utcnow().isoformat(), reason,
                datetime.datetime.utcnow().isoformat(), reason,
            ),
        )


async def unblock_user(user_id: int):
    async with get_conn() as conn:
        await conn.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))


async def is_user_blocked(user_id: int) -> bool:
    async with get_conn() as conn:
        cursor = await conn.execute(
            "SELECT user_id FROM blocked_users WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row is not None


async def get_blocked_users() -> list:
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT b.user_id, b.blocked_at, b.reason, u.username, u.first_name
            FROM blocked_users b
            LEFT JOIN users u ON b.user_id = u.user_id
            ORDER BY b.blocked_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
