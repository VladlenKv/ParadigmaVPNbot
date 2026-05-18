from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import back_keyboard, subscription_keyboard
from app.bot.texts import ru
from app.config import Settings
from app.db.models import Plan
from app.integrations.marzban import MarzbanClient, MarzbanError
from app.services.provisioning import MarzbanProvisioningService
from app.services.subscriptions import MAX_ADDITIONAL_DEVICES, SubscriptionService
from app.services.users import UserService

router = Router()


@router.callback_query(lambda call: call.data == "trial:create")
async def create_trial(call: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if not call.from_user or not call.message:
        return
    user = await UserService(session, settings).upsert_from_telegram(call.from_user)
    service = SubscriptionService(session, settings)
    subscription = await service.create_trial(user)

    if not settings.trial_enabled:
        await session.commit()
        text = ru.TRIAL_DISABLED
        reply_markup = back_keyboard()
    elif subscription is None:
        await session.commit()
        text = ru.TRIAL_ALREADY_USED
        reply_markup = back_keyboard()
    else:
        trial_plan = Plan(
            code="trial",
            title="РўРµСЃС‚РѕРІС‹Р№ РїРµСЂРёРѕРґ",
            description="",
            price_amount=0,
            currency="RUB",
            duration_days=settings.trial_duration_days,
            traffic_limit_gb=settings.trial_traffic_limit_gb,
            device_limit=1,
        )
        client = MarzbanClient(settings)
        try:
            await MarzbanProvisioningService(client).provision(user, subscription, trial_plan)
            await session.commit()
            text = ru.TRIAL_CREATED.format(
                expires_at=subscription.expires_at.strftime("%d.%m.%Y")
                if subscription.expires_at
                else "",
                traffic_gb=settings.trial_traffic_limit_gb,
                subscription_url=subscription.subscription_url or "РѕР¶РёРґР°РµС‚ РІС‹РґР°С‡Рё",
            )
            reply_markup = subscription_keyboard(
                bool(subscription.subscription_url),
                subscription.additional_devices_count < MAX_ADDITIONAL_DEVICES,
            )
        except MarzbanError:
            await session.commit()
            text = ru.TRIAL_PROVISIONING_FAILED
            reply_markup = back_keyboard()
        finally:
            await client.aclose()

    await call.message.edit_text(
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    await call.answer()
