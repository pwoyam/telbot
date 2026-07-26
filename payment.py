"""
اتصال به درگاه زرین‌پال (Zarinpal) با استفاده از REST API نسخه‌ی 4
مستندات: https://docs.zarinpal.com
"""
import httpx

from config import ZARINPAL_MERCHANT_ID, ZARINPAL_SANDBOX, CALLBACK_BASE_URL

if ZARINPAL_SANDBOX:
    BASE_URL = "https://sandbox.zarinpal.com/pg/v4/payment"
    STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay"
else:
    BASE_URL = "https://payment.zarinpal.com/pg/v4/payment"
    STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay"


async def request_payment(amount_toman: int, user_id: int, description: str = "خرید اشتراک ربات"):
    """
    درخواست ایجاد تراکنش پرداخت.
    خروجی: (authority, payment_url) یا در صورت خطا (None, error_message)
    نکته: زرین‌پال مبلغ را به ریال می‌گیرد، پس ضرب‌در ۱۰ می‌کنیم.
    """
    payload = {
        "merchant_id": ZARINPAL_MERCHANT_ID,
        "amount": amount_toman * 10,  # تبدیل تومان به ریال
        "description": description,
        "callback_url": f"{CALLBACK_BASE_URL}/payment/callback?user_id={user_id}",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{BASE_URL}/request.json", json=payload)
        data = resp.json()

    if data.get("data") and data["data"].get("code") == 100:
        authority = data["data"]["authority"]
        payment_url = f"{STARTPAY_URL}/{authority}"
        return authority, payment_url

    error_msg = data.get("errors", {}).get("message", "خطای نامشخص در ایجاد تراکنش")
    return None, error_msg


async def verify_payment(authority: str, amount_toman: int):
    """
    تایید تراکنش پس از بازگشت کاربر از درگاه.
    خروجی: (success: bool, ref_id_or_error)
    """
    payload = {
        "merchant_id": ZARINPAL_MERCHANT_ID,
        "amount": amount_toman * 10,
        "authority": authority,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{BASE_URL}/verify.json", json=payload)
        data = resp.json()

    if data.get("data") and data["data"].get("code") in (100, 101):
        ref_id = data["data"].get("ref_id")
        return True, ref_id

    error_msg = data.get("errors", {}).get("message", "پرداخت تایید نشد")
    return False, error_msg
