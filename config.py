"""
تنظیمات اصلی پروژه
همه‌ی مقادیر حساس از فایل .env خوانده می‌شوند
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- تلگرام ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# آیدی عددی کاربرانی که ادمین هستن (با کاما جدا کنید، مثلاً: 111111,222222)
ADMIN_USER_IDS = [
    int(uid.strip()) for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()
]

# --- هوش مصنوعی ---
# provider: "openai" یا "anthropic" یا هر reseller سازگار با OpenAI
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")  # برای reseller های ایرانی یا proxy، آدرس سفارشی
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

# --- زرین‌پال ---
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "")
ZARINPAL_SANDBOX = os.getenv("ZARINPAL_SANDBOX", "true").lower() == "true"
# آدرس عمومی سرور شما که کالبک پرداخت به آن برمی‌گردد (باید https باشد)
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "https://yourdomain.com")

# --- اشتراک ---
SUBSCRIPTION_PRICE_TOMAN = int(os.getenv("SUBSCRIPTION_PRICE_TOMAN", "99000"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
FREE_DAILY_MESSAGES = int(os.getenv("FREE_DAILY_MESSAGES", "5"))  # تعداد پیام رایگان روزانه

# --- دیتابیس ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

# --- وب سرور کالبک (برای زرین‌پال) ---
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))

# --- پنل ادمین ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")  # حتماً عوضش کن
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "super-secret-key-change-me")  # برای سشن
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "super-secret-key-change-me")
PROXY_URL = os.getenv("PROXY_URL", "")