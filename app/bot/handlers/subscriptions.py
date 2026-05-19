from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import back_keyboard, subscription_keyboard
from app.bot.texts import ru
from app.config import Settings
from app.db.models import SubscriptionStatus
from app.integrations.marzban import MarzbanClient, MarzbanError
from app.integrations.site_api import SiteApiClient, SiteApiError
from app.services.marzban_sync import MarzbanSyncService
from app.services.subscriptions import MAX_ADDITIONAL_DEVICES, SubscriptionService
from app.services.users import UserService

router = Router()


async def sync_subscription_from_marzban(
    subscription: Any,
    session: AsyncSession,
    settings: Settings,
) -> bool:
    if not subscription.marzban_username:
        return False
    client = MarzbanClient(settings)
    try:
        synced = await MarzbanSyncService(client).sync_subscription(subscription)
    except MarzbanError:
        await session.rollback()
        return False
    finally:
        await client.aclose()
    await session.commit()
    return synced


def can_add_device(subscription: Any) -> bool:
    return (
        bool(subscription.subscription_url)
        and subscription.status == SubscriptionStatus.active.value
        and subscription.additional_devices_count < MAX_ADDITIONAL_DEVICES
    )


def subscription_markup(subscription: Any):
    return subscription_keyboard(
        bool(subscription.subscription_url),
        can_add_device(subscription),
    )


def subscription_text(subscription: Any) -> str:
    plan_title = subscription.plan.title if subscription.plan else "Тестовый период"
    limit = (
        f"{subscription.traffic_limit_bytes / 1024 / 1024 / 1024:.0f} GB"
        if subscription.traffic_limit_bytes
        else "без фиксированного лимита"
    )
    used = subscription.last_traffic_used_bytes / 1024 / 1024 / 1024
    expires = (
        subscription.expires_at.strftime("%d.%m.%Y")
        if subscription.expires_at
        else "не указано"
    )
    return ru.SUBSCRIPTION_INFO.format(
        status=subscription.status,
        plan_title=plan_title,
        expires_at=expires,
        used_gb=f"{used:.1f}",
        limit_gb=limit,
        additional_devices_count=subscription.additional_devices_count,
        max_additional_devices=MAX_ADDITIONAL_DEVICES,
        subscription_url=subscription.subscription_url or "ожидает выдачи",
    )


async def get_latest_subscription(
    target: CallbackQuery | Message,
    session: AsyncSession,
    settings: Settings,
):
    from_user = target.from_user
    if not from_user:
        return None
    user = await UserService(session, settings).get_by_telegram_id(from_user.id)
    if not user:
        return None
    return await SubscriptionService(session, settings).latest_for_user(user)


async def answer_subscription(
    target: CallbackQuery | Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    subscription = await get_latest_subscription(target, session, settings)
    if not subscription:
        text = ru.SUBSCRIPTION_EMPTY
        if isinstance(target, CallbackQuery) and target.message:
            await target.message.edit_text(text, reply_markup=back_keyboard())
            await target.answer()
        elif isinstance(target, Message):
            await target.answer(text, reply_markup=back_keyboard())
        return

    is_free_subscription = subscription.plan_id is None
    synced = await sync_subscription_from_marzban(subscription, session, settings)
    if target.from_user:
        try:
            await SiteApiClient(settings).sync_subscription(
                target.from_user,
                subscription,
                is_free=is_free_subscription,
            )
        except SiteApiError:
            pass
    text = subscription_text(subscription)
    if not synced:
        text += "\n\nСтатус Marzban сейчас не обновился. Показаны последние данные бота."

    if isinstance(target, CallbackQuery) and target.message:
        await target.message.edit_text(
            text,
            reply_markup=subscription_markup(subscription),
            disable_web_page_preview=True,
        )
        await target.answer("Обновлено" if synced else "Marzban не ответил", show_alert=False)
    elif isinstance(target, Message):
        await target.answer(
            text,
            reply_markup=subscription_markup(subscription),
            disable_web_page_preview=True,
        )


@router.callback_query(lambda call: call.data == "subscription:show")
async def show_subscription(call: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    await answer_subscription(call, session, settings)


@router.callback_query(lambda call: call.data == "subscription:device:add")
async def add_subscription_device(
    call: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not call.from_user or not call.message:
        return

    subscription = await get_latest_subscription(call, session, settings)
    if not subscription:
        await call.message.edit_text(ru.SUBSCRIPTION_EMPTY, reply_markup=back_keyboard())
        await call.answer()
        return

    await sync_subscription_from_marzban(subscription, session, settings)
    if not subscription.subscription_url or subscription.status != SubscriptionStatus.active.value:
        await call.answer(ru.DEVICE_ADD_UNAVAILABLE, show_alert=True)
        return

    service = SubscriptionService(session, settings)
    count = await service.add_additional_device(subscription)
    if count is None:
        await session.rollback()
        await call.answer(
            ru.DEVICE_LIMIT_REACHED.format(max_count=MAX_ADDITIONAL_DEVICES),
            show_alert=True,
        )
        return

    await session.commit()
    await call.bot.send_message(
        call.from_user.id,
        ru.DEVICE_ADDED.format(
            count=count,
            max_count=MAX_ADDITIONAL_DEVICES,
            subscription_url=subscription.subscription_url,
        ),
        disable_web_page_preview=True,
    )
    await call.message.edit_text(
        subscription_text(subscription),
        reply_markup=subscription_markup(subscription),
        disable_web_page_preview=True,
    )
    await call.answer("Устройство добавлено", show_alert=False)


@router.message(Command("subscription"))
async def subscription_command(message: Message, session: AsyncSession, settings: Settings) -> None:
    await answer_subscription(message, session, settings)
