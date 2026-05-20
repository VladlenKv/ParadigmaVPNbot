import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class MarzbanError(RuntimeError):
    pass


class MarzbanAuthError(MarzbanError):
    pass


class MarzbanRequestError(MarzbanError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MarzbanUserPayload:
    username: str
    expire_at: datetime | None
    data_limit_bytes: int | None
    note: str
    status: str = "active"


class MarzbanClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=self._normalize_base_url(str(settings.marzban_base_url)),
            verify=settings.marzban_verify_ssl,
            timeout=httpx.Timeout(15.0),
        )
        self._access_token: str | None = None
        self._validated_default_inbounds: dict[str, list[str]] | None = None

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        parsed = urlsplit(value)
        path = parsed.path.rstrip("/")
        if path.endswith("/dashboard"):
            path = path[: -len("/dashboard")]
        elif path == "dashboard":
            path = ""
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def authenticate(self) -> None:
        response = await self._client.post(
            "/api/admin/token",
            data={
                "username": self._settings.marzban_username,
                "password": self._settings.marzban_password.get_secret_value(),
            },
        )
        if response.status_code in {401, 403}:
            raise MarzbanAuthError("Marzban authentication failed")
        if response.is_error:
            raise MarzbanRequestError(f"Marzban auth returned HTTP {response.status_code}")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise MarzbanAuthError("Marzban auth response has no access_token")
        self._access_token = token

    async def create_user(self, payload: MarzbanUserPayload) -> dict[str, Any]:
        await self._ensure_default_inbounds_exist()
        return await self._request("POST", "/api/user", json=self._user_body(payload))

    async def get_user(self, username: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/user/{username}")

    async def update_user(self, username: str, payload: MarzbanUserPayload) -> dict[str, Any]:
        await self._ensure_default_inbounds_exist()
        return await self._request("PUT", f"/api/user/{username}", json=self._user_body(payload))

    async def get_inbounds(self) -> dict[str, list[dict[str, Any]]]:
        return await self._request("GET", "/api/inbounds")

    async def disable_user(self, username: str) -> dict[str, Any]:
        return await self._request("PUT", f"/api/user/{username}", json={"status": "disabled"})

    async def revoke_user(self, username: str) -> dict[str, Any]:
        return await self.disable_user(username)

    async def get_subscription_link(self, username: str) -> str:
        user = await self.get_user(username)
        link = user.get("subscription_url") or user.get("subscription_link")
        if not link:
            raise MarzbanRequestError("Marzban user response has no subscription link")
        return str(link)

    async def get_user_usage(self, username: str) -> dict[str, Any]:
        return await self.get_user(username)

    async def reset_user_traffic(self, username: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/user/{username}/reset")

    async def healthcheck(self) -> bool:
        try:
            await self._request("GET", "/api/system")
        except MarzbanError:
            return False
        return True

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self._access_token:
            await self.authenticate()

        for attempt in range(3):
            try:
                response = await self._client.request(
                    method,
                    path,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    **kwargs,
                )
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise MarzbanRequestError("Temporary Marzban transport error") from exc
                await asyncio.sleep(0.2 * (2**attempt))
                continue

            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                await self.authenticate()
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await asyncio.sleep(0.2 * (2**attempt))
                continue
            if response.is_error:
                raise MarzbanRequestError(
                    f"Marzban request failed with HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            if not response.content:
                return {}
            return response.json()

        raise MarzbanRequestError("Marzban request retries exhausted")

    def _user_body(self, payload: MarzbanUserPayload) -> dict[str, Any]:
        inbounds = self._default_inbounds()
        body: dict[str, Any] = {
            "username": payload.username,
            "status": payload.status,
            "note": payload.note,
            "proxies": {"vless": {}},
            "inbounds": inbounds,
            "data_limit_reset_strategy": "no_reset",
        }
        if payload.expire_at:
            body["expire"] = int(payload.expire_at.astimezone(UTC).timestamp())
        if payload.data_limit_bytes is not None:
            body["data_limit"] = payload.data_limit_bytes
        return body

    def _default_inbounds(self) -> dict[str, list[str]]:
        raw = self._settings.marzban_default_inbounds or self._settings.marzban_default_proxy_inbounds
        if not raw:
            raise MarzbanError("MARZBAN_DEFAULT_INBOUNDS is not configured")

        raw = raw.strip()
        if raw.startswith("{"):
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise MarzbanError("MARZBAN_DEFAULT_INBOUNDS JSON must be an object")
            inbounds = {
                str(protocol): [str(tag) for tag in tags if str(tag).strip()]
                for protocol, tags in parsed.items()
                if isinstance(tags, list)
            }
        else:
            tags = [tag.strip() for tag in raw.split(",") if tag.strip()]
            inbounds = {"vless": tags}

        if not any(inbounds.values()):
            raise MarzbanError("MARZBAN_DEFAULT_INBOUNDS has no inbound tags")
        return inbounds

    async def _ensure_default_inbounds_exist(self) -> None:
        expected = self._default_inbounds()
        if self._validated_default_inbounds == expected:
            return

        available = await self.get_inbounds()
        missing: list[str] = []
        for protocol, tags in expected.items():
            available_tags = {
                str(inbound.get("tag"))
                for inbound in available.get(protocol, [])
                if inbound.get("tag")
            }
            missing.extend(f"{protocol}:{tag}" for tag in tags if tag not in available_tags)

        if missing:
            logger.error("Configured Marzban inbounds are missing: %s", ", ".join(missing))
            raise MarzbanError(f"Configured Marzban inbounds are missing: {', '.join(missing)}")

        self._validated_default_inbounds = expected
