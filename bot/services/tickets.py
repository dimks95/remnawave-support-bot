from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import SupportMessage, Ticket, User


async def upsert_user(session: AsyncSession, tg_id: int, username: str | None, is_admin: bool) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, username=username, is_admin=is_admin)
        session.add(user)
        await session.flush()
        return user
    changed = False
    if user.username != username:
        user.username = username
        changed = True
    if user.is_admin != is_admin:
        user.is_admin = is_admin
        changed = True
    if changed:
        await session.flush()
    return user


async def get_or_create_open_ticket(session: AsyncSession, user: User) -> Ticket:
    ticket = await session.scalar(
        select(Ticket).where(Ticket.user_id == user.id, Ticket.status == "open").order_by(Ticket.id.desc())
    )
    if ticket is None:
        ticket = Ticket(user_id=user.id, status="open")
        session.add(ticket)
        await session.flush()
        return ticket
    ticket.updated_at = dt.datetime.now(dt.timezone.utc)
    await session.flush()
    return ticket


async def log_message(
    session: AsyncSession,
    ticket: Ticket,
    *,
    from_admin: bool,
    from_tg_id: int,
    tg_message_id: int | None,
    text: str,
) -> SupportMessage:
    msg = SupportMessage(
        ticket_id=ticket.id,
        from_admin=from_admin,
        from_tg_id=from_tg_id,
        tg_message_id=tg_message_id,
        text=text,
    )
    session.add(msg)
    await session.flush()
    ticket.updated_at = dt.datetime.now(dt.timezone.utc)
    await session.flush()
    return msg

