"""
پنل مدیریت وب برای ربات
آدرس: /admin
"""
import hmac
import hashlib
import time
from aiohttp import web
from telegram import Bot

from config import ADMIN_PASSWORD, ADMIN_SECRET_KEY, SUBSCRIPTION_DAYS, SUBSCRIPTION_PRICE_TOMAN
from database import (
    get_stats,
    get_all_users,
    get_user,
    get_today_usage,
    get_user_free_limit,
    set_user_custom_free_messages,
    activate_subscription,
    deactivate_subscription,
    get_payments,
    get_setting,
    set_setting,
    get_free_daily_messages_global,
    get_user_ids_for_broadcast,
    get_user_messages,
)


# ==================== احراز هویت ساده ====================

def _make_token() -> str:
    raw = f"{ADMIN_PASSWORD}:{int(time.time() // 3600)}"
    return hmac.new(ADMIN_SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _check_auth(request: web.Request) -> bool:
    token = request.cookies.get("admin_token")
    return token == _make_token()


def _require_auth(handler):
    async def wrapper(request: web.Request):
        if not _check_auth(request):
            raise web.HTTPFound("/admin/login")
        return await handler(request)
    return wrapper


# ==================== قالب HTML پایه ====================

BASE_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} | پنل مدیریت ربات</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <style>
        body {{ background: #f0f2f5; font-family: Tahoma, sans-serif; }}
        .sidebar {{ min-height: 100vh; background: #1e293b; }}
        .sidebar a {{ color: #cbd5e1; text-decoration: none; display: block; padding: 12px 20px; }}
        .sidebar a:hover, .sidebar a.active {{ background: #334155; color: white; }}
        .card {{ border: none; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .stat-card {{ border-right: 4px solid; }}
    </style>
</head>
<body>
<div class="container-fluid">
    <div class="row">
        {sidebar}
        <div class="col-md-10 p-4">
            {content}
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

SIDEBAR = """
<div class="col-md-2 sidebar p-0">
    <div class="p-3 text-white fw-bold fs-5 border-bottom border-secondary">پنل مدیریت</div>
    <a href="/admin" class="{dashboard_active}">📊 داشبورد</a>
    <a href="/admin/users" class="{users_active}">👥 کاربران</a>
    <a href="/admin/payments" class="{payments_active}">💳 پرداخت‌ها</a>
    <a href="/admin/settings" class="{settings_active}">⚙️ تنظیمات</a>
    <a href="/admin/broadcast" class="{broadcast_active}">📢 پیام همگانی</a>
    <a href="/admin/logout" class="text-danger">خروج</a>
</div>
"""


def render(title: str, content: str, active: str = "dashboard"):
    sidebar = SIDEBAR.format(
        dashboard_active="active" if active == "dashboard" else "",
        users_active="active" if active == "users" else "",
        payments_active="active" if active == "payments" else "",
        settings_active="active" if active == "settings" else "",
        broadcast_active="active" if active == "broadcast" else "",
    )
    return BASE_HTML.format(title=title, sidebar=sidebar, content=content)


# ==================== صفحات ====================

async def login_page(request: web.Request):
    if _check_auth(request):
        raise web.HTTPFound("/admin")

    error = ""
    if request.method == "POST":
        data = await request.post()
        if data.get("password") == ADMIN_PASSWORD:
            resp = web.HTTPFound("/admin")
            resp.set_cookie("admin_token", _make_token(), max_age=3600 * 12, httponly=True)
            return resp
        error = '<div class="alert alert-danger">رمز عبور اشتباه است</div>'

    html = f"""
    <div class="row justify-content-center mt-5">
        <div class="col-md-4">
            <div class="card p-4">
                <h4 class="mb-3 text-center">ورود به پنل مدیریت</h4>
                {error}
                <form method="post">
                    <div class="mb-3">
                        <label class="form-label">رمز عبور</label>
                        <input type="password" name="password" class="form-control" required autofocus>
                    </div>
                    <button class="btn btn-primary w-100">ورود</button>
                </form>
            </div>
        </div>
    </div>
    """
    return web.Response(text=BASE_HTML.format(title="ورود", sidebar="", content=html), content_type="text/html")


@_require_auth
async def dashboard(request: web.Request):
    stats = get_stats()
    content = f"""
    <h3 class="mb-4">داشبورد</h3>
    <div class="row g-3">
        <div class="col-md-3">
            <div class="card p-3 stat-card" style="border-color:#3b82f6">
                <div class="text-muted small">کل کاربران</div>
                <div class="fs-3 fw-bold">{stats['total_users']}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 stat-card" style="border-color:#10b981">
                <div class="text-muted small">مشترکین فعال</div>
                <div class="fs-3 fw-bold">{stats['active_subs']}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 stat-card" style="border-color:#f59e0b">
                <div class="text-muted small">پیام‌های امروز</div>
                <div class="fs-3 fw-bold">{stats['today_messages']}</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card p-3 stat-card" style="border-color:#8b5cf6">
                <div class="text-muted small">درآمد کل (تومان)</div>
                <div class="fs-3 fw-bold">{stats['total_revenue']:,}</div>
            </div>
        </div>
    </div>
    <div class="row g-3 mt-2">
        <div class="col-md-3">
            <div class="card p-3">
                <div class="text-muted small">درآمد امروز</div>
                <div class="fs-4 fw-bold text-success">{stats['today_revenue']:,} تومان</div>
            </div>
        </div>
    </div>
    """
    return web.Response(text=render("داشبورد", content, "dashboard"), content_type="text/html")


@_require_auth
async def users_page(request: web.Request):
    search = request.query.get("q", "")
    only_sub = request.query.get("sub") == "1"
    users = get_all_users(limit=100, search=search or None, only_subscribed=only_sub)

    rows = ""
    for u in users:
        sub_badge = '<span class="badge bg-success">فعال</span>' if u["is_subscribed"] else '<span class="badge bg-secondary">ندارد</span>'
        rows += f"""
        <tr>
            <td><a href="/admin/user/{u['user_id']}">{u['user_id']}</a></td>
            <td>{u['username'] or '-'}</td>
            <td>{u['first_name'] or '-'}</td>
            <td>{sub_badge}</td>
            <td>{u['joined_at'][:10] if u['joined_at'] else '-'}</td>
            <td><a href="/admin/user/{u['user_id']}" class="btn btn-sm btn-outline-primary">مدیریت</a></td>
        </tr>
        """

    content = f"""
    <h3 class="mb-4">مدیریت کاربران</h3>
    <form class="row g-2 mb-3">
        <div class="col-auto">
            <input type="text" name="q" value="{search}" class="form-control" placeholder="جستجو آیدی / یوزرنیم / نام">
        </div>
        <div class="col-auto">
            <select name="sub" class="form-select">
                <option value="">همه</option>
                <option value="1" {"selected" if only_sub else ""}>فقط مشترکین</option>
            </select>
        </div>
        <div class="col-auto">
            <button class="btn btn-primary">فیلتر</button>
        </div>
    </form>
    <div class="card">
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>آیدی</th>
                    <th>یوزرنیم</th>
                    <th>نام</th>
                    <th>اشتراک</th>
                    <th>تاریخ عضویت</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>{rows or '<tr><td colspan="6" class="text-center text-muted">کاربری یافت نشد</td></tr>'}</tbody>
        </table>
    </div>
    """
    return web.Response(text=render("کاربران", content, "users"), content_type="text/html")


@_require_auth
async def user_detail(request: web.Request):
    user_id = int(request.match_info["user_id"])
    user = get_user(user_id)
    if not user:
        return web.Response(text="کاربر یافت نشد", status=404)

    usage = get_today_usage(user_id)
    free_limit = get_user_free_limit(user_id)
    custom_limit = user["custom_free_messages"]

    if request.method == "POST":
        data = await request.post()
        action = data.get("action")

        if action == "activate":
            days = int(data.get("days", SUBSCRIPTION_DAYS))
            activate_subscription(user_id, days)
        elif action == "deactivate":
            deactivate_subscription(user_id)
        elif action == "set_limit":
            limit_val = data.get("limit", "").strip()
            if limit_val == "":
                set_user_custom_free_messages(user_id, None)
            else:
                set_user_custom_free_messages(user_id, int(limit_val))

        raise web.HTTPFound(f"/admin/user/{user_id}")

    sub_status = "فعال" if user["is_subscribed"] else "غیرفعال"
    expires = user["subscription_expires_at"][:16].replace("T", " ") if user["subscription_expires_at"] else "-"

    # تاریخچه پیام‌ها
    messages = get_user_messages(user_id, limit=40)
    messages = list(reversed(messages))

    history_html = ""
    for msg in messages:
        role_label = "کاربر" if msg["role"] == "user" else "ربات"
        role_class = "text-primary" if msg["role"] == "user" else "text-success"
        time_str = msg["created_at"][:16].replace("T", " ") if msg["created_at"] else ""
        content_safe = msg["content"].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

        history_html += f"""
        <div class="border-bottom py-2">
            <div class="d-flex justify-content-between">
                <strong class="{role_class}">{role_label}</strong>
                <small class="text-muted">{time_str}</small>
            </div>
            <div class="mt-1">{content_safe}</div>
        </div>
        """

    content = f"""
    <h3 class="mb-3">کاربر {user_id}</h3>
    <div class="row g-3">
        <div class="col-md-6">
            <div class="card p-3">
                <h5>اطلاعات کلی</h5>
                <p><b>آیدی:</b> {user['user_id']}</p>
                <p><b>یوزرنیم:</b> @{user['username'] or '-'}</p>
                <p><b>نام:</b> {user['first_name'] or '-'}</p>
                <p><b>تاریخ عضویت:</b> {user['joined_at'][:16].replace('T', ' ') if user['joined_at'] else '-'}</p>
                <p><b>وضعیت اشتراک:</b> {sub_status}</p>
                <p><b>انقضا:</b> {expires}</p>
                <p><b>مصرف امروز:</b> {usage} از {free_limit}</p>
                <p><b>محدودیت اختصاصی:</b> {custom_limit if custom_limit is not None else 'ندارد (سراسری)'}</p>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card p-3 mb-3">
                <h5>مدیریت اشتراک</h5>
                <form method="post" class="mb-2">
                    <input type="hidden" name="action" value="activate">
                    <div class="input-group">
                        <input type="number" name="days" value="{SUBSCRIPTION_DAYS}" class="form-control" min="1">
                        <button class="btn btn-success">فعال‌سازی اشتراک (روز)</button>
                    </div>
                </form>
                <form method="post">
                    <input type="hidden" name="action" value="deactivate">
                    <button class="btn btn-outline-danger w-100">لغو اشتراک</button>
                </form>
            </div>
            <div class="card p-3">
                <h5>تنظیم پیام رایگان این کاربر</h5>
                <form method="post">
                    <input type="hidden" name="action" value="set_limit">
                    <div class="input-group">
                        <input type="number" name="limit" value="{custom_limit if custom_limit is not None else ''}" 
                               class="form-control" placeholder="خالی = سراسری" min="0">
                        <button class="btn btn-primary">ذخیره</button>
                    </div>
                    <div class="form-text">اگر خالی بذاری، از مقدار سراسری استفاده می‌شه</div>
                </form>
            </div>
        </div>
    </div>

    <div class="card p-3 mt-4">
        <h5 class="mb-3">تاریخچه مکالمات (آخرین ۴۰ پیام)</h5>
        <div style="max-height: 500px; overflow-y: auto;">
            {history_html if history_html else '<p class="text-muted">هنوز پیامی ثبت نشده</p>'}
        </div>
    </div>

    <a href="/admin/users" class="btn btn-secondary mt-3">← بازگشت</a>
    """
    return web.Response(text=render(f"کاربر {user_id}", content, "users"), content_type="text/html")


@_require_auth
async def payments_page(request: web.Request):
    payments = get_payments(100)
    rows = ""
    for p in payments:
        status_badge = {
            "verified": '<span class="badge bg-success">موفق</span>',
            "pending": '<span class="badge bg-warning">در انتظار</span>',
        }.get(p["status"], f'<span class="badge bg-secondary">{p["status"]}</span>')
        rows += f"""
        <tr>
            <td>{p['id']}</td>
            <td><a href="/admin/user/{p['user_id']}">{p['user_id']}</a></td>
            <td>{p['amount']:,}</td>
            <td>{status_badge}</td>
            <td>{p['created_at'][:16].replace('T',' ') if p['created_at'] else '-'}</td>
            <td>{p['verified_at'][:16].replace('T',' ') if p['verified_at'] else '-'}</td>
        </tr>
        """

    content = f"""
    <h3 class="mb-4">لاگ پرداخت‌ها</h3>
    <div class="card">
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>#</th>
                    <th>کاربر</th>
                    <th>مبلغ (تومان)</th>
                    <th>وضعیت</th>
                    <th>تاریخ ایجاد</th>
                    <th>تاریخ تایید</th>
                </tr>
            </thead>
            <tbody>{rows or '<tr><td colspan="6" class="text-center text-muted">پرداختی وجود ندارد</td></tr>'}</tbody>
        </table>
    </div>
    """
    return web.Response(text=render("پرداخت‌ها", content, "payments"), content_type="text/html")


@_require_auth
async def settings_page(request: web.Request):
    current_free = get_free_daily_messages_global()
    message = ""

    if request.method == "POST":
        data = await request.post()
        new_free = data.get("free_daily_messages", "").strip()
        if new_free.isdigit():
            set_setting("free_daily_messages", new_free)
            message = '<div class="alert alert-success">تنظیمات ذخیره شد</div>'
            current_free = int(new_free)

    content = f"""
    <h3 class="mb-4">تنظیمات سراسری</h3>
    {message}
    <div class="card p-4" style="max-width:500px">
        <form method="post">
            <div class="mb-3">
                <label class="form-label">تعداد پیام رایگان روزانه (سراسری)</label>
                <input type="number" name="free_daily_messages" value="{current_free}" class="form-control" min="0" required>
                <div class="form-text">این مقدار برای کاربرانی اعمال می‌شه که محدودیت اختصاصی نداشته باشن</div>
            </div>
            <button class="btn btn-primary">ذخیره</button>
        </form>
    </div>
    """
    return web.Response(text=render("تنظیمات", content, "settings"), content_type="text/html")


@_require_auth
async def broadcast_page(request: web.Request):
    message = ""
    if request.method == "POST":
        data = await request.post()
        text = data.get("message", "").strip()
        only_sub = data.get("only_subscribed") == "1"
        if text:
            bot: Bot = request.app["bot"]
            user_ids = get_user_ids_for_broadcast(only_subscribed=only_sub)
            success = 0
            fail = 0
            for uid in user_ids:
                try:
                    await bot.send_message(chat_id=uid, text=text)
                    success += 1
                except Exception:
                    fail += 1
            message = f'<div class="alert alert-success">ارسال شد: {success} موفق، {fail} ناموفق</div>'

    content = f"""
    <h3 class="mb-4">پیام همگانی</h3>
    {message}
    <div class="card p-4" style="max-width:600px">
        <form method="post">
            <div class="mb-3">
                <label class="form-label">متن پیام</label>
                <textarea name="message" class="form-control" rows="5" required></textarea>
            </div>
            <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" name="only_subscribed" value="1" id="onlySub">
                <label class="form-check-label" for="onlySub">فقط به مشترکین فعال ارسال شود</label>
            </div>
            <button class="btn btn-warning" onclick="return confirm('آیا مطمئن هستید؟')">ارسال پیام</button>
        </form>
    </div>
    """
    return web.Response(text=render("پیام همگانی", content, "broadcast"), content_type="text/html")


async def logout(request: web.Request):
    resp = web.HTTPFound("/admin/login")
    resp.del_cookie("admin_token")
    return resp


def setup_admin_routes(app: web.Application):
    app.router.add_get("/admin/login", login_page)
    app.router.add_post("/admin/login", login_page)
    app.router.add_get("/admin", dashboard)
    app.router.add_get("/admin/users", users_page)
    app.router.add_get("/admin/user/{user_id}", user_detail)
    app.router.add_post("/admin/user/{user_id}", user_detail)
    app.router.add_get("/admin/payments", payments_page)
    app.router.add_get("/admin/settings", settings_page)
    app.router.add_post("/admin/settings", settings_page)
    app.router.add_get("/admin/broadcast", broadcast_page)
    app.router.add_post("/admin/broadcast", broadcast_page)
    app.router.add_get("/admin/logout", logout)