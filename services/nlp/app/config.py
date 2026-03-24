from functools import lru_cache

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration values."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    object_storage_endpoint_url: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ENDPOINT_URL",
    )
    raw_bucket: str = Field(default="reg-engine-raw-data-dev", alias="RAW_DATA_BUCKET")
    processed_bucket: str = Field(
        default="reg-engine-processed-data-dev", alias="PROCESSED_DATA_BUCKET"
    )
    kafka_bootstrap: str = Field(
        default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    topic_in: str = Field(default="ingest.normalized", alias="KAFKA_TOPIC_NORMALIZED")
    topic_out: str = Field(default="nlp.extracted", alias="KAFKA_TOPIC_NLP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Extraction Thresholds (SR 11-7 validation)
    extraction_confidence_high: float = Field(
        default=0.95, 
        ge=0.0, le=1.0, 
        alias="EXTRACTION_CONFIDENCE_HIGH"
    )
    extraction_confidence_medium: float = Field(
        default=0.85, 
        ge=0.0, le=1.0, 
        alias="EXTRACTION_CONFIDENCE_MEDIUM"
    )
    graph_service_url: str = Field(
        default="http://graph-service:8200",
        alias="GRAPH_SERVICE_URL",
    )
    graph_request_timeout_s: float = Field(
        default=15.0,
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
    """Return cached settings instance."""

    return Settings()


try:
    settings = get_settings()
except Exception as exc:
    import logging as _logging

    _logging.getLogger(__name__).error(
        "Failed to load NLP settings: %s. Falling back to defaults.", exc
    )
    # Provide a Settings instance with defaults so the module remains importable
    # in test environments with incomplete env vars.
    settings = Settings.model_construct(
        object_storage_endpoint_url=None,
        raw_bucket="reg-engine-raw-data-dev",
        processed_bucket="reg-engine-processed-data-dev",
        kafka_bootstrap="redpanda:9092",
        topic_in="ingest.normalized",
        topic_out="nlp.extracted",
        log_level="INFO",
        extraction_confidence_high=0.95,
        extraction_confidence_medium=0.85,
        graph_service_url="http://graph-service:8200",
        graph_request_timeout_s=15.0,
        internal_service_secret=None,
    )
