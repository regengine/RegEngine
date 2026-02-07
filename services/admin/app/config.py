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

    # S3/Storage configuration
    pcos_bucket: str = Field(default="reg-engine-pcos-data-dev", alias="PCOS_DATA_BUCKET")
    aws_endpoint_url: Optional[str] = Field(default=None, alias="AWS_ENDPOINT_URL")
    aws_region: str = Field(default="us-east-1", alias="AWS_DEFAULT_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    # File upload limits
    max_upload_size_mb: int = Field(default=10, alias="MAX_UPLOAD_SIZE_MB")

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
