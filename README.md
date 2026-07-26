# ربات تلگرامی هوش مصنوعی با اشتراک پولی (زرین‌پال)

## قابلیت‌ها
- پاسخ‌دهی هوش مصنوعی (OpenAI / Anthropic / هر reseller سازگار با OpenAI)
- محدودیت پیام رایگان روزانه برای کاربران غیرمشترک
- خرید اشتراک از طریق درگاه زرین‌پال
- فعال‌سازی خودکار اشتراک بعد از پرداخت موفق
- حافظه‌ی مکالمه (context) برای هر کاربر

## پیش‌نیازها
1. یک سرور (VPS) **خارج از ایران** برای اجرای ربات — چون OpenAI و Anthropic دسترسی مستقیم از IP ایران را مسدود می‌کنند.
   - جایگزین: استفاده از یک reseller ایرانی (مثل metisai.ir یا مشابه) که خودش دسترسی به مدل‌ها را فراهم می‌کند؛ در این حالت لازم نیست سرور خارج از ایران باشد.
2. توکن ربات تلگرام از [@BotFather](https://t.me/BotFather)
3. حساب merchant در [زرین‌پال](https://www.zarinpal.com) (برای تست از حالت sandbox استفاده کنید)
4. دامنه با HTTPS برای دریافت کالبک پرداخت (می‌توانید از nginx + certbot استفاده کنید)

## نصب

```bash
git clone <this-project>
cd telegram_ai_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env را با اطلاعات خودتان پر کنید
```

## اجرا

```bash
python bot.py
```

این دستور همزمان:
- ربات تلگرام را با polling اجرا می‌کند
- یک سرور کوچک aiohttp روی پورت `WEBHOOK_PORT` بالا می‌آورد که کالبک زرین‌پال را می‌گیرد

## تنظیم Nginx برای کالبک (نمونه)

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    location /payment/callback {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

سپس در `.env`:
```
CALLBACK_BASE_URL=https://yourdomain.com
```

## اجرای دائمی با systemd (پیشنهادی)

فایل `/etc/systemd/system/aibot.service`:
```ini
[Unit]
Description=Telegram AI Bot
After=network.target

[Service]
WorkingDirectory=/path/to/telegram_ai_bot
ExecStart=/path/to/telegram_ai_bot/venv/bin/python bot.py
Restart=always
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable aibot
sudo systemctl start aibot
```

## ساختار پروژه

| فایل | توضیح |
|---|---|
| `bot.py` | نقطه‌ی ورود؛ دستورات تلگرام و اجرای همزمان سرور کالبک |
| `ai_service.py` | لایه‌ی انتزاعی هوش مصنوعی (OpenAI/Anthropic) + حافظه‌ی مکالمه |
| `payment.py` | ایجاد و تایید تراکنش زرین‌پال |
| `webhook_server.py` | دریافت کالبک پرداخت و فعال‌سازی اشتراک |
| `database.py` | مدیریت SQLite (کاربران، پرداخت‌ها، مصرف روزانه) |
| `config.py` | خواندن تنظیمات از `.env` |

## نکات مهم امنیتی و عملیاتی
- **هرگز** `.env` را در گیت commit نکنید.
- مبلغ تایید پرداخت را همیشه از سمت سرور خودتان (نه کلاینت) محاسبه کنید — این کد همین کار را می‌کند.
- برای مقیاس بزرگ‌تر، حافظه‌ی مکالمه را از حافظه‌ی RAM به Redis منتقل کنید (الان با ری‌استارت ربات پاک می‌شود).
- می‌توانید `FREE_DAILY_MESSAGES`, `SUBSCRIPTION_PRICE_TOMAN`, `SUBSCRIPTION_DAYS` را در `.env` تغییر دهید.

## توسعه‌های پیشنهادی بعدی
- پنل ادمین برای مشاهده‌ی کاربران و درآمد
- ارسال یادآوری قبل از انقضای اشتراک
- پشتیبانی از چند سطح اشتراک (Basic/Pro)
- Rate limiting بیشتر برای جلوگیری از سو استفاده
