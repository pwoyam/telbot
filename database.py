"""
مدیریت دیتابیس با sqlite3
جدول‌ها: users, payments, daily_usage, settings
"""
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
                joined_at TEXT,
                is_subscribed INTEGER DEFAULT 0,
                subscription_expires_at TEXT,
                custom_free_messages INTEGER DEFAULT NULL
            )
        """)

        # برای دیتابیس‌های قدیمی
        try:
            conn.execute("ALTER TABLE users ADD COLUMN custom_free_messages INTEGER DEFAULT NULL")
        except sqlite3.OperationalError:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                authority TEXT,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                verified_at TEXT
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('free_daily_messages', '5')
        """)


# ---------------- توابع تنظیمات ----------------

def get_setting(key: str, default: str = None) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
            (key, value, value),
        )


def get_free_daily_messages_global() -> int:
    return int(get_setting("free_daily_messages", "5"))


def get_user_free_limit(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT custom_free_messages FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row and row["custom_free_messages"] is not None:
            return row["custom_free_messages"]
    return get_free_daily_messages_global()


def set_user_custom_free_messages(user_id: int, limit: int | None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET custom_free_messages=? WHERE user_id=?",
            (limit, user_id),
        )


# ---------------- توابع کاربران ----------------

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


def is_user_subscribed(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_subscribed, subscription_expires_at FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row or not row["is_subscribed"]:
            return False
        expires_at = row["subscription_expires_at"]
        if expires_at and datetime.datetime.fromisoformat(expires_at) < datetime.datetime.utcnow():
            conn.execute("UPDATE users SET is_subscribed=0 WHERE user_id=?", (user_id,))
            return False
        return True


def activate_subscription(user_id: int, days: int):
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET is_subscribed=1, subscription_expires_at=? WHERE user_id=?",
            (expires_at.isoformat(), user_id),
        )


def deactivate_subscription(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET is_subscribed=0, subscription_expires_at=NULL WHERE user_id=?",
            (user_id,),
        )


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def get_all_users(limit: int = 100, offset: int = 0, search: str = None, only_subscribed: bool = False):
    with get_conn() as conn:
        query = "SELECT * FROM users WHERE 1=1"
        params = []

        if search:
            query += " AND (CAST(user_id AS TEXT) LIKE ? OR username LIKE ? OR first_name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        if only_subscribed:
            query += " AND is_subscribed = 1"

        query += " ORDER BY joined_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        return conn.execute(query, params).fetchall()


def get_user_ids_for_broadcast(only_subscribed: bool = False) -> list[int]:
    with get_conn() as conn:
        if only_subscribed:
            rows = conn.execute("SELECT user_id FROM users WHERE is_subscribed=1").fetchall()
        else:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


# ---------------- توابع پرداخت ----------------

def create_payment(user_id: int, authority: str, amount: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO payments (user_id, authority, amount, created_at) VALUES (?, ?, ?, ?)",
            (user_id, authority, amount, datetime.datetime.utcnow().isoformat()),
        )


def mark_payment_verified(authority: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE payments SET status='verified', verified_at=? WHERE authority=?",
            (datetime.datetime.utcnow().isoformat(), authority),
        )


def get_payment_by_authority(authority: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM payments WHERE authority=?", (authority,)).fetchone()


def get_payments(limit: int = 50):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM payments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ---------------- توابع مصرف روزانه ----------------

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


# ---------------- آمار ----------------

def get_stats():
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        active_subs = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE is_subscribed=1"
        ).fetchone()["c"]

        today = datetime.date.today().isoformat()
        today_messages = conn.execute(
            "SELECT SUM(message_count) as s FROM daily_usage WHERE usage_date=?", (today,)
        ).fetchone()["s"] or 0

        total_revenue = conn.execute(
            "SELECT SUM(amount) as s FROM payments WHERE status='verified'"
        ).fetchone()["s"] or 0

        today_revenue = conn.execute(
            "SELECT SUM(amount) as s FROM payments WHERE status='verified' AND date(verified_at)=?",
            (today,),
        ).fetchone()["s"] or 0

        return {
            "total_users": total_users,
            "active_subs": active_subs,
            "today_messages": today_messages,
            "total_revenue": total_revenue,
            "today_revenue": today_revenue,
        }

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