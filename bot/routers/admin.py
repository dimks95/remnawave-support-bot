from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.states import AdminFaqEdit, AdminReply
from bot.db.models import Ticket
from bot.services.tickets import get_or_create_open_ticket, log_message, upsert_user
from bot.utils.faq import get_faq_text, set_faq_text
from bot.utils.support_format import parse_user_and_ticket_from_header

logger = logging.getLogger(__name__)

admin_router = Router(name="admin")
admin_router.message.filter(IsAdmin(), F.chat.type == "private")
admin_router.callback_query.filter(IsAdmin(), F.message.chat.type == "private")


def _parse_ticket_action(data: str) -> tuple[str | None, int | None, int | None]:
    """
    Форматы:
      - t:reply:<ticket_id>:<user_tg_id>
      - t:close:<ticket_id>
    """
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != "t":
        return None, None, None
    action = parts[1]
    if action == "reply" and len(parts) == 4:
        try:
            return "reply", int(parts[2]), int(parts[3])
        except ValueError:
            return None, None, None
    if action == "close" and len(parts) == 3:
        try:
            return "close", int(parts[2]), None
        except ValueError:
            return None, None, None
    return None, None, None


@admin_router.callback_query(F.data.startswith("t:reply:"))
async def admin_ticket_reply_button(cq: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if cq.from_user is None:
        return
    action, ticket_id, user_tg_id = _parse_ticket_action(cq.data or "")
    if action != "reply" or ticket_id is None or user_tg_id is None:
        await cq.answer("Не удалось разобрать действие.", show_alert=True)
        return

    # Проверяем, что тикет существует и открыт
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await cq.answer("Тикет не найден.", show_alert=True)
        return
    if ticket.status != "open":
        await cq.answer("Тикет уже закрыт.", show_alert=True)
        return

    await state.set_state(AdminReply.waiting_for_text)
    await state.update_data(target_user_id=user_tg_id, ticket_id=ticket_id)
    await cq.answer()
    if cq.message:
        await cq.message.answer(f"Ок. Отправь текст ответа для тикета {ticket_id} пользователю {user_tg_id}.")


@admin_router.callback_query(F.data.startswith("t:close:"))
async def admin_ticket_close_button(cq: CallbackQuery, session: AsyncSession) -> None:
    action, ticket_id, _user_tg_id = _parse_ticket_action(cq.data or "")
    if action != "close" or ticket_id is None:
        await cq.answer("Не удалось разобрать действие.", show_alert=True)
        return

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await cq.answer("Тикет не найден.", show_alert=True)
        return
    if ticket.status == "closed":
        await cq.answer("Уже закрыт.")
        # уберём клавиатуру, если она ещё висит
        if cq.message:
            try:
                await cq.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return

    ticket.status = "closed"
    await session.flush()

    await cq.answer("Тикет закрыт.")
    if cq.message:
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cq.message.answer(f"✅ Тикет {ticket_id} закрыт.")


@admin_router.message(Command("reply"))
async def admin_reply_cmd(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """
    /reply <user_id> <text>
    Если <text> не указан — включаем FSM и ждём следующим сообщением.
    """
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: `/reply <user_id> <текст>`")
        return
    user_id = int(parts[1])
    if len(parts) == 3 and parts[2].strip():
        await _log_and_send_admin_reply(
            session=session,
            admin_message=message,
            target_user_id=user_id,
            text=parts[2].strip(),
        )
        return

    await state.set_state(AdminReply.waiting_for_text)
    await state.update_data(target_user_id=user_id)
    await message.answer(f"Ок. Теперь отправь текст ответа пользователю {user_id}.")


@admin_router.message(Command("faq"))
async def admin_faq_show(message: Message) -> None:
    await message.answer(get_faq_text())


@admin_router.message(Command("setfaq"))
async def admin_faq_set(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        set_faq_text(parts[1])
        await message.answer("FAQ обновлён.")
        return
    await state.set_state(AdminFaqEdit.waiting_for_text)
    await message.answer("Отправь одним сообщением новый текст FAQ.")


@admin_router.message(AdminFaqEdit.waiting_for_text)
async def admin_faq_set_fsm(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужен текст.")
        return
    set_faq_text(message.text)
    await state.clear()
    await message.answer("FAQ обновлён.")


@admin_router.message(F.reply_to_message.as_("rtm"))
async def admin_reply_by_reply(
    message: Message,
    rtm: Message,
    session: AsyncSession,
) -> None:
    header_text = None
    if rtm.text:
        header_text = rtm.text
    elif rtm.reply_to_message and rtm.reply_to_message.text:
        # если админ ответил на медиа, которое было отправлено реплаем к header-сообщению
        header_text = rtm.reply_to_message.text
    if not header_text:
        return

    user_id, ticket_id = parse_user_and_ticket_from_header(header_text)
    if user_id is None:
        return
    if not message.text:
        await message.answer("Пока поддерживается только текстовый ответ.")
        return
    await _log_and_send_admin_reply(
        session=session,
        admin_message=message,
        target_user_id=user_id,
        ticket_id=ticket_id,
        text=message.text,
    )


@admin_router.message(AdminReply.waiting_for_text)
async def admin_reply_fsm(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    target_user_id = int(data["target_user_id"])
    ticket_id = data.get("ticket_id")
    if not message.text:
        await message.answer("Нужен текст.")
        return

    await _log_and_send_admin_reply(
        session=session,
        admin_message=message,
        target_user_id=target_user_id,
        ticket_id=int(ticket_id) if ticket_id is not None else None,
        text=message.text,
    )
    await state.clear()


async def _log_and_send_admin_reply(
    *,
    session: AsyncSession,
    admin_message: Message,
    target_user_id: int,
    ticket_id: int | None = None,
    text: str,
) -> None:
    if admin_message.from_user is None:
        return

    admin_user = await upsert_user(
        session,
        tg_id=admin_message.from_user.id,
        username=admin_message.from_user.username,
        is_admin=True,
    )
    target_user = await upsert_user(session, tg_id=target_user_id, username=None, is_admin=False)
    ticket: Ticket | None
    if ticket_id is None:
        ticket = await get_or_create_open_ticket(session, user=target_user)
    else:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            await admin_message.answer("Тикет не найден.")
            return
        if ticket.user_id != target_user.id:
            await admin_message.answer("Тикет не принадлежит этому пользователю.")
            return
        if ticket.status != "open":
            await admin_message.answer("Тикет уже закрыт.")
            return
    await log_message(
        session,
        ticket,
        from_admin=True,
        from_tg_id=admin_user.tg_id,
        tg_message_id=admin_message.message_id,
        text=text,
    )

    try:
        await admin_message.bot.send_message(target_user_id, f"Ответ поддержки:\n{text}")
        await admin_message.answer("Отправлено.")
    except Exception:
        logger.exception("Failed to send admin reply to user_id=%s", target_user_id)
        await admin_message.answer("Не удалось отправить сообщение пользователю (возможно, он не писал боту).")

