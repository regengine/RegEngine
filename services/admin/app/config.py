"""Configuration for the admin service."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Admin service configuration."""

    log_level: str = "INFO"
    admin_master_key: str
    kafka_bootstrap: str = "redpanda:9092"

    # Object storage configuration
    pcos_bucket: str = Field(default="reg-engine-pcos-data-dev", alias="PCOS_DATA_BUCKET")
    object_storage_endpoint_url: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ENDPOINT_URL",
    )
    object_storage_region: str = Field(default="us-east-1", alias="OBJECT_STORAGE_REGION")
    object_storage_access_key_id: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ACCESS_KEY_ID",
    )
    object_storage_secret_access_key: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_SECRET_ACCESS_KEY",
    )

    # File upload limits
    max_upload_size_mb: int = Field(default=512, alias="MAX_UPLOAD_SIZE_MB")

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
