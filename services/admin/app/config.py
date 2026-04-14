"""Configuration for the admin service."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from shared.base_config import BaseServiceSettings, ObjectStorageMixin


class Settings(ObjectStorageMixin, BaseServiceSettings):
    """Admin service configuration."""

    admin_master_key: str
    kafka_bootstrap: str = "redpanda:9092"
    # Consumer group isolation (#1008) — unique per service, env-configurable.
    consumer_group_id: str = Field(
        default="admin-review-consumer", alias="KAFKA_CONSUMER_GROUP_ID"
    )

    # File upload limits
    max_upload_size_mb: int = Field(default=512, alias="MAX_UPLOAD_SIZE_MB")


@lru_cache
def get_settings() -> Settings:
    return Settings()
