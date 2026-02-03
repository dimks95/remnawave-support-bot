from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def user_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="FAQ", callback_data="u:faq")],
            [InlineKeyboardButton(text="Создать обращение", callback_data="u:new")],
            [InlineKeyboardButton(text="Мои обращения", callback_data="u:mine")],
        ]
    )

