from __future__ import annotations

import datetime as dt
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.filters.is_admin import IsUser
from bot.fsm.states import UserNewTicket
from bot.services.remnawave import RemnawaveClient
from bot.services.tickets import get_or_create_open_ticket, log_message, upsert_user
from bot.db.models import Ticket
from bot.utils.faq import get_faq_text
from bot.utils.keyboards import user_main_menu_kb
from bot.utils.support_format import build_admin_ticket_actions_kb, build_admin_ticket_header, format_subscription

logger = logging.getLogger(__name__)

user_router = Router(name="user")
user_router.callback_query.filter(IsUser(), F.message.chat.type == "private")


async def _forward_user_message_to_admins(
    *,
    message: Message,
    session: AsyncSession,
    settings: Settings,
    remnawave: RemnawaveClient,
) -> int | None:
    if message.from_user is None:
        return None

    text_for_log = message.text or message.caption or f"<{message.content_type}>"

    user = await upsert_user(session, tg_id=message.from_user.id, username=message.from_user.username, is_admin=False)
    ticket = await get_or_create_open_ticket(session, user=user)
    await log_message(
        session,
        ticket,
        from_admin=False,
        from_tg_id=message.from_user.id,
        tg_message_id=message.message_id,
        text=text_for_log,
    )

    sub_info = None
    try:
        sub_info = await remnawave.get_user_subscription_by_telegram_id(message.from_user.id)
    except Exception:
        logger.exception("Remnawave API error for tg_id=%s", message.from_user.id)

    header = build_admin_ticket_header(
        ticket_id=ticket.id,
        user_tg_id=message.from_user.id,
        username=message.from_user.username,
    )
    panel_block = format_subscription(sub_info)
    admin_kb = build_admin_ticket_actions_kb(ticket_id=ticket.id, user_tg_id=message.from_user.id)

    # Отправляем всем админам
    for admin_id in settings.admin_ids:
        try:
            if message.text or message.caption:
                admin_text = f"{header}\n\n{panel_block}\n\nСообщение:\n{text_for_log}"
                await message.bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
            else:
                head_msg = await message.bot.send_message(
                    admin_id,
                    f"{header}\n\n{panel_block}\n\nСообщение ниже:",
                    reply_markup=admin_kb,
                )
                await message.copy_to(admin_id, reply_to_message_id=head_msg.message_id)
        except Exception:
            logger.exception("Failed to send message to admin_id=%s", admin_id)

    return ticket.id


@user_router.callback_query(F.data == "u:faq")
async def user_faq_button(cq: CallbackQuery) -> None:
    await cq.answer()
    if cq.message:
        await cq.message.answer(get_faq_text(), reply_markup=user_main_menu_kb())


@user_router.callback_query(F.data == "u:mine")
async def user_my_tickets_button(cq: CallbackQuery, session: AsyncSession) -> None:
    if cq.from_user is None:
        return
    await cq.answer()

    user = await upsert_user(session, tg_id=cq.from_user.id, username=cq.from_user.username, is_admin=False)
    tickets = (
        await session.scalars(select(Ticket).where(Ticket.user_id == user.id).order_by(Ticket.updated_at.desc()).limit(10))
    ).all()

    if not tickets:
        text = "У вас пока нет обращений."
    else:
        lines: list[str] = ["Ваши обращения (последние 10):"]
        for t in tickets:
            updated = t.updated_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            status = "🟢 open" if t.status == "open" else "⚪️ closed"
            lines.append(f"- 🎫 #{t.id} — {status} — обновлён: {updated}")
        text = "\n".join(lines)

    if cq.message:
        await cq.message.answer(text, reply_markup=user_main_menu_kb())


@user_router.callback_query(F.data == "u:new")
async def user_new_ticket_button(cq: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if cq.from_user is None:
        return
    await cq.answer()

    user = await upsert_user(session, tg_id=cq.from_user.id, username=cq.from_user.username, is_admin=False)
    open_ticket = await session.scalar(
        select(Ticket).where(Ticket.user_id == user.id, Ticket.status == "open").order_by(Ticket.id.desc())
    )

    await state.set_state(UserNewTicket.waiting_for_text)
    if cq.message:
        if open_ticket is None:
            await cq.message.answer("Ок. Опишите проблему одним сообщением — я создам обращение и отправлю в поддержку.")
        else:
            await cq.message.answer(
                f"У вас уже есть открытое обращение #{open_ticket.id}.\n"
                "Напишите сообщение — я отправлю его в поддержку в рамках этого обращения."
            )


@user_router.message(IsUser(), UserNewTicket.waiting_for_text, F.chat.type == "private")
async def user_new_ticket_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    remnawave: RemnawaveClient,
) -> None:
    ticket_id = await _forward_user_message_to_admins(
        message=message,
        session=session,
        settings=settings,
        remnawave=remnawave,
    )
    await state.clear()
    if ticket_id is not None:
        await message.answer(f"Сообщение отправлено в поддержку. Номер тикета: {ticket_id}", reply_markup=user_main_menu_kb())


@user_router.message(IsUser(), StateFilter(None), F.chat.type == "private")
async def user_any_message(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    remnawave: RemnawaveClient,
) -> None:
    ticket_id = await _forward_user_message_to_admins(
        message=message,
        session=session,
        settings=settings,
        remnawave=remnawave,
    )
    if ticket_id is not None:
        await message.answer(f"Сообщение отправлено в поддержку. Номер тикета: {ticket_id}", reply_markup=user_main_menu_kb())

