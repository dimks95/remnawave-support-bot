from sqlalchemy.ext.asyncio import AsyncEngine

from bot.db.base import Base
from bot.db import models  # noqa: F401  (import for metadata)


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

