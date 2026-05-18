import pytest

pytest.importorskip("sqlalchemy")

from app.bot.handlers.subscriptions import can_add_device  # noqa: E402
from app.db.models import Subscription, SubscriptionStatus  # noqa: E402
from app.services.subscriptions import MAX_ADDITIONAL_DEVICES  # noqa: E402


def test_can_add_device_until_limit() -> None:
    subscription = Subscription(
        status=SubscriptionStatus.active.value,
        marzban_username="tg_1",
        subscription_url="https://sub.example/tg_1",
        additional_devices_count=0,
    )

    assert can_add_device(subscription) is True

    subscription.additional_devices_count = MAX_ADDITIONAL_DEVICES

    assert can_add_device(subscription) is False


def test_cannot_add_device_without_active_subscription_url() -> None:
    subscription = Subscription(
        status=SubscriptionStatus.failed.value,
        marzban_username="tg_1",
        subscription_url=None,
        additional_devices_count=0,
    )

    assert can_add_device(subscription) is False