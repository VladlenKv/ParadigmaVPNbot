from datetime import UTC, datetime, timedelta

from app.db.models import Plan, Subscription, SubscriptionStatus, User
from app.integrations.marzban import (
    MarzbanClient,
    MarzbanError,
    MarzbanRequestError,
    MarzbanUserPayload,
)


def marzban_username_for(user: User, subscription_id: int | None = None) -> str:
    if subscription_id is None:
        return f"tg_{user.telegram_id}"
    return f"tg_{user.telegram_id}_{subscription_id}"


def gb_to_bytes(value: int | None) -> int | None:
    if value is None:
        return None
    return value * 1024 * 1024 * 1024


class MarzbanProvisioningService:
    def __init__(self, client: MarzbanClient) -> None:
        self._client = client

    async def provision(self, user: User, subscription: Subscription, plan: Plan) -> Subscription:
        now = datetime.now(UTC)
        base = (
            subscription.expires_at
            if subscription.expires_at and subscription.expires_at > now
            else now
        )
        starts_at = subscription.starts_at or now
        expires_at = base + timedelta(days=plan.duration_days)
        traffic_limit = gb_to_bytes(plan.traffic_limit_gb)
        username = subscription.marzban_username or marzban_username_for(user, subscription.id)
        fallback_username = marzban_username_for(user, subscription.id)
        usernames = [username]
        if not subscription.subscription_url:
            for candidate in (fallback_username, f"{fallback_username}_sync"):
                if candidate != username:
                    usernames.append(candidate)

        try:
            last_error: MarzbanError | None = None
            link = ""
            for candidate_username in usernames:
                payload = MarzbanUserPayload(
                    username=candidate_username,
                    expire_at=expires_at,
                    data_limit_bytes=traffic_limit,
                    note=f"Paradigma VPN Telegram user {user.telegram_id}",
                )
                try:
                    try:
                        await self._client.get_user(candidate_username)
                    except MarzbanRequestError as exc:
                        if exc.status_code != 404:
                            raise
                        try:
                            await self._client.create_user(payload)
                        except MarzbanRequestError as create_exc:
                            # Marzban can create the user and still answer 500.
                            # 409 means a retry found it.
                            if create_exc.status_code not in {409, 500}:
                                raise
                            await self._client.get_user(candidate_username)
                    await self._client.update_user(candidate_username, payload)
                    link = await self._client.get_subscription_link(candidate_username)
                    username = candidate_username
                    break
                except MarzbanError as exc:
                    last_error = exc
            else:
                if last_error:
                    raise last_error
                raise MarzbanError("Marzban provisioning failed")
        except MarzbanError:
            subscription.status = SubscriptionStatus.failed.value
            raise

        subscription.status = SubscriptionStatus.active.value
        subscription.marzban_username = username
        subscription.subscription_url = link
        subscription.starts_at = starts_at
        subscription.expires_at = expires_at
        subscription.traffic_limit_bytes = traffic_limit
        return subscription