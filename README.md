# Paradigma VPN

Telegram bot and FastAPI backend for selling and issuing VPN subscriptions through Marzban.

## Stack

- Python 3.12
- FastAPI
- aiogram 3
- SQLAlchemy 2 async
- Alembic
- PostgreSQL
- Redis placeholder for cache/FSM/rate limits
- httpx Marzban API client

## Local Run

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app alembic upgrade head
```

Fill `.env` before using the bot:

- `BOT_TOKEN`
- `WEBHOOK_SECRET`
- `ADMIN_TELEGRAM_IDS`
- `MARZBAN_BASE_URL`
- `MARZBAN_USERNAME`
- `MARZBAN_PASSWORD`
- public/support/legal URLs

Health endpoint:

```bash
curl http://localhost:8000/health
```

Telegram webhook path defaults to `/telegram/webhook`. Set it in Telegram with the secret token from `WEBHOOK_SECRET`.

## Site Sync

Set these variables in the bot `.env` to synchronize Telegram users, issued subscriptions, and config URLs with the site:

- `SITE_API_BASE_URL`: public site API URL, for example `https://95.181.167.201.sslip.io:8888`.
- `TELEGRAM_AUTH_SECRET`: the same value as in the site API `.env`.

The bot reads DB-backed site settings through `GET /api/internal/bot/settings` and writes issued Marzban configs through `POST /api/internal/bot/subscription-sync`. Users can run `/config` or press “Получить конфигурацию” to receive a temporary free config when free mode is enabled in the site admin panel.

## Manual Payments MVP

## Site Telegram Login

The site login button creates a one-time auth token and opens the bot with `/start auth_<token>`. The bot confirms the token through `POST /api/internal/telegram/auth-confirm`; it does not mark tokens as used. The site frontend polls `GET /api/auth/telegram/status/:tokenId` and calls `POST /api/auth/telegram/complete` after confirmation, which creates the site session cookie.

Required shared settings:

- `SITE_API_BASE_URL`: public site API URL.
- `TELEGRAM_AUTH_SECRET`: the same value as the site API `.env`.

The first provider is `manual`:

1. User selects a tariff.
2. Bot creates a pending payment.
3. Admin confirms it with `/confirm_payment <payment_id>`.
4. Backend creates or updates the Marzban user and stores the subscription link.

## Tests

```bash
python -m compileall app
pytest
ruff check .
```
