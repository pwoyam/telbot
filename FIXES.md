# تغییرات اعمال‌شده نسبت به v2-production-ready

## 🔴 بحرانی
1. **کرش کردن `/stats` و کل پنل ادمین** — در ۷ جای کد (`bot.py` و ۶ مورد در
   `admin_commands.py`) از الگوی اشتباه `async with get_connection() as conn:`
   استفاده شده بود. چون `get_connection()` تابع `async def` است، این باعث
   خطای `TypeError` در همان لحظه‌ی اجرا می‌شد. اصلاح شد به:
   - `conn = await get_connection()` برای کوئری‌های ساده، یا
   - `async with get_conn() as conn:` (تابع امن موجود در `database.py`
     که commit/rollback می‌کند ولی کانکشن مشترک را نمی‌بندد).

## 🟠 مهم
2. **دکمه‌های خراب پنل ادمین** — روت‌های گم‌شده برای `admin_back`،
   `admin_questions_*`، `admin_clear_history_*`، `admin_limit_*` و
   `admin_settings_model` به `admin_button_handler` اضافه شد؛ توابع
   `handle_clear_history` و `handle_limit_change` هم پیاده‌سازی شدند.
3. **پاک نشدن کش با prefix** — در `cache.py` یک ستون `prefix` جدا به جدول
   کش اضافه شد (با migration خودکار) تا `cache_clear("ai_response")` و
   `cache_clear("web_search")` واقعاً همان namespace را پاک کنند، نه اینکه
   بی‌اثر بمانند چون کلید واقعی هش SHA256 است.
4. **تغییر زنده‌ی محدودیت روزانه** — دکمه‌ی «تغییر محدودیت روزانه» قبلاً هیچ
   اثری نداشت چون `DAILY_MESSAGE_LIMIT` با `from config import ...` کپی شده
   بود. حالا `bot.py` و `admin_commands.py` از `config.DAILY_MESSAGE_LIMIT`
   استفاده می‌کنند و دکمه واقعاً مقدار را در حافظه‌ی پردازش تغییر می‌دهد
   (برای ماندگاری بعد از ری‌استارت، `.env` را هم به‌روز کنید).
5. **`ADMIN_PANEL_PASSWORD` اجباری بدون وجود پنل وب** — `validate_config()`
   دیگر این متغیر را الزامی نمی‌کند، چون هیچ سرور وب پنل ادمینی در این
   کدبیس پیاده‌سازی نشده (پنل فعلی همان دستور تلگرامی `/admin` است).

## 🟡 جزئی
6. **request_id مشترک بین درخواست‌های هم‌زمان** — در `logging_config.py`
   یک متغیر global ساده جایگزینِ `contextvars.ContextVar` شد تا وقتی چند
   کاربر هم‌زمان پیام می‌فرستند، لاگ‌ها request_id درست خودشان را نشان دهند.

## بدون تغییر (چون از قبل درست بودند)
- همه‌ی کوئری‌های SQL پارامتریزه هستند (بدون خطر SQL Injection).
- Rate limiting به‌صورت atomic و امن در برابر race condition.
- امنیت Webhook (secret token، بدون توکن در URL).
