from __future__ import annotations

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.remnawave import SubscriptionInfo


def format_subscription(info: SubscriptionInfo | None) -> str:
    if info is None:
        return "📡 Панель: данных не найдено"
    parts: list[str] = [f"📡 Панель: {info.status}"]
    if info.days_left is not None:
        parts.append(f"⏳ Дней до конца: {info.days_left}")
    if info.traffic_used_gb is not None:
        parts.append(f"📊 Трафик: {info.traffic_used_gb:.2f} GB")
    if info.connection_url:
        parts.append(f"🔗 Ссылка: {info.connection_url}")
    return "\n".join(parts)


def build_admin_ticket_header(*, ticket_id: int, user_tg_id: int, username: str | None) -> str:
    u = f"@{username}" if username else "—"
    # Важно: этот header парсится по regex при reply
    return f"🎫 Ticket: {ticket_id} | 🆔 User: {user_tg_id} | 👤 {u}"


def build_admin_ticket_actions_kb(*, ticket_id: int, user_tg_id: int) -> InlineKeyboardMarkup:
    """
    Inline-кнопки для админов под сообщением тикета.
    callback_data должен быть <= 64 байт.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✉️ Ответить", callback_data=f"t:reply:{ticket_id}:{user_tg_id}"),
                InlineKeyboardButton(text="✅ Закрыть", callback_data=f"t:close:{ticket_id}"),
            ]
        ]
    )


_RE_USER = re.compile(r"User:\s*(\d+)")
_RE_TICKET = re.compile(r"Ticket:\s*(\d+)")


def parse_user_and_ticket_from_header(text: str) -> tuple[int | None, int | None]:
    user_id = None
    ticket_id = None
    mu = _RE_USER.search(text)
    mt = _RE_TICKET.search(text)
    if mu:
        user_id = int(mu.group(1))
    if mt:
        ticket_id = int(mt.group(1))
    return user_id, ticket_id

