from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import get_settings
from bot.db import create_engine, create_sessionmaker
from bot.logging import setup_logging
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.remnawave import RemnawaveMiddleware
from bot.middlewares.settings import SettingsMiddleware
from bot.routers import admin_router, common_router, user_router
from bot.services.remnawave import RemnawaveClient


async def _close_storage(storage) -> None:
    close = getattr(storage, "close", None)
    if callable(close):
        res = close()
        if asyncio.iscoroutine(res):
            await res
    wait_closed = getattr(storage, "wait_closed", None)
    if callable(wait_closed):
        res = wait_closed()
        if asyncio.iscoroutine(res):
            await res


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    remnawave = RemnawaveClient(
        settings.remnawave_api_base_url,
        settings.remnawave_api_token,
        caddy_api_key=settings.remnawave_caddy_api_key,
    )

    bot = Bot(token=settings.bot_token)
    storage = RedisStorage.from_url(settings.redis_url) if settings.redis_url else MemoryStorage()
    dp = Dispatcher(storage=storage)

    # DI middlewares
    dp.update.middleware(SettingsMiddleware(settings))
    dp.update.middleware(RemnawaveMiddleware(remnawave))
    dp.update.middleware(DbSessionMiddleware(sessionmaker))

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await _close_storage(storage)
        await remnawave.aclose()
        await engine.dispose()
        await bot.session.close()


def run() -> None:
    asyncio.run(main())

