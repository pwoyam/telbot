"""
ربات تلگرامی هوش مصنوعی شخصی - نسخه ۲
- حافظه پایدار در دیتابیس
- Rate Limiting
- پشتیبانی از Webhook برای سرور
- Polling برای توسعه محلی
"""
import asyncio
import logging
import time

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    InlineQueryHandler,
)
from telegram.constants import ParseMode

from config import (
    BOT_TOKEN, ADMIN_USER_IDS, PROXY_URL,
    DAILY_MESSAGE_LIMIT, USE_WEBHOOK, WEBHOOK_URL, WEBHOOK_PORT, WEBHOOK_SECRET
)
from database import (
    init_db, upsert_user, get_today_usage, increment_today_usage
)
from ai_service import get_ai_response, reset_history, web_search, set_language, _get_language

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🔄 مکالمه جدید"), KeyboardButton("ℹ️ راهنما")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        f"من دستیار هوش مصنوعی شخصی تو هستم.\n\n"
        f"🎯 **قابلیت‌ها:**\n"
        f"🌐 جستجوی وب با `/search سوال`\n"
        f"🌍 تغییر زبان با `/lang en` یا `/lang fa`\n"
        f"💬 استفاده به صورت Inline در چت‌های دیگه\n"
        f"🎨 پاسخ‌های Markdown زیبا\n"
        f"⏱️ نمایش زمان پاسخ\n"
        f"📊 محدودیت روزانه: {DAILY_MESSAGE_LIMIT} پیام (ادمین نامحدود)\n\n"
        f"هر سوالی داری بپرس!",
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🆔 آیدی عددی شما: `{user_id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_usage = get_today_usage(user_id)
    remaining = max(0, DAILY_MESSAGE_LIMIT - today_usage)

    lang = _get_language(user_id)
    if lang == "fa":
        text = (
            f"📊 **آمار امروز شما:**\n\n"
            f"📨 پیام‌های استفاده‌شده: `{today_usage}` / `{DAILY_MESSAGE_LIMIT}`\n"
            f"✨ باقیمانده: `{remaining}` پیام\n"
        )
    else:
        text = (
            f"📊 **Today's stats:**\n\n"
            f"📨 Used messages: `{today_usage}` / `{DAILY_MESSAGE_LIMIT}`\n"
            f"✨ Remaining: `{remaining}` messages\n"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**دستورات موجود:**\n\n"
        "`/search سوال` — جستجو در وب\n"
        "`/lang fa` — پاسخ فارسی (پیش‌فرض)\n"
        "`/lang en` — پاسخ انگلیسی\n"
        "`/reset` — پاک کردن حافظه مکالمه\n"
        "`/stats` — مشاهده آمار مصرف روزانه\n"
        "`/myid` — نمایش آیدی عددی شما\n"
        "`/help` — نمایش این راهنما\n"
        "`/start` — شروع مجدد",
        parse_mode=ParseMode.MARKDOWN
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_history(update.effective_user.id)
    await update.message.reply_text("✅ حافظه‌ی مکالمه پاک شد. می‌تونیم از اول شروع کنیم.")


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        current_lang = _get_language(user_id)
        lang_name = "فارسی" if current_lang == "fa" else "English"
        await update.message.reply_text(
            f"🌍 زبان فعلی: **{lang_name}**\n\n"
            f"برای تغییر زبان:\n"
            "`/lang fa` — فارسی\n"
            "`/lang en` — انگلیسی",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    lang = args[0].lower()
    if lang not in ["fa", "en"]:
        await update.message.reply_text("❌ زبان نامعتبر. فقط `fa` یا `en` مجاز است.", parse_mode=ParseMode.MARKDOWN)
        return

    set_language(user_id, lang)
    lang_name = "فارسی" if lang == "fa" else "English"
    await update.message.reply_text(f"✅ زبان تغییر کرد به: **{lang_name}**", parse_mode=ParseMode.MARKDOWN)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = " ".join(context.args)

    if not query:
        await update.message.reply_text("❌ لطفاً یک سوال برای جستجو بنویسید.\nمثال: `/search هوش مصنوعی`", parse_mode=ParseMode.MARKDOWN)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    start_time = time.time()
    results = web_search(query)
    end_time = time.time()

    response_time = round(end_time - start_time, 2)

    await update.message.reply_text(
        f"{results}\n\n⏱️ **زمان پاسخ:** {response_time} ثانیه",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_long_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list:
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def handle_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔄 مکالمه جدید":
        await reset_command(update, context)
    elif text == "ℹ️ راهنما":
        await help_command(update, context)
    else:
        await handle_message(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_text = update.message.text
    upsert_user(user_id, user.username, user.first_name)

    # === Rate Limit Check ===
    if not is_admin(user_id):
        today_usage = get_today_usage(user_id)
        if today_usage >= DAILY_MESSAGE_LIMIT:
            lang = _get_language(user_id)
            if lang == "fa":
                msg = (
                    f"⚠️ **محدودیت روزانه**\n\n"
                    f"شما امروز به سقف `{DAILY_MESSAGE_LIMIT}` پیام رسیده‌اید.\n"
                    f"لطفاً فردا دوباره امتحان کنید. 🙏"
                )
            else:
                msg = (
                    f"⚠️ **Daily limit reached**\n\n"
                    f"You have reached the daily limit of `{DAILY_MESSAGE_LIMIT}` messages.\n"
                    f"Please try again tomorrow. 🙏"
                )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    start_time = time.time()

    try:
        reply = await get_ai_response(user_id, user_text)
        if not is_admin(user_id):
            increment_today_usage(user_id)
    except Exception as e:
        logger.exception("AI service error")
        reply = "متاسفانه در حال حاضر مشکلی در پاسخ‌دهی پیش اومده. لطفاً دوباره امتحان کن."

    end_time = time.time()
    response_time = round(end_time - start_time, 2)

    lang = _get_language(user_id)
    time_text = f"\n\n⏱️ _{response_time} ثانیه_" if lang == "fa" else f"\n\n⏱️ _{response_time}s_"

    chunks = split_long_message(reply)
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await update.message.reply_text(chunk + time_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    user_id = update.effective_user.id

    if not query:
        return

    upsert_user(user_id, update.effective_user.username, update.effective_user.first_name)

    # Rate limit for inline
    if not is_admin(user_id):
        today_usage = get_today_usage(user_id)
        if today_usage >= DAILY_MESSAGE_LIMIT:
            await update.inline_query.answer(
                [InlineQueryResultArticle(
                    id="limit",
                    title="⚠️ Daily limit reached",
                    description="You reached the daily limit",
                    input_message_content=InputTextMessageContent(
                        message_text=f"Daily limit of {DAILY_MESSAGE_LIMIT} messages reached."
                    )
                })],
                cache_time=300
            )
            return

    try:
        start_time = time.time()

        if query.lower().startswith("search "):
            search_query = query[7:]
            reply = web_search(search_query)
        else:
            reply = await get_ai_response(user_id, query)
            if not is_admin(user_id):
                increment_today_usage(user_id)

        end_time = time.time()
        response_time = round(end_time - start_time, 2)

        results = [
            InlineQueryResultArticle(
                id=str(user_id),
                title="💬 پاسخ هوش مصنوعی",
                description=reply[:100] + "..." if len(reply) > 100 else reply,
                input_message_content=InputTextMessageContent(
                    message_text=reply + f"\n\n⏱️ _{response_time}s_",
                    parse_mode=ParseMode.MARKDOWN
                )
            )
        ]

        await update.inline_query.answer(results, cache_time=1)

    except Exception as e:
        logger.exception("Inline query error")


async def main():
    init_db()
    builder = Application.builder().token(BOT_TOKEN)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
    application = builder.build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(InlineQueryHandler(inline_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text))

    async with application:
        await application.start()

        if USE_WEBHOOK and WEBHOOK_URL:
            # === WEBHOOK MODE (Production) ===
            webhook_path = f"/webhook/{BOT_TOKEN}"
            full_url = f"{WEBHOOK_URL}{webhook_path}"
            logger.info(f"🌐 Starting bot with Webhook: {full_url}")
            await application.updater.start_webhook(
                listen="0.0.0.0",
                port=WEBHOOK_PORT,
                webhook_url=full_url,
                secret_token=WEBHOOK_SECRET or None,
                drop_pending_updates=True,
            )
        else:
            # === POLLING MODE (Development) ===
            logger.info("🔄 Starting bot with Polling...")
            await application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )

        logger.info("✅ ربات با موفقیت اجرا شد. برای توقف Ctrl+C بزنید.")
        stop_event = asyncio.Event()
        await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
