from datetime import UTC, datetime
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import back_keyboard, config_keyboard, subscription_keyboard
from app.bot.texts import ru
from app.config import Settings
from app.db.models import Plan, Subscription, SubscriptionStatus
from app.integrations.marzban import MarzbanClient, MarzbanError
from app.integrations.site_api import SiteApiClient, SiteApiError
from app.services.marzban_sync import MarzbanSyncService
from app.services.provisioning import MarzbanProvisioningService
from app.services.subscriptions import MAX_ADDITIONAL_DEVICES, SubscriptionService
from app.services.users import UserService

router = Router()


def _setting(settings: dict[str, Any], key: str, fallback: Any) -> Any:
    return settings.get(key) if settings.get(key) is not None else fallback


def _expires_text(subscription: Subscription) -> str:
    return subscription.expires_at.strftime("%d.%m.%Y") if subscription.expires_at else "не указано"


async def _sync_to_site(
    settings: Settings,
    telegram_user: Any,
    subscription: Subscription,
    *,
    is_free: bool,
    event_type: str,
) -> None:
    client = SiteApiClient(settings)
    try:
        await client.sync_subscription(telegram_user, subscription, is_free=is_free)
        await client.log_event(event_type, telegram_user.id, {"subscription_id": subscription.id})
    except SiteApiError:
        return


async def get_or_issue_config_for_user(
    telegram_user: TelegramUser,
    answer,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await UserService(session, settings).upsert_from_telegram(telegram_user)
    site_client = SiteApiClient(settings)
    try:
        bot_settings = await site_client.get_bot_settings()
    except SiteApiError:
        bot_settings = {}

    service = SubscriptionService(session, settings)
    subscription = await service.active_for_user(user)

    if subscription and subscription.subscription_url:
        await session.commit()
        await _sync_to_site(settings, telegram_user, subscription, is_free=subscription.plan_id is None, event_type="config.show_existing")
        await answer(
            ru.CONFIG_READY.format(
                expires_at=_expires_text(subscription),
                subscription_url=subscription.subscription_url,
            ),
            reply_markup=config_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if subscription and not subscription.subscription_url:
        client = MarzbanClient(settings)
        try:
            plan = Plan(
                code="free",
                title="Free",
                description="",
                price_amount=0,
                currency="RUB",
                duration_days=max(1, (subscription.expires_at - datetime.now(UTC)).days) if subscription.expires_at else 7,
                traffic_limit_gb=None,
                device_limit=1,
            )
            await MarzbanProvisioningService(client).provision(user, subscription, plan)
            await session.commit()
        except MarzbanError:
            await session.commit()
            await _sync_to_site(settings, telegram_user, subscription, is_free=True, event_type="config.issue_failed")
            await answer(ru.CONFIG_ISSUE_FAILED, reply_markup=back_keyboard())
            return
        finally:
            await client.aclose()

    if not subscription:
        free_enabled = bool(_setting(bot_settings, "freeSubscriptionsEnabled", settings.trial_enabled))
        auto_issue_enabled = bool(_setting(bot_settings, "configAutoIssueEnabled", True))
        if not free_enabled or not auto_issue_enabled:
            await session.commit()
            try:
                await site_client.log_event(
                    "config.issue_denied",
                    telegram_user.id,
                    {"free_enabled": free_enabled, "auto_issue_enabled": auto_issue_enabled},
                )
            except SiteApiError:
                pass
            await answer(
                _setting(bot_settings, "botSubscriptionExpiredMessage", ru.CONFIG_FREE_DISABLED),
                reply_markup=back_keyboard(),
            )
            return

        duration_days = int(_setting(bot_settings, "freeSubscriptionDurationDays", settings.trial_duration_days))
        traffic_gb = _setting(bot_settings, "freeSubscriptionTrafficGb", settings.trial_traffic_limit_gb)
        subscription = await service.create_free_subscription(user, duration_days, traffic_gb)
        client = MarzbanClient(settings)
        try:
            plan = Plan(
                code="free",
                title="Free",
                description="",
                price_amount=0,
                currency="RUB",
                duration_days=duration_days,
                traffic_limit_gb=traffic_gb,
                device_limit=1,
            )
            await MarzbanProvisioningService(client).provision(user, subscription, plan)
            await session.commit()
        except MarzbanError:
            subscription.status = SubscriptionStatus.failed.value
            await session.commit()
            await _sync_to_site(settings, telegram_user, subscription, is_free=True, event_type="config.issue_failed")
            await answer(ru.CONFIG_ISSUE_FAILED, reply_markup=back_keyboard())
            return
        finally:
            await client.aclose()

    await _sync_to_site(settings, telegram_user, subscription, is_free=subscription.plan_id is None, event_type="config.issued")
    await answer(
        ru.CONFIG_READY.format(
            expires_at=_expires_text(subscription),
            subscription_url=subscription.subscription_url or "ожидает выдачи",
        ),
        reply_markup=subscription_keyboard(
            bool(subscription.subscription_url),
            subscription.additional_devices_count < MAX_ADDITIONAL_DEVICES,
        ),
        disable_web_page_preview=True,
    )


@router.message(Command("config"))
async def config_command(message: Message, session: AsyncSession, settings: Settings) -> None:
    if not message.from_user:
        return
    await get_or_issue_config_for_user(message.from_user, message.answer, session, settings)


@router.callback_query(lambda call: call.data == "config:get")
async def config_callback(call: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if call.message:
        await call.answer()
        await get_or_issue_config_for_user(call.from_user, call.message.answer, session, settings)


@router.message(Command("profile"))
async def profile_command(message: Message, session: AsyncSession, settings: Settings) -> None:
    if not message.from_user:
        return
    user = await UserService(session, settings).upsert_from_telegram(message.from_user)
    subscription = await SubscriptionService(session, settings).active_for_user(user)
    if subscription:
        client = MarzbanClient(settings)
        try:
            await MarzbanSyncService(client).sync_subscription(subscription)
        except MarzbanError:
            pass
        finally:
            await client.aclose()
    await session.commit()
    await message.answer(
        ru.PROFILE_INFO.format(
            telegram_id=message.from_user.id,
            username=message.from_user.username or "-",
            status=subscription.status if subscription else "no_subscription",
            expires_at=_expires_text(subscription) if subscription else "-",
            config_status="active" if subscription and subscription.subscription_url else "missing",
        ),
        reply_markup=config_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message, settings: Settings) -> None:
    await message.answer(ru.HELP_TEXT.format(support_url=settings.support_url), reply_markup=back_keyboard())
