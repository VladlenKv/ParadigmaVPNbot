import httpx
from aiogram.types import User as TelegramUser

from app.config import Settings
from app.db.models import Subscription


class SiteApiError(RuntimeError):
    pass


class SiteApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def link_telegram(self, token: str, telegram_user: TelegramUser) -> None:
        await self._post_telegram_user("/api/internal/telegram/link", token, telegram_user)

    async def confirm_telegram_login(self, token: str, telegram_user: TelegramUser) -> None:
        await self._post_telegram_user("/api/internal/telegram/login", token, telegram_user)

    async def get_bot_settings(self) -> dict:
        response = await self._request("GET", "/api/internal/bot/settings")
        self._raise_for_response(response)
        return response.json().get("settings", {})

    async def log_event(
        self,
        event_type: str,
        telegram_id: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        response = await self._request(
            "POST",
            "/api/internal/bot/events",
            json={
                "telegramId": telegram_id,
                "eventType": event_type,
                "metadata": metadata or {},
            },
        )
        self._raise_for_response(response)

    async def sync_subscription(
        self,
        telegram_user: TelegramUser,
        subscription: Subscription,
        *,
        is_free: bool,
        created_by: str = "bot",
    ) -> None:
        response = await self._request(
            "POST",
            "/api/internal/bot/subscription-sync",
            json={
                "telegramId": telegram_user.id,
                "telegramUsername": telegram_user.username,
                "firstName": telegram_user.first_name,
                "lastName": telegram_user.last_name,
                "status": subscription.status,
                "type": "vpn",
                "startsAt": subscription.starts_at.isoformat() if subscription.starts_at else None,
                "expiresAt": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "isFree": is_free,
                "createdBy": created_by,
                "trafficLimitBytes": subscription.traffic_limit_bytes,
                "trafficUsedBytes": subscription.last_traffic_used_bytes,
                "marzbanUsername": subscription.marzban_username,
                "sourceSubscriptionId": str(subscription.id),
                "configUrl": subscription.subscription_url,
                "configStatus": "active" if subscription.subscription_url else "failed",
                "issuedAt": subscription.updated_at.isoformat() if subscription.updated_at else None,
            },
        )
        self._raise_for_response(response)

    async def _post_telegram_user(self, path: str, token: str, telegram_user: TelegramUser) -> None:
        response = await self._request(
            "POST",
            path,
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
        self._raise_for_response(response)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self._settings.site_api_base_url:
            raise SiteApiError("Site API base URL is not configured")
        secret = self._settings.telegram_auth_secret.get_secret_value()
        if not secret:
            raise SiteApiError("Telegram auth secret is not configured")

        async with httpx.AsyncClient(
            base_url=str(self._settings.site_api_base_url).rstrip("/"),
            timeout=httpx.Timeout(15.0),
        ) as client:
            headers = kwargs.pop("headers", {})
            response = await client.request(
                method,
                path,
                headers={"x-telegram-auth-secret": secret, **headers},
                **kwargs,
            )

        return response

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_error:
            raise SiteApiError(f"Site API returned HTTP {response.status_code}")
