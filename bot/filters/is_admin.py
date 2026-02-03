from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from bot.config import Settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        if event.from_user is None:
            return False
        return event.from_user.id in set(settings.admin_ids)


class IsUser(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        if event.from_user is None:
            return False
        return event.from_user.id not in set(settings.admin_ids)

