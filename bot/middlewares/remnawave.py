from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware

from bot.services.remnawave import RemnawaveClient


class RemnawaveMiddleware(BaseMiddleware):
    def __init__(self, client: RemnawaveClient) -> None:
        super().__init__()
        self._client = client

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        data["remnawave"] = self._client
        return await handler(event, data)

