from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import main_menu
from app.bot.texts import ru
from app.config import Settings
from app.integrations.site_api import SiteApiClient, SiteApiError
from app.services.users import UserService

router = Router()


def user_is_admin(telegram_id: int | None, settings: Settings) -> bool:
    return telegram_id is not None and telegram_id in settings.admin_telegram_ids


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession, settings: Settings) -> None:
    referral_code = None
    if message.text and len(message.text.split(maxsplit=1)) == 2:
        referral_code = message.text.split(maxsplit=1)[1]
    if message.from_user:
        is_site_link = bool(referral_code and referral_code.startswith("site_"))
        await UserService(session, settings).upsert_from_telegram(
            message.from_user,
            None if is_site_link else referral_code,
        )
        await session.commit()
        if is_site_link and referral_code:
            await link_site_account(message, settings, referral_code.removeprefix("site_"))
            return
    await message.answer(
        ru.WELCOME,
        reply_markup=main_menu(
            str(settings.public_site_url),
            is_admin=user_is_admin(message.from_user.id if message.from_user else None, settings),
        ),
    )


async def link_site_account(message: Message, settings: Settings, token: str) -> None:
    if not message.from_user:
        await message.answer(ru.TELEGRAM_LINK_FAILED)
        return
    try:
        await SiteApiClient(settings).link_telegram(token, message.from_user)
    except SiteApiError as exc:
        if str(exc) in {"Link expired", "Telegram account is already linked"}:
            await message.answer(ru.TELEGRAM_LINK_EXPIRED)
            return
        await message.answer(ru.TELEGRAM_LINK_FAILED)
        return
    await message.answer(
        ru.TELEGRAM_LINKED,
        reply_markup=main_menu(
            str(settings.public_site_url),
            is_admin=user_is_admin(message.from_user.id, settings),
        ),
    )


@router.callback_query(lambda call: call.data == "menu:main")
async def show_main_menu(call: CallbackQuery, settings: Settings) -> None:
    if call.message:
        await call.message.edit_text(
            ru.WELCOME,
            reply_markup=main_menu(
                str(settings.public_site_url),
                is_admin=user_is_admin(call.from_user.id if call.from_user else None, settings),
            ),
        )
    await call.answer()
