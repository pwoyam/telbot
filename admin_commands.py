"""
دستورات مدیریت ربات - فقط برای ادمین‌ها

شامل:
- آمار کلی
- مدیریت کاربران (لیست، جستجو، بلاک)
- دیدن سوالات کاربران
- مدیریت کش
- ارسال همگانی
- تنظیمات ربات
"""
import asyncio
from datetime import date

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    CallbackQuery, InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
from config import AI_MODEL, AI_PROVIDER
from database import (
    get_conn, block_user, unblock_user,
    is_user_blocked, get_blocked_users,
)
from cache import cache_clear, get_cache_stats, close_cache
from ai_service import (
    get_ai_response, reset_history, _get_language,
)


def is_admin(user_id: int, admin_ids: list) -> bool:
    return user_id in admin_ids


# ===== /admin - منوی اصلی =====
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id, context.bot_data.get("admin_ids", [])):
        await update.message.reply_text("❌ دسترسی غیرمجاز")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"),
            InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("🗂️ مدیریت کش", callback_data="admin_cache"),
            InlineKeyboardButton("📢 همگانی", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings"),
        ],
    ]
    
    await update.message.reply_text(
        "🤖 **پنل مدیریت ادمین**\n\ng یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


# ===== هندلر کلی برای دکمه‌های ادمین =====
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_admin(user_id, context.bot_data.get("admin_ids", [])):
        await query.answer("❌ دسترسی غیرمجاز")
        return
    
    await query.answer()
    
    action = query.data
    
    if action == "admin_stats":
        await show_stats(query, context)
    elif action == "admin_users":
        await show_users_menu(query)
    elif action == "admin_users_list":
        await show_users_list(query)
    elif action == "admin_users_new":
        await show_new_users(query)
    elif action == "admin_users_top":
        await show_top_users(query)
    elif action.startswith("admin_clear_history_"):
        # باید قبل از admin_user_ چک بشه چون هر دو با admin_ شروع میشن
        await handle_clear_history(query, int(action.rsplit("_", 1)[1]))
    elif action.startswith("admin_questions_"):
        await show_user_questions(query, int(action.rsplit("_", 1)[1]))
    elif action.startswith("admin_user_"):
        await show_user_detail(query, int(action.rsplit("_", 1)[1]))
    elif action.startswith("admin_block_"):
        await handle_block(query, int(action.rsplit("_", 1)[1]))
    elif action.startswith("admin_unblock_"):
        await handle_unblock(query, int(action.rsplit("_", 1)[1]))
    elif action == "admin_blocked":
        await show_blocked_users(query)
    elif action == "admin_cache":
        await show_cache_menu(query)
    elif action == "admin_cache_clear":
        await handle_cache_clear(query)
    elif action == "admin_cache_ai":
        await handle_cache_clear_ai(query)
    elif action == "admin_cache_search":
        await handle_cache_clear_search(query)
    elif action == "admin_broadcast":
        await start_broadcast(query)
    elif action == "admin_settings":
        await show_settings(query)
    elif action == "admin_settings_limit":
        await show_limit_options(query)
    elif action.startswith("admin_limit_"):
        await handle_limit_change(query, int(action.rsplit("_", 1)[1]))
    elif action == "admin_settings_model":
        await show_settings(query)  # تغییر مدل نیازمند ری‌استارت است؛ فعلاً فقط نمایش تنظیمات فعلی
    elif action == "admin_back":
        await show_main_menu(query)


# ===== 📊 آمار کلی =====
async def show_stats(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    async with get_conn() as conn:
        # کاربران
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]
        
        # کل سوالات
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='user'"
        )
        total_questions = (await cursor.fetchone())[0]
        
        # سوالات امروز
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='user' AND created_at LIKE ?",
            (f"{date.today().isoformat()}%",)
        )
        today_questions = (await cursor.fetchone())[0]
        
        # کاربران فعال امروز
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM daily_usage WHERE usage_date=?",
            (date.today().isoformat(),)
        )
        active_today = (await cursor.fetchone())[0]
        
        # کاربران بلاک‌شده
        cursor = await conn.execute("SELECT COUNT(*) FROM blocked_users")
        blocked_count = (await cursor.fetchone())[0]
    
    # آمار کش
    cache_stats = get_cache_stats()
    
    text = f"""📊 **آمار کلی ربات**

👥 **کاربران**
├── کل: `{total_users}` نفر
├── فعال امروز: `{active_today}` نفر
└── بلاک‌شده: `{blocked_count}` نفر

💬 **پیام‌ها**
├── کل سوالات: `{total_questions}`
└── سوالات امروز: `{today_questions}`

🗂️ **وضعیت کش**
├── 🟢 Hit: `{cache_stats['hits']}`
├── 🔴 Miss: `{cache_stats['misses']}`
└── 📈 Hit Rate: `{cache_stats['hit_rate_percent']}%`

⚙️ **تنظیمات فعلی**
├── مدل: `{AI_MODEL}`
├── سرویس: `{AI_PROVIDER}`
└── محدودیت روزانه: `{config.DAILY_MESSAGE_LIMIT}` پیام"""
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ])
    )


# ===== 👥 منوی کاربران =====
async def show_users_menu(query: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton("📋 لیست کاربران", callback_data="admin_users_list")],
        [InlineKeyboardButton("🆕 کاربران جدید", callback_data="admin_users_new")],
        [InlineKeyboardButton("🏆 بیشترین استفاده", callback_data="admin_users_top")],
        [InlineKeyboardButton("🚫 لیست بلاک‌شده", callback_data="admin_blocked")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ]
    
    await query.edit_message_text(
        "👥 **مدیریت کاربران**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def show_users_list(query: CallbackQuery):
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, COUNT(m.id) as msg_count
            FROM users u
            LEFT JOIN messages m ON u.user_id = m.user_id AND m.role='user'
            GROUP BY u.user_id
            ORDER BY msg_count DESC
            LIMIT 10
            """
        )
        users = await cursor.fetchall()
    
    keyboard = []
    for u in users:
        name = u["first_name"] or u["username"] or str(u["user_id"])
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {name} ({u['msg_count']} سوال)",
                callback_data=f"admin_user_{u['user_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")])
    
    await query.edit_message_text(
        "📋 **کاربران فعال‌تر (۱۰ نفر اول)**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def show_new_users(query: CallbackQuery):
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT user_id, username, first_name, joined_at
            FROM users
            WHERE joined_at LIKE ?
            ORDER BY joined_at DESC
            LIMIT 10
            """,
            (f"{date.today().isoformat()}%",)
        )
        users = await cursor.fetchall()
    
    if not users:
        text = "🆕 امروز کاربر جدیدی عضو نشده است."
    else:
        text = "🆕 **کاربران جدید امروز:**\n\n"
        for u in users:
            name = u["first_name"] or u["username"] or str(u["user_id"])
            text += f"• {name} ({u['user_id']})\n"
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ])
    )


async def show_top_users(query: CallbackQuery):
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, COUNT(m.id) as msg_count
            FROM users u
            LEFT JOIN messages m ON u.user_id = m.user_id AND m.role='user'
            GROUP BY u.user_id
            ORDER BY msg_count DESC
            LIMIT 5
            """
        )
        users = await cursor.fetchall()
    
    text = "🏆 **بیشترین استفاده‌کننده‌ها:**\n\n"
    for i, u in enumerate(users, 1):
        name = u["first_name"] or u["username"] or str(u["user_id"])
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
        text += f"{medal} {name} - `{u['msg_count']}` سوال\n"
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ])
    )


async def show_user_detail(query: CallbackQuery, user_id: int):
    async with get_conn() as conn:
        # اطلاعات کاربر
        cursor = await conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        )
        user = await cursor.fetchone()
        
        if not user:
            await query.edit_message_text("❌ کاربر پیدا نشد")
            return
        
        # تعداد سوالات
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id=? AND role='user'",
            (user_id,)
        )
        question_count = (await cursor.fetchone())[0]
        
        # وضعیت بلاک
        cursor = await conn.execute(
            "SELECT blocked_at FROM blocked_users WHERE user_id=?", (user_id,)
        )
        blocked = await cursor.fetchone()
    
    name = user["first_name"] or user["username"] or str(user_id)
    status = "🚫 بلاک شده" if blocked else "✅ فعال"
    
    text = f"""👤 **اطلاعات کاربر**

🆔 آیدی: `{user_id}`
👤 نام: {name}
📧 نام کاربری: @{user['username'] or '-'}
🌍 زبان: {'فارسی' if user['language'] == 'fa' else 'English'}
💬 تعداد سوالات: `{question_count}`
📅 عضویت: {user['joined_at'][:10] if user['joined_at'] else '-'}
📌 وضعیت: {status}"""
    
    keyboard = [
        [InlineKeyboardButton("📝 دیدن سوالات", callback_data=f"admin_questions_{user_id}")],
    ]
    
    if blocked:
        keyboard.append([InlineKeyboardButton("✅ آنبلاک", callback_data=f"admin_unblock_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 بلاک کردن", callback_data=f"admin_block_{user_id}")])
    
    keyboard.append([InlineKeyboardButton("🗑️ پاک کردن تاریخچه", callback_data=f"admin_clear_history_{user_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")])
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_user_questions(query: CallbackQuery, user_id: int):
    async with get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT content, created_at FROM messages
            WHERE user_id=? AND role='user'
            ORDER BY id DESC
            LIMIT 10
            """,
            (user_id,)
        )
        questions = await cursor.fetchall()
    
    if not questions:
        text = f"📝 کاربر `{user_id}` هنوز سوالی نپرسیده است."
    else:
        text = f"📝 **آخرین سوالات کاربر {user_id}:**\n\n"
        for i, q in enumerate(questions, 1):
            time = q["created_at"][:16].replace("T", " ") if q["created_at"] else "-"
            # کوتاه کردن سوال‌های طولانی
            content = q["content"][:100] + "..." if len(q["content"]) > 100 else q["content"]
            text += f"{i}. {content}\n   ⏰ {time}\n\n"
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_user_{user_id}")]
        ])
    )


async def handle_clear_history(query: CallbackQuery, user_id: int):
    from database import reset_user_history
    await reset_user_history(user_id)
    await query.edit_message_text(
        f"✅ تاریخچه‌ی مکالمه کاربر `{user_id}` پاک شد.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_user_{user_id}")]
        ])
    )


async def handle_block(query: CallbackQuery, user_id: int):
    await block_user(user_id, "Blocked by admin")
    await query.edit_message_text(
        f"✅ کاربر `{user_id}` با موفقیت بلاک شد.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ])
    )


async def handle_unblock(query: CallbackQuery, user_id: int):
    await unblock_user(user_id)
    await query.edit_message_text(
        f"✅ کاربر `{user_id}` آنبلاک شد.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ])
    )


async def show_blocked_users(query: CallbackQuery):
    blocked = await get_blocked_users()
    
    if not blocked:
        text = "🚫 هیچ کاربری بلاک نیست."
    else:
        text = f"🚫 **کاربران بلاک‌شده ({len(blocked)} نفر):**\n\n"
        for b in blocked:
            name = b["first_name"] or b["username"] or str(b["user_id"])
            reason = b["reason"] or "-"
            text += f"• {name} ({b['user_id']})\n   دلیل: {reason}\n\n"
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")]
        ])
    )


# ===== 🗂️ مدیریت کش =====
async def show_cache_menu(query: CallbackQuery):
    stats = get_cache_stats()
    
    keyboard = [
        [InlineKeyboardButton("🗑️ پاک کردن همه کش", callback_data="admin_cache_clear")],
        [InlineKeyboardButton("🗑️ پاک کردن کش AI", callback_data="admin_cache_ai")],
        [InlineKeyboardButton("🗑️ پاک کردن کش جستجو", callback_data="admin_cache_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ]
    
    text = f"""🗂️ **مدیریت کش**

📊 وضعیت فعلی:
├── 🟢 Hit: `{stats['hits']}`
├── 🔴 Miss: `{stats['misses']}`
└── 📈 Hit Rate: `{stats['hit_rate_percent']}%`"""
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_cache_clear(query: CallbackQuery):
    await cache_clear()
    await query.edit_message_text(
        "✅ همه کش با موفقیت پاک شد.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_cache")]
        ])
    )


async def handle_cache_clear_ai(query: CallbackQuery):
    await cache_clear("ai_response")
    await query.edit_message_text(
        "✅ کش AI پاک شد.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_cache")]
        ])
    )


async def handle_cache_clear_search(query: CallbackQuery):
    await cache_clear("web_search")
    await query.edit_message_text(
        "✅ کش جستجو پاک شد.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_cache")]
        ])
    )


# ===== 📢 ارسال همگانی =====
async def start_broadcast(query: CallbackQuery):
    await query.edit_message_text(
        "📢 **ارسال همگانی**\n\n"
        "لطفاً پیام خود را بنویسید. این پیام به همه کاربران ارسال می‌شود.\n\n"
        "برای لغو، /cancel را بفرستید.",
        parse_mode=ParseMode.MARKDOWN,
    )
    # اینجا باید یه حالت انتظار برای پیام بعدی داشته باشیم
    # که در bot.py با ConversationHandler پیاده می‌شود


# ===== ⚙️ تنظیمات =====
async def show_settings(query: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton("📊 تغییر محدودیت روزانه", callback_data="admin_settings_limit")],
        [InlineKeyboardButton("🤖 تغییر مدل AI", callback_data="admin_settings_model")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ]
    
    text = f"""⚙️ **تنظیمات ربات**

📊 محدودیت روزانه: `{config.DAILY_MESSAGE_LIMIT}` پیام
🤖 مدل فعلی: `{AI_MODEL}`
🌐 سرویس: `{AI_PROVIDER}`"""
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_limit_change(query: CallbackQuery, new_limit: int):
    """
    تغییر محدودیت روزانه در حافظه‌ی پردازش فعلی.
    توجه: این تغییر با ری‌استارت شدن ربات از بین می‌رود؛ برای ماندگاری
    باید متغیر محیطی DAILY_MESSAGE_LIMIT را در .env هم به‌روزرسانی کنید.
    """
    config.DAILY_MESSAGE_LIMIT = new_limit
    await query.edit_message_text(
        f"✅ محدودیت روزانه به `{new_limit}` پیام تغییر کرد.\n\n"
        f"⚠️ توجه: این تغییر تا ری‌استارت بعدی ربات پابرجاست. برای ماندگاری، "
        f"مقدار `DAILY_MESSAGE_LIMIT` را در فایل `.env` هم به‌روز کنید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_settings")]
        ])
    )


async def show_limit_options(query: CallbackQuery):
    keyboard = [
        [
            InlineKeyboardButton("25", callback_data="admin_limit_25"),
            InlineKeyboardButton("50", callback_data="admin_limit_50"),
            InlineKeyboardButton("100", callback_data="admin_limit_100"),
        ],
        [
            InlineKeyboardButton("200", callback_data="admin_limit_200"),
            InlineKeyboardButton("500", callback_data="admin_limit_500"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_settings")],
    ]
    
    await query.edit_message_text(
        "📊 محدودیت روزانه جدید را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ===== 🔙 بازگشت به منوی اصلی =====
async def show_main_menu(query: CallbackQuery):
    keyboard = [
        [
            InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"),
            InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("🗂️ مدیریت کش", callback_data="admin_cache"),
            InlineKeyboardButton("📢 همگانی", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings"),
        ],
    ]
    
    await query.edit_message_text(
        "🤖 **پنل مدیریت ادمین**\n\ng یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )
