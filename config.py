import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_USER_IDS = [
    int(uid.strip()) for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()
]

AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30.0"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))

DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")
PROXY_URL = os.getenv("PROXY_URL", "")

DAILY_MESSAGE_LIMIT = int(os.getenv("DAILY_MESSAGE_LIMIT", "50"))

USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache_database.db")
CACHE_TTL_AI = int(os.getenv("CACHE_TTL_AI", "3600"))
CACHE_TTL_SEARCH = int(os.getenv("CACHE_TTL_SEARCH", "900"))
CACHE_MAX_ENTRIES = int(os.getenv("CACHE_MAX_ENTRIES", "1000"))

HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9090"))  # Changed from 8080 (already in use)
HEALTH_HOST = os.getenv("HEALTH_HOST", "0.0.0.0")

STRUCTURED_LOGGING = os.getenv("STRUCTURED_LOGGING", "false").lower() == "true"

# Admin Panel
ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "8081"))
ADMIN_PANEL_HOST = os.getenv("ADMIN_PANEL_HOST", "0.0.0.0")
ADMIN_PANEL_USERNAME = os.getenv("ADMIN_PANEL_USERNAME", "admin")
ADMIN_PANEL_PASSWORD = os.getenv("ADMIN_PANEL_PASSWORD", "")

SUPPORTED_PROVIDERS = {"openai", "anthropic", "deepseek"}


def validate_config():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not AI_API_KEY:
        missing.append("AI_API_KEY")
    if AI_PROVIDER not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Invalid AI_PROVIDER '{AI_PROVIDER}'. Must be one of: {SUPPORTED_PROVIDERS}"
        )
    if USE_WEBHOOK:
        if not WEBHOOK_URL:
            missing.append("WEBHOOK_URL (required when USE_WEBHOOK=true)")
        if not WEBHOOK_SECRET:
            missing.append("WEBHOOK_SECRET (required when USE_WEBHOOK=true)")
    # نکته: پنل ادمین وب (ADMIN_PANEL_*) در این نسخه از کد پیاده‌سازی نشده؛
    # پنل ادمین فعلی از طریق دستور تلگرام /admin کار می‌کند و نیازی به
    # این متغیرها ندارد. اگر بعداً یک وب‌سرور ادمین جداگانه اضافه کردید،
    # این چک را دوباره فعال کنید.
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    print("✅ Configuration validated")
