from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from shared.base_config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Environment-driven configuration for the compliance service."""

    # Graph is experimental and disabled in production. Do not default to a
    # Docker DNS hostname that looks configured but cannot be reached (#2862).
    graph_service_url: Optional[str] = Field(
        default=None,
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
