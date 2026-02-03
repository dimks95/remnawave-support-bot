from __future__ import annotations

from functools import lru_cache
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_ids: List[int] = Field(default_factory=list, alias="ADMIN_IDS")

    database_url: str = Field(alias="DATABASE_URL")

    remnawave_api_base_url: str = Field(alias="REMNAWAVE_API_BASE_URL")
    remnawave_api_token: str = Field(alias="REMNAWAVE_API_TOKEN")
    remnawave_caddy_api_key: str | None = Field(default=None, alias="REMNAWAVE_CADDY_API_KEY")

    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            # supports: "1,2,3" or "1 2 3"
            parts = [p.strip() for p in s.replace(" ", ",").split(",") if p.strip()]
            return [int(p) for p in parts]
        return [int(v)]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

