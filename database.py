import sqlite3
import datetime
from contextlib import contextmanager

from config import DATABASE_PATH

@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'fa',
                joined_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id INTEGER,
                usage_date TEXT,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            )
        """)
        # اضافه کردن ستون language به users اگر از قبل موجود نیست
        try:
            conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'fa'")
        except sqlite3.OperationalError:
            pass  # ستون از قبل وجود دارد
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")

def upsert_user(user_id: int, username: str, first_name: str):
    with get_conn() as conn:
        existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, datetime.datetime.utcnow().isoformat()),
            )
        else:
            conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, user_id),
            )

def save_message(user_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.datetime.utcnow().isoformat()),
        )

def get_user_messages(user_id: int, limit: int = 50):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT role, content, created_at 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

def get_conversation_history(user_id: int, limit: int = 10) -> list[dict]:
    """گرفتن تاریخچه مکالمه از دیتابیس (به ترتیب زمانی)"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        # برعکس کردن چون DESC گرفتیم
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

def reset_user_history(user_id: int):
    """پاک کردن کامل تاریخچه مکالمه کاربر"""
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

def get_user_language(user_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row["language"] if row and row["language"] else "fa"

def set_user_language(user_id: int, lang: str):
    with get_conn() as conn:
        existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, language, joined_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, "", "", lang, datetime.datetime.utcnow().isoformat()),
            )
        else:
            conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))

def get_today_usage(user_id: int) -> int:
    today = datetime.date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT message_count FROM daily_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        return row["message_count"] if row else 0

def increment_today_usage(user_id: int):
    today = datetime.date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO daily_usage (user_id, usage_date, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, usage_date)
            DO UPDATE SET message_count = message_count + 1
            """,
            (user_id, today),
        )
