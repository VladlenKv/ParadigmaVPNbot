import asyncio

from aiogram import Bot


class NotificationService:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_admins(self, admin_ids: set[int], text: str) -> None:
        await asyncio.gather(
            *(self._bot.send_message(admin_id, text) for admin_id in admin_ids),
            return_exceptions=True,
        )
