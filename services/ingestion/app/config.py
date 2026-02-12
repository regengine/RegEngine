"""Configuration for the ingestion service."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration values."""

    kafka_topic_normalized: str = "ingest.normalized"
    kafka_topic_dlq: str = "ingest.dlq"

    # Search / Discovery
    google_api_key: Optional[str] = None
    google_cx: Optional[str] = None
    discovery_query: str = "site:gov filetype:pdf financial regulation"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    raw_bucket: str = Field(default="reg-engine-raw-data-dev", alias="RAW_DATA_BUCKET")
    processed_bucket: str = Field(
        default="reg-engine-processed-data-dev", alias="PROCESSED_DATA_BUCKET"
    )
    aws_endpoint_url: Optional[str] = Field(default=None, alias="AWS_ENDPOINT_URL")
    aws_region: str = Field(default="us-east-1", alias="AWS_DEFAULT_REGION")
    aws_access_key_id: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(
        default=None, alias="AWS_SECRET_ACCESS_KEY"
    )
    kafka_bootstrap_servers: str = Field(
        default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_normalized: str = Field(
        default="ingest.normalized", alias="KAFKA_TOPIC_NORMALIZED"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    auth_test_bypass_token: Optional[str] = Field(default=None, alias="AUTH_TEST_BYPASS_TOKEN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    if not settings.api_key and settings.auth_test_bypass_token:
        settings.api_key = settings.auth_test_bypass_token
    return settings
