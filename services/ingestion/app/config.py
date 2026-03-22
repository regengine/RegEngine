"""Configuration for the ingestion service."""

import logging
import warnings
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Environment-driven configuration values."""

    kafka_topic_normalized: str = "ingest.normalized"
    kafka_topic_dlq: str = "ingest.dlq"

    # Search / Discovery
    google_api_key: Optional[str] = None
    google_cx: Optional[str] = None
    discovery_query: str = "site:gov filetype:pdf FSMA food traceability"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    raw_bucket: str = Field(default="reg-engine-raw-data-dev", alias="RAW_DATA_BUCKET")
    processed_bucket: str = Field(
        default="reg-engine-processed-data-dev", alias="PROCESSED_DATA_BUCKET"
    )
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
    kafka_bootstrap_servers: str = Field(
        default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_normalized: str = Field(
        default="ingest.normalized", alias="KAFKA_TOPIC_NORMALIZED"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_key: Optional[str] = Field(default=None, alias="API_KEY")
    auth_test_bypass_token: Optional[str] = Field(default=None, alias="AUTH_TEST_BYPASS_TOKEN")
    env: str = Field(default="development", alias="ENV")
    allowed_origins: str = Field(
        default="http://localhost:3000,https://regengine.co,https://www.regengine.co",
        alias="ALLOWED_ORIGINS",
    )

    # Neo4j Graph Database
    neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    # AI & Cache
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance.

    Warns loudly if API_KEY is not configured in a production-like environment
    so operators notice immediately instead of silently falling back.
    """
    import os
    settings = Settings()
    _regengine_env = os.getenv("REGENGINE_ENV", "").lower()
    _is_prod = (
        _regengine_env == "production"
        or settings.env.lower() == "production"
    )
    if settings.api_key is None and _is_prod:
        msg = (
            "API_KEY env var is not set in production. "
            "Webhook ingestion will reject all requests until configured."
        )
        _logger.warning(msg)
        warnings.warn(msg, stacklevel=2)
    return settings
