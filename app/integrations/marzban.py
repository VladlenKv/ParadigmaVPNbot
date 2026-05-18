import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import Settings


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
        return await self._request("POST", "/api/user", json=self._user_body(payload))

    async def get_user(self, username: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/user/{username}")

    async def update_user(self, username: str, payload: MarzbanUserPayload) -> dict[str, Any]:
        return await self._request("PUT", f"/api/user/{username}", json=self._user_body(payload))

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
        body: dict[str, Any] = {
            "username": payload.username,
            "status": payload.status,
            "note": payload.note,
            "proxies": {"vless": {}},
            "data_limit_reset_strategy": "no_reset",
        }
        if payload.expire_at:
            body["expire"] = int(payload.expire_at.astimezone(UTC).timestamp())
        if payload.data_limit_bytes:
            body["data_limit"] = payload.data_limit_bytes
        if self._settings.marzban_default_proxy_inbounds:
            body["inbounds"] = json.loads(self._settings.marzban_default_proxy_inbounds)
        return body