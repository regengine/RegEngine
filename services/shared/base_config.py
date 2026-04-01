"""Base configuration for all RegEngine services.

All per-service Settings classes should inherit from BaseServiceSettings
to ensure consistent env loading, logging, and model_config behavior.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common settings shared by all RegEngine services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    regengine_env: str = Field(default="development", alias="REGENGINE_ENV")


class ObjectStorageMixin(BaseSettings):
    """Mixin for services that access S3-compatible object storage."""

    object_storage_endpoint_url: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ENDPOINT_URL",
    )
    object_storage_region: str = Field(
        default="us-east-1",
        alias="OBJECT_STORAGE_REGION",
    )
    object_storage_access_key_id: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ACCESS_KEY_ID",
    )
    object_storage_secret_access_key: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_SECRET_ACCESS_KEY",
    )
