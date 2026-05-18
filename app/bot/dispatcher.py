from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject

from app.bot.handlers import admin, config, instructions, payments, plans, start, subscriptions, trial
from app.config import Settings
from app.db.session import SessionLocal


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class SettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self._settings
        return await handler(event, data)


def create_dispatcher(settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(SettingsMiddleware(settings))
    dp.update.middleware(DbSessionMiddleware())
    dp.include_routers(
        start.router,
        plans.router,
        payments.router,
        trial.router,
        subscriptions.router,
        config.router,
        instructions.router,
        admin.router,
    )
    return dp


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.bot_token.get_secret_value())
