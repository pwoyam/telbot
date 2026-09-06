from config import (
    BOT_TOKEN,
    SUBSCRIPTION_PRICE_TOMAN,
    SUBSCRIPTION_DAYS,
    WEBHOOK_HOST,
    WEBHOOK_PORT,
    ADMIN_USER_IDS,
    PROXY_URL,
)
from database import (
    init_db,
    upsert_user,
    is_user_subscribed,
    get_today_usage,
    increment_today_usage,
    create_payment,
    get_user_free_limit,
)
from ai_service import get_ai_response, reset_history
from payment import request_payment
from webhook_server import create_app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ---------- کیبورد ثابت پایین صفحه ----------

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📊 وضعیت من"), KeyboardButton("💎 خرید اشتراک")],
        [KeyboardButton("🔄 مکالمه جدید"), KeyboardButton("ℹ️ راهنما")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ---------- دستورات ربات ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        f"من یه دستیار هوش مصنوعی هستم که می‌تونم به سوالاتت جواب بدم.\n\n"
        f"🆓 روزانه چند پیام رایگان داری.\n"
        f"💎 برای دسترسی نامحدود از دکمه «خرید اشتراک» استفاده کن.\n"
        f"🔄 برای شروع مکالمه‌ی جدید روی «مکالمه جدید» بزن.",
        reply_markup=get_main_keyboard()
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🆔 آیدی عددی شما: `{user_id}`\n\n"
        f"اگه می‌خواید ادمین بشید، این عدد رو توی .env جلوی ADMIN_USER_IDS بذارید و ربات رو ری‌استارت کنید.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات و دکمه‌های موجود:\n\n"
        "📊 وضعیت من — دیدن وضعیت اشتراک و پیام‌های باقی‌مانده\n"
        "💎 خرید اشتراک — خرید اشتراک نامحدود\n"
        "🔄 مکالمه جدید — پاک کردن حافظه مکالمه\n"
        "ℹ️ راهنما — نمایش همین پیام\n\n"
        "یا می‌تونی مستقیم سوالت رو بنویسی."
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_history(update.effective_user.id)
    await update.message.reply_text("✅ حافظه‌ی مکالمه پاک شد. می‌تونیم از اول شروع کنیم.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_user_subscribed(user_id):
        await update.message.reply_text("💎 اشتراک شما فعال است.")
    else:
        used = get_today_usage(user_id)
        free_limit = get_user_free_limit(user_id)
        remaining = max(0, free_limit - used)
        await update.message.reply_text(
            f"🆓 شما اشتراک فعال ندارید.\n"
            f"پیام‌های رایگان امروز: {remaining} از {free_limit} باقی مانده.\n"
            f"برای خرید اشتراک از دکمه «خرید اشتراک» استفاده کن."
        )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_user_subscribed(user_id):
        await update.message.reply_text("✅ شما همین الان هم اشتراک فعال دارید!")
        return

    await update.message.reply_text("⏳ در حال ایجاد لینک پرداخت...")

    authority, result = await request_payment(
        amount_toman=SUBSCRIPTION_PRICE_TOMAN,
        user_id=user_id,
        description=f"اشتراک {SUBSCRIPTION_DAYS} روزه ربات",
    )

    if authority is None:
        await update.message.reply_text(f"❌ خطا در ایجاد پرداخت: {result}")
        return

    create_payment(user_id, authority, SUBSCRIPTION_PRICE_TOMAN)
    await update.message.reply_text(
        f"💳 برای پرداخت {SUBSCRIPTION_PRICE_TOMAN:,} تومان روی لینک زیر بزنید:\n\n{result}\n\n"
        f"بعد از پرداخت موفق، اشتراک شما به‌صورت خودکار فعال می‌شود."
    )


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


# ---------- هندل دکمه‌ها و پیام‌های متنی ----------

async def handle_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📊 وضعیت من":
        await status_command(update, context)
    elif text == "💎 خرید اشتراک":
        await subscribe_command(update, context)
    elif text == "🔄 مکالمه جدید":
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

    is_admin = user_id in ADMIN_USER_IDS

    if not is_admin and not is_user_subscribed(user_id):
        used = get_today_usage(user_id)
        free_limit = get_user_free_limit(user_id)
        if used >= free_limit:
            await update.message.reply_text(
                "⛔️ پیام‌های رایگان امروزت تموم شده.\n"
                "برای ادامه از دکمه «خرید اشتراک» استفاده کن."
            )
            return
        increment_today_usage(user_id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply = await get_ai_response(user_id, user_text)
    except Exception as e:
        logger.exception("AI service error")
        reply = "متاسفانه در حال حاضر مشکلی در پاسخ‌دهی پیش اومده. لطفاً دوباره امتحان کن."

    for chunk in split_long_message(reply):
        await update.message.reply_text(chunk)


# ---------- اجرای همزمان ربات + سرور کالبک ----------

async def run_webhook_server(bot):
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()
    logger.info(f"سرور کالبک پرداخت روی {WEBHOOK_HOST}:{WEBHOOK_PORT} اجرا شد.")


async def main():
    init_db()

    builder = Application.builder().token(BOT_TOKEN)

    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)

    application = builder.build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_text))

    async with application:
        await application.start()
        await application.updater.start_polling()
        await run_webhook_server(application.bot)

        logger.info("ربات و سرور کالبک با موفقیت اجرا شدند. برای توقف Ctrl+C بزنید.")
        stop_event = asyncio.Event()
        await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
