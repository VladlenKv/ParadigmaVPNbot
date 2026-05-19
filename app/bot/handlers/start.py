from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.config import get_or_issue_config_for_user
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
        is_site_login = bool(referral_code and referral_code.startswith("login_"))
        is_site_auth = bool(referral_code and referral_code.startswith("auth_"))
        await UserService(session, settings).upsert_from_telegram(
            message.from_user,
            None if is_site_link or is_site_login or is_site_auth else referral_code,
        )
        await session.commit()
        if is_site_link and referral_code:
            await link_site_account(message, settings, referral_code.removeprefix("site_"))
            return
        if is_site_auth and referral_code:
            await confirm_site_auth(message, settings, referral_code.removeprefix("auth_"))
            return
        if is_site_login and referral_code:
            await confirm_site_login(message, settings, referral_code.removeprefix("login_"))
            return
        if referral_code == "config":
            await get_or_issue_config_for_user(message.from_user, message.answer, session, settings)
            return
    await message.answer(
        ru.WELCOME,
        reply_markup=main_menu(
            str(settings.public_site_url),
            is_admin=user_is_admin(message.from_user.id if message.from_user else None, settings),
        ),
    )


async def confirm_site_login(message: Message, settings: Settings, token: str) -> None:
    if not message.from_user:
        await message.answer(ru.TELEGRAM_LOGIN_FAILED)
        return
    try:
        await SiteApiClient(settings).confirm_telegram_login(token, message.from_user)
    except SiteApiError as exc:
        if str(exc) == "Link expired":
            await message.answer(ru.TELEGRAM_LOGIN_EXPIRED)
            return
        await message.answer(ru.TELEGRAM_LOGIN_FAILED)
        return
    await message.answer(
        ru.TELEGRAM_LOGIN_CONFIRMED,
        reply_markup=main_menu(
            str(settings.public_site_url),
            is_admin=user_is_admin(message.from_user.id, settings),
        ),
    )


async def confirm_site_auth(message: Message, settings: Settings, token: str) -> None:
    if not message.from_user:
        await message.answer(ru.TELEGRAM_LOGIN_FAILED)
        return
    try:
        await SiteApiClient(settings).confirm_telegram_auth(token, message.from_user)
    except SiteApiError as exc:
        if str(exc) == "Link expired":
            await message.answer(ru.TELEGRAM_LOGIN_EXPIRED)
            return
        await message.answer(ru.TELEGRAM_LOGIN_FAILED)
        return
    await message.answer(
        ru.TELEGRAM_LOGIN_CONFIRMED,
        reply_markup=main_menu(
            str(settings.public_site_url),
            is_admin=user_is_admin(message.from_user.id, settings),
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
