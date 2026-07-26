"""
یک سرور وب سبک (aiohttp) که هم کالبک زرین‌پال و هم پنل ادمین را سرو می‌کند.
"""
from aiohttp import web
from telegram import Bot

from config import SUBSCRIPTION_DAYS, SUBSCRIPTION_PRICE_TOMAN
from payment import verify_payment
from database import get_payment_by_authority, mark_payment_verified, activate_subscription
from admin_panel import setup_admin_routes


def create_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot  # برای استفاده در broadcast

    async def handle_callback(request: web.Request):
        authority = request.query.get("Authority")
        status = request.query.get("Status")
        user_id = request.query.get("user_id")

        if not authority or status != "OK":
            return web.Response(text="پرداخت لغو شد یا ناموفق بود.", content_type="text/html; charset=utf-8")

        payment_row = get_payment_by_authority(authority)
        if not payment_row:
            return web.Response(text="تراکنش یافت نشد.", status=404)

        success, ref_id_or_error = await verify_payment(authority, SUBSCRIPTION_PRICE_TOMAN)

        if success:
            mark_payment_verified(authority)
            activate_subscription(int(user_id), SUBSCRIPTION_DAYS)
            await bot.send_message(
                chat_id=int(user_id),
                text=(
                    f"✅ پرداخت با موفقیت انجام شد!\n"
                    f"کد پیگیری: {ref_id_or_error}\n"
                    f"اشتراک شما برای {SUBSCRIPTION_DAYS} روز فعال شد. 🎉"
                ),
            )
            return web.Response(
                text="پرداخت موفق بود ✅ می‌تونید به ربات تلگرام برگردید.",
                content_type="text/html; charset=utf-8",
            )
        else:
            await bot.send_message(
                chat_id=int(user_id),
                text=f"❌ پرداخت ناموفق بود: {ref_id_or_error}",
            )
            return web.Response(
                text=f"پرداخت ناموفق بود: {ref_id_or_error}",
                content_type="text/html; charset=utf-8",
            )

    app.router.add_get("/payment/callback", handle_callback)

    # اضافه کردن مسیرهای پنل ادمین
    setup_admin_routes(app)

    return app