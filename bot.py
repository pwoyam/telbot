"""
ربات تلگرامی هوش مصنوعی شخصی

اجرا: python bot.py
"""
import asyncio
import logging

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN, ADMIN_USER_IDS, PROXY_URL
from database import init_db, upsert_user
from ai_service import get_ai_response, reset_history

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


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
        f"من دستیار هوش مصنوعی شخصی تو هستم.\n"
        f"هر سوالی داری بپرس یا از دکمه‌های پایین استفاده کن.",
        reply_markup=get_main_keyboard()
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🆔 آیدی عددی شما: `{user_id}`",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات و دکمه‌های موجود:\n\n"
        "🔄 مکالمه جدید — پاک کردن حافظه مکالمه\n"
        "ℹ️ راهنما — نمایش همین پیام\n"
        "یا می‌تونی مستقیم سوالت رو بنویسی."
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_history(update.effective_user.id)
    await update.message.reply_text("✅ حافظه‌ی مکالمه پاک شد. می‌تونیم از اول شروع کنیم.")


TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_long_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
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
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = await get_ai_response(user_id, user_text)
    except Exception as e:
        logger.exception("AI service error")
        reply = "متاسفانه در حال حاضر مشکلی در پاسخ‌دهی پیش اومده. لطفاً دوباره امتحان کن."
    for chunk in split_long_message(reply):
        await update.message.reply_text(chunk)


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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text))
    async with application:
        await application.start()
        await application.updater.start_polling()
        logger.info("ربات با موفقیت اجرا شد. برای توقف Ctrl+C بزنید.")
        stop_event = asyncio.Event()
        await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())