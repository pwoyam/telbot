"""
Telegram AI Bot - Production-ready with caching, health checks,
structured logging, safe Markdown, atomic rate limiting, and async search.
"""
import asyncio
import logging
import signal
import time
import config

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, InlineQueryHandler, CallbackQueryHandler,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import (
    BOT_TOKEN, ADMIN_USER_IDS, PROXY_URL,
    USE_WEBHOOK, WEBHOOK_URL,
    WEBHOOK_PORT, WEBHOOK_SECRET, validate_config,
    STRUCTURED_LOGGING, HEALTH_PORT, HEALTH_HOST,
)
from logging_config import setup_logging, ContextLogger, get_context_filter
from health import HealthServer

# Create health server with config
health_server = HealthServer(host=HEALTH_HOST, port=HEALTH_PORT)
from database import init_db, upsert_user, try_increment_usage, is_user_blocked
from admin_commands import admin_command, admin_button_handler, is_admin as check_admin
from cache import close_cache, get_cache_stats
from ai_service import (
    get_ai_response, get_ai_response_inline, reset_history,
    web_search, set_language, _get_language,
    AIServiceError, AIServiceTimeoutError, AIServiceRateLimitError,
    AIServiceAuthError, AIServiceUnavailableError,
)

# Setup logging (structured for production, colorful for dev)
setup_logging(structured=STRUCTURED_LOGGING)
logger = ContextLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🔄 مکالمه جدید"), KeyboardButton("ℹ️ راهنما")]],
        resize_keyboard=True,
    )


# ===== Safe Markdown sender =====
async def safe_reply(message, text: str, **kwargs):
    """Send with Markdown; fall back to plain text on parse error."""
    try:
        return await message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, **kwargs
        )
    except BadRequest as e:
        logger.warning("Markdown failed, falling back to plain text: %s", e)
        plain = text.replace("**", "").replace("*", "").replace("`", "")
        try:
            return await message.reply_text(plain, **kwargs)
        except Exception as e2:
            logger.error("Plain text fallback also failed: %s", e2)
            return None


def split_long_message(text: str, limit: int = 4096) -> list:
    """Split long messages while preserving code blocks."""
    if len(text) <= limit:
        return [text]
    
    chunks = []
    remaining = text
    
    while len(remaining) > limit:
        window = remaining[:limit]
        
        triple = window.count("```")
        in_code = (triple % 2 == 1)
        
        split_at = -1
        
        if in_code:
            code_start = window.find("```")
            if code_start > 200:
                split_at = code_start
        
        if split_at == -1 or split_at < limit // 2:
            split_at = window.rfind("\n\n")
        if split_at == -1 or split_at < limit // 2:
            split_at = window.rfind("\n")
        if split_at == -1 or split_at < limit // 2:
            split_at = window.rfind(" ")
        if split_at == -1 or split_at < limit // 2:
            split_at = limit
        
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    
    if remaining:
        chunks.append(remaining)
    return chunks


# ===== Commands =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)
    await safe_reply(
        update.message,
        f"سلام {user.first_name} 👋\n\n"
        f"من دستیار هوش مصنوعی شخصی تو هستم.\n\n"
        f"🎯 **قابلیت‌ها:**\n"
        f"🌐 `/search سوال` — جستجو در وب\n"
        f"🌍 `/lang fa|en` — تغییر زبان\n"
        f"🔄 `/reset` — پاک کردن حافظه\n"
        f"📊 `/stats` — آمار مصرف\n"
        f"💬 حالت Inline در چت‌های دیگه\n"
        f"🗂️ `/cache` — آمار کش (فقط ادمین)\n\n"
        f"📊 محدودیت روزانه: {config.DAILY_MESSAGE_LIMIT} پیام",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message,
        "**دستورات:**\n\n"
        "`/search سوال` — جستجو در وب\n"
        "`/lang fa|en` — تغییر زبان\n"
        "`/reset` — پاک کردن حافظه\n"
        "`/stats` — آمار مصرف\n"
        "`/myid` — آیدی عددی\n"
        "`/cache` — آمار کش (فقط ادمین)\n"
        "`/help` — این راهنما",
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reset_history(update.effective_user.id)
    await safe_reply(update.message, "✅ حافظه‌ی مکالمه پاک شد.")


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message, f"🆔 آیدی عددی: `{update.effective_user.id}`"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from database import get_connection
    import datetime
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT message_count FROM daily_usage WHERE user_id=? AND usage_date=?",
        (user_id, datetime.date.today().isoformat()),
    )
    row = await cursor.fetchone()
    usage = row["message_count"] if row else 0
    
    await safe_reply(
        update.message,
        f"📊 **آمار امروز:**\n\n"
        f"📨 استفاده شده: `{usage}` / `{config.DAILY_MESSAGE_LIMIT}`\n"
        f"✨ باقیمانده: `{max(0, config.DAILY_MESSAGE_LIMIT - usage)}`",
    )


async def cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show cache statistics (admin only)."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ این دستور فقط برای ادمین‌ها مجاز است.")
        return
    
    stats = get_cache_stats()
    await safe_reply(
        update.message,
        f"🗂️ **آمار کش:**\n\n"
        f"🟢 Hit: `{stats['hits']}`\n"
        f"🔴 Miss: `{stats['misses']}`\n"
        f"📊 مجموع: `{stats['total']}`\n"
        f"📈 Hit Rate: `{stats['hit_rate_percent']}%`",
    )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        lang = await _get_language(user_id)
        await safe_reply(
            update.message,
            f"🌍 زبان فعلی: **{'فارسی' if lang == 'fa' else 'English'}**\n\n"
            f"`/lang fa` یا `/lang en`",
        )
        return
    
    lang = args[0].lower()
    if lang not in ("fa", "en"):
        await safe_reply(update.message, "❌ فقط `fa` یا `en`")
        return
    
    await set_language(user_id, lang)
    await safe_reply(
        update.message,
        f"✅ زبان تغییر کرد: **{'فارسی' if lang == 'fa' else 'English'}**",
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = " ".join(context.args)
    
    if not query:
        await safe_reply(
            update.message, "❌ مثال: `/search هوش مصنوعی`"
        )
        return
    
    # چک بلاک بودن
    if await is_user_blocked(user_id):
        await safe_reply(update.message, "⛔ دسترسی شما مسدود شده است.")
        return
    
    # Atomic rate limit
    if not is_admin(user_id):
        allowed, _ = await try_increment_usage(user_id, config.DAILY_MESSAGE_LIMIT)
        if not allowed:
            await safe_reply(
                update.message,
                f"⚠️ **محدودیت روزانه**\n\n"
                f"سقف `{config.DAILY_MESSAGE_LIMIT}` پیام رسیده.",
            )
            return
    
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    start = time.time()
    results = await web_search(query)
    duration = round(time.time() - start, 2)
    
    await safe_reply(
        update.message,
        f"{results}\n\n⏱️ **زمان پاسخ:** {duration} ثانیه",
        disable_web_page_preview=True,
    )
    
    # Track metrics
    health_server.increment("searches")


async def handle_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔄 مکالمه جدید":
        await reset_command(update, context)
    elif text == "ℹ️ راهنما":
        await help_command(update, context)
    else:
        await handle_message(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Generate request ID for tracing
    request_id = get_context_filter().generate_request_id()
    start_time_req = time.time()
    
    user = update.effective_user
    user_id = user.id
    user_text = update.message.text
    
    req_logger = logger.bind(user_id=user_id, request_id=request_id)
    req_logger.info("Incoming message", action="chat")
    
    # چک بلاک بودن کاربر
    if await is_user_blocked(user_id):
        await safe_reply(update.message, "⛔ دسترسی شما مسدود شده است.")
        return
    
    await upsert_user(user_id, user.username, user.first_name)
    
    # چک بلاک بودن
    if await is_user_blocked(user_id):
        await safe_reply(update.message, "⛔ دسترسی شما مسدود شده است.")
        return
    
    # Atomic rate limit
    if not is_admin(user_id):
        allowed, _ = await try_increment_usage(user_id, config.DAILY_MESSAGE_LIMIT)
        if not allowed:
            await safe_reply(
                update.message,
                f"⚠️ **محدودیت روزانه**\n\n"
                f"سقف `{config.DAILY_MESSAGE_LIMIT}` پیام رسیده.",
            )
            return
    
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    start = time.time()
    
    try:
        reply = await get_ai_response(user_id, user_text)
    except AIServiceTimeoutError:
        reply = "⏳ درخواست زمان بیشتری نیاز داشت."
    except AIServiceRateLimitError:
        reply = "🚫 محدودیت درخواست. لطفاً صبر کنید."
    except AIServiceAuthError:
        logger.error("AI auth error")
        reply = "❌ خطای سرویس هوش مصنوعی."
    except AIServiceUnavailableError:
        reply = "🔧 سرویس موقتاً در دسترس نیست."
    except AIServiceError:
        logger.exception("AI error")
        reply = "متاسفانه مشکل پاسخ‌دهی پیش اومد."
    except Exception:
        logger.exception("Unexpected error")
        reply = "❌ خطای غیرمنتظره."
    
    duration = round(time.time() - start, 2)
    time_text = f"\n\n⏱️ _{duration} ثانیه_"
    
    chunks = split_long_message(reply)
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await safe_reply(update.message, chunk + time_text)
        else:
            await safe_reply(update.message, chunk)
    
    # Track metrics
    health_server.increment("requests_processed")
    duration_ms = round((time.time() - start_time_req) * 1000)
    req_logger.info("Message processed", action="chat_complete", duration_ms=duration_ms)


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    user_id = update.effective_user.id
    
    if not query:
        return
    
    await upsert_user(
        user_id,
        update.effective_user.username,
        update.effective_user.first_name,
    )
    
    # Rate limit for inline too
    if not is_admin(user_id):
        allowed, _ = await try_increment_usage(user_id, config.DAILY_MESSAGE_LIMIT)
        if not allowed:
            await update.inline_query.answer(
                [InlineQueryResultArticle(
                    id="limit",
                    title="⚠️ Daily limit reached",
                    input_message_content=InputTextMessageContent(
                        message_text=f"Limit of {config.DAILY_MESSAGE_LIMIT} reached."
                    ),
                )],
                cache_time=300,
            )
            return
    
    try:
        start = time.time()
        health_server.increment("inline_queries")
        
        if query.lower().startswith("search "):
            reply = await web_search(query[7:])
        else:
            # Separate context - no history pollution
            reply = await get_ai_response_inline(user_id, query)
        
        duration = round(time.time() - start, 2)
        
        results = [InlineQueryResultArticle(
            id=str(user_id),
            title="💬 پاسخ هوش مصنوعی",
            description=(reply[:100] + "...") if len(reply) > 100 else reply,
            input_message_content=InputTextMessageContent(
                message_text=reply + f"\n\n⏱️ _{duration}s_",
                parse_mode=ParseMode.MARKDOWN,
            ),
        )]
        
        await update.inline_query.answer(results, cache_time=1)
    except Exception:
        logger.exception("Inline query error")


async def main():
    # Validate FIRST - fail fast
    validate_config()
    
    # Graceful shutdown setup
    stop_event = asyncio.Event()
    shutdown_requested = False
    
    def signal_handler():
        nonlocal shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            logger.info("🛑 Shutdown signal received, draining requests...")
            stop_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass
    
    await init_db()
    
    builder = Application.builder().token(BOT_TOKEN)
    
    # ذخیره لیست ادمین‌ها برای استفاده در هندلرها
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    app = builder.build()
    
    # تنظیم ادمین‌ها در bot_data
    app.bot_data["admin_ids"] = ADMIN_USER_IDS
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("cache", cache_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(admin_button_handler))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_button_text
    ))
    
    async with app:
        await app.start()
        
        # Start health server
        try:
            await health_server.start()
        except Exception as e:
            logger.warning("Health server failed to start: %s", e)
        
        if USE_WEBHOOK and WEBHOOK_URL:
            # SECURE webhook: no token in URL, secret required
            webhook_path = "/webhook"
            full_url = f"{WEBHOOK_URL}{webhook_path}"
            logger.info(
                "🌐 Starting webhook on port %d (URL not logged for security)",
                WEBHOOK_PORT,
            )
            await app.updater.start_webhook(
                listen="0.0.0.0",
                port=WEBHOOK_PORT,
                webhook_url=full_url,
                url_path=webhook_path,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
        else:
            logger.info("🔄 Starting with Polling...")
            await app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
        
        logger.info("✅ Bot started. Ctrl+C to stop.")
        await stop_event.wait()
        
        # Graceful shutdown
        logger.info("🔄 Shutting down gracefully...")
        try:
            await health_server.stop()
        except Exception as e:
            logger.warning("Error stopping health server: %s", e)
        
        try:
            await close_cache()
        except Exception as e:
            logger.warning("Error closing cache: %s", e)
        
        logger.info("👋 Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
