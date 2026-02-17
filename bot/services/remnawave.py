from __future__ import annotations

import datetime as dt
import logging
import math
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubscriptionInfo:
    status: str  # active/expired/unknown
    raw_status: str | None  # оригинальный статус из API (ACTIVE, EXPIRED, SUSPENDED и т.д.)
    connection_url: str | None
    traffic_used_gb: float | None
    days_left: int | None
    user_id: int | None  # ID пользователя в панели


class RemnawaveClient:
    """
    Минимальный async-клиент панели Remnawave.

    Адаптирован под стандартный Remnawave API:
    - base_url должен указывать на панель или на /api (мы нормализуем).
    - получение пользователей по Telegram ID: GET /api/users/by-telegram-id/{telegramId}
    """

    def __init__(self, base_url: str, token: str, *, caddy_api_key: str | None = None) -> None:
        self._base_url = self._normalize_api_base(base_url)
        self._token = token
        self._caddy_api_key = caddy_api_key
        self._client = httpx.AsyncClient(timeout=15)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _normalize_api_base(base_url: str) -> str:
        s = base_url.rstrip("/")
        if not s.endswith("/api"):
            s = f"{s}/api"
        return s

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if self._caddy_api_key:
            headers["X-Api-Key"] = self._caddy_api_key
        return headers

    @staticmethod
    def _parse_dt(value: Any) -> dt.datetime | None:
        if not value:
            return None
        if isinstance(value, dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            # ISO 8601: 2026-01-01T00:00:00Z
            s = s.replace("Z", "+00:00")
            try:
                parsed = dt.datetime.fromisoformat(s)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                return None
        return None

    @staticmethod
    def _pick_best_user(users: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
        # если пользователей несколько — берём того, у кого expireAt максимальный
        best = None
        best_exp = None
        for u in users:
            exp = RemnawaveClient._parse_dt(u.get("expireAt"))
            if best is None:
                best = u
                best_exp = exp
                continue
            if exp is not None and (best_exp is None or exp > best_exp):
                best = u
                best_exp = exp
        return best

    async def get_user_subscription_by_telegram_id(self, telegram_user_id: int) -> SubscriptionInfo | None:
        """
        Remnawave: GET /api/users/by-telegram-id/{telegramId}
        Ответ: список пользователей (может быть пустым).
        """
        url = f"{self._base_url}/users/by-telegram-id/{telegram_user_id}"
        try:
            resp = await self._client.get(url, headers=self._headers())
            if resp.status_code == 404:
                logger.debug("Remnawave API: user not found (404) for tg_id=%s", telegram_user_id)
                return None
            resp.raise_for_status()
            data = resp.json()
            logger.debug("Remnawave API response for tg_id=%s: status=%s, data_type=%s, data=%s", 
                        telegram_user_id, resp.status_code, type(data).__name__, str(data)[:500])
            
            # Поддержка как списка, так и одного объекта
            users_list = []
            if isinstance(data, list):
                users_list = data
            elif isinstance(data, dict):
                # Если API вернул один объект вместо списка
                users_list = [data]
            else:
                logger.warning("Remnawave API: unexpected data type %s for tg_id=%s", type(data).__name__, telegram_user_id)
                return None
            
            if not users_list:
                logger.debug("Remnawave API: empty list for tg_id=%s", telegram_user_id)
                return None

            user = self._pick_best_user([x for x in users_list if isinstance(x, dict)])  # type: ignore[arg-type]
            if not user:
                logger.debug("Remnawave API: no valid user dict found for tg_id=%s", telegram_user_id)
                return None
            
            logger.debug("Remnawave API: found user for tg_id=%s: id=%s, status=%s", 
                        telegram_user_id, user.get("id"), user.get("status"))
        except httpx.HTTPStatusError as e:
            logger.error("Remnawave API HTTP error for tg_id=%s: status=%s, response=%s", 
                        telegram_user_id, e.response.status_code, e.response.text[:200])
            return None
        except Exception as e:
            logger.exception("Remnawave API error for tg_id=%s", telegram_user_id)
            return None

        status_raw = str(user.get("status") or "UNKNOWN").upper()
        expire_at = self._parse_dt(user.get("expireAt"))
        now = dt.datetime.now(dt.timezone.utc)

        is_expired = status_raw != "ACTIVE" or (expire_at is not None and expire_at <= now)
        status = "expired" if is_expired else "active"

        days_left = None
        if expire_at is not None:
            delta = expire_at - now
            days_left = max(0, int(math.ceil(delta.total_seconds() / 86400)))

        used_bytes = None
        traffic = user.get("userTraffic")
        if isinstance(traffic, dict) and traffic.get("usedTrafficBytes") is not None:
            try:
                used_bytes = float(traffic["usedTrafficBytes"])
            except (TypeError, ValueError):
                used_bytes = None

        traffic_used_gb = None
        if used_bytes is not None:
            traffic_used_gb = used_bytes / (1024**3)

        user_id = None
        if user.get("id") is not None:
            try:
                user_id = int(user["id"])
            except (TypeError, ValueError):
                user_id = None

        return SubscriptionInfo(
            status=status,
            raw_status=status_raw,
            connection_url=(str(user["subscriptionUrl"]) if user.get("subscriptionUrl") else None),
            traffic_used_gb=traffic_used_gb,
            days_left=days_left,
            user_id=user_id,
        )

