from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import Settings
from bot.utils.keyboards import user_main_menu_kb

common_router = Router(name="common")


@common_router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    if message.from_user and message.from_user.id in set(settings.admin_ids):
        await message.answer(
            "Привет! Ты админ поддержки.\n\n"
            "Как отвечать:\n"
            "- ответь реплаем на сообщение тикета (в этом чате), или\n"
            "- используй команду `/reply <user_id> <текст>`",
        )
    else:
        await message.answer(
            "Здравствуйте! Это бот технической поддержки.\n"
            "Выберите действие ниже или просто напишите сообщение — мы передадим его администраторам.",
            reply_markup=user_main_menu_kb(),
        )

