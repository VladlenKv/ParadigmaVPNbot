import httpx
from aiogram.types import User as TelegramUser

from app.config import Settings


class SiteApiError(RuntimeError):
    pass


class SiteApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def link_telegram(self, token: str, telegram_user: TelegramUser) -> None:
        if not self._settings.site_api_base_url:
            raise SiteApiError("Site API base URL is not configured")
        secret = self._settings.telegram_auth_secret.get_secret_value()
        if not secret:
            raise SiteApiError("Telegram auth secret is not configured")

        async with httpx.AsyncClient(
            base_url=str(self._settings.site_api_base_url).rstrip("/"),
            timeout=httpx.Timeout(15.0),
        ) as client:
            response = await client.post(
                "/api/internal/telegram/link",
                headers={"x-telegram-auth-secret": secret},
                json={
                    "token": token,
                    "telegramId": telegram_user.id,
                    "telegramUsername": telegram_user.username,
                    "firstName": telegram_user.first_name,
                    "lastName": telegram_user.last_name,
                },
            )

        if response.status_code == 404:
            raise SiteApiError("Link expired")
        if response.status_code == 409:
            raise SiteApiError("Telegram account is already linked")
        if response.is_error:
            raise SiteApiError(f"Site API returned HTTP {response.status_code}")
