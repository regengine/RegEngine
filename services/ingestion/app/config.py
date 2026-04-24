"""Configuration for the ingestion service."""

import logging
import warnings
from functools import lru_cache
from typing import Optional

from pydantic import Field
from shared.base_config import BaseServiceSettings, ObjectStorageMixin
from shared.api_key_env import has_configured_api_key

_logger = logging.getLogger(__name__)


class Settings(ObjectStorageMixin, BaseServiceSettings):
    """Environment-driven configuration values."""

    kafka_topic_dlq: str = "ingest.dlq"

    # Search / Discovery
    google_api_key: Optional[str] = None
    google_cx: Optional[str] = None
    discovery_query: str = "site:gov filetype:pdf FSMA food traceability"

    raw_bucket: str = Field(default="reg-engine-raw-data-dev", alias="RAW_DATA_BUCKET")
    processed_bucket: str = Field(
        default="reg-engine-processed-data-dev", alias="PROCESSED_DATA_BUCKET"
    )
    kafka_bootstrap_servers: str = Field(
        default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_topic_normalized: str = Field(
        default="ingest.normalized", alias="KAFKA_TOPIC_NORMALIZED"
    )
    api_key: Optional[str] = Field(default=None, alias="API_KEY")
    auth_test_bypass_token: Optional[str] = Field(default=None, alias="AUTH_TEST_BYPASS_TOKEN")
    env: str = Field(default="development", alias="ENV")
    allowed_origins: str = Field(
        default="https://regengine.co,https://www.regengine.co",
        alias="ALLOWED_ORIGINS",
    )

    # Neo4j Graph Database
    neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    # AI & Cache
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    redis_url: str = Field(default="rediss://redis:6379/0", alias="REDIS_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance.

    Warns loudly if no supported API key env var is configured in a
    production-like environment
    so operators notice immediately instead of silently falling back.
    """
    from shared.env import is_production
    settings = Settings()
    _is_prod = is_production()
    if not has_configured_api_key() and _is_prod:
        msg = (
            "REGENGINE_API_KEY/API_KEY env var is not set in production. "
            "Webhook ingestion will reject all requests until configured."
        )
        _logger.warning(msg)
        warnings.warn(msg, stacklevel=2)

    # Block AUTH_TEST_BYPASS_TOKEN in production — fail closed.
    if _is_prod and settings.auth_test_bypass_token:
        _logger.warning(
            "AUTH_TEST_BYPASS_TOKEN is set in a production environment — "
            "forcing it to None. Remove this env var from your production config."
        )
        settings.auth_test_bypass_token = None

    return settings
