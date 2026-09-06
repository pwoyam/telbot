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