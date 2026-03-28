from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the compliance service."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    graph_service_url: str = Field(
        default="http://graph-service:8200",
        alias="GRAPH_SERVICE_URL",
    )
    graph_request_timeout_s: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        alias="GRAPH_REQUEST_TIMEOUT_S",
    )
    internal_service_secret: Optional[str] = Field(
        default=None,
        alias="REGENGINE_INTERNAL_SECRET",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
