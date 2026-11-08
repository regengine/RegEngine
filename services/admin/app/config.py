"""Configuration for the admin service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from shared.base_config import BaseServiceSettings, ObjectStorageMixin


class Settings(ObjectStorageMixin, BaseServiceSettings):
    """Admin service configuration."""

    # File upload limits
    max_upload_size_mb: int = Field(default=512, alias="MAX_UPLOAD_SIZE_MB")


@lru_cache
def get_settings() -> Settings:
    return Settings()
