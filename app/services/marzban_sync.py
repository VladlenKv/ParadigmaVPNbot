from datetime import UTC, datetime
from typing import Any

from app.db.models import Subscription, SubscriptionStatus
from app.integrations.marzban import MarzbanClient, MarzbanRequestError


def _timestamp_to_datetime(value: Any) -> datetime | None:
    if value in (None, 0, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _int_from_user(user_data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = user_data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _status_from_marzban(value: Any) -> str:
    status = str(value or "").lower()
    if status == "active":
        return SubscriptionStatus.active.value
    if status in {"expired", "limited"}:
        return SubscriptionStatus.expired.value
    if status in {"disabled", "on_hold"}:
        return SubscriptionStatus.cancelled.value
    return SubscriptionStatus.failed.value


class MarzbanSyncService:
    def __init__(self, client: MarzbanClient) -> None:
        self._client = client

    async def sync_subscription(self, subscription: Subscription) -> bool:
        try:
            user_data = await self._client.get_user(subscription.marzban_username)
        except MarzbanRequestError as exc:
            if exc.status_code == 404:
                subscription.status = SubscriptionStatus.failed.value
                return False
            raise

        subscription.status = _status_from_marzban(user_data.get("status"))
        subscription.subscription_url = (
            user_data.get("subscription_url")
            or user_data.get("subscription_link")
            or subscription.subscription_url
        )
        subscription.expires_at = (
            _timestamp_to_datetime(user_data.get("expire")) or subscription.expires_at
        )
        data_limit = _int_from_user(user_data, "data_limit")
        subscription.traffic_limit_bytes = None if data_limit in (None, 0) else data_limit
        subscription.last_traffic_used_bytes = (
            _int_from_user(
                user_data,
                "used_traffic",
                "lifetime_used_traffic",
                "usedTraffic",
                "data_used",
            )
            or subscription.last_traffic_used_bytes
            or 0
        )
        return True
