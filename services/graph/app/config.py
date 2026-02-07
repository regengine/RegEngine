from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration values."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    kafka_bootstrap: str = Field(
        default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    topic_in: str = Field(default="nlp.extracted", alias="KAFKA_TOPIC_NLP")
    topic_dlq: str = Field(default="fsma.events.dlq", alias="KAFKA_TOPIC_DLQ")
    schema_registry_url: str = Field(
        default="http://schema-registry:8081", alias="SCHEMA_REGISTRY_URL"
    )
    consumer_group_id: str = Field(
        default="fsma-graph-service", alias="KAFKA_CONSUMER_GROUP_ID"
    )
    neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    # No default password - must be set via environment variable
    neo4j_password: str = Field(alias="NEO4J_PASSWORD")
    neo4j_pool_size: int = Field(default=50, alias="NEO4J_POOL_SIZE")
    neo4j_pool_timeout: float = Field(default=60.0, alias="NEO4J_POOL_TIMEOUT")
    neo4j_max_lifetime: int = Field(default=3600, alias="NEO4J_MAX_LIFETIME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


settings = get_settings()
