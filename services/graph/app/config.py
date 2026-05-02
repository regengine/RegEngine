from functools import lru_cache

from pydantic import Field
from shared.base_config import BaseServiceSettings


class Settings(BaseServiceSettings):
    """Environment-driven configuration values."""

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
    neo4j_uri: str = Field(default="bolt+s://neo4j:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    # Keep imports/startup non-fatal when Neo4j is intentionally disabled; the
    # readiness probe and client connection path report missing credentials.
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")
    neo4j_pool_size: int = Field(default=50, alias="NEO4J_POOL_SIZE")
    neo4j_pool_timeout: float = Field(default=60.0, alias="NEO4J_POOL_TIMEOUT")
    neo4j_max_lifetime: int = Field(default=3600, alias="NEO4J_MAX_LIFETIME")
    # TLS encryption for Bolt connections (NIST SC-8, #985).
    # bolt+s:// enables TLS with system CA verification.
    # bolt+ssc:// enables TLS with self-signed cert acceptance (dev only).
    # bolt:// disables TLS (set NEO4J_URI=bolt://neo4j:7687 for local dev).
    neo4j_encrypted: bool = Field(default=True, alias="NEO4J_ENCRYPTED")
    # Per-tenant database isolation requires Neo4j Enterprise (Community
    # supports only a single user database). When true, ``Neo4jClient`` honors
    # the ``database=`` constructor argument. When false (Community / default),
    # the client is pinned to the global database and tenant isolation is
    # property-based (``tenant_id`` predicates on every MATCH/MERGE). See
    # issue #1229.
    neo4j_enterprise: bool = Field(default=False, alias="NEO4J_ENTERPRISE")

    # Security & Compliance Patterns
    redaction_patterns: list[str] = Field(
        default=[
            r"password\s*=\s*'[^']*'",
            r"password\s*=\s*\"[^\"]*\"",
            r"secret\s*=\s*'[^']*'",
            r"api_key\s*=\s*'[^']*'",
            r"token\s*=\s*'[^']*'",
            r"ssn\s*=\s*'[^']*'",
            r"credit_card\s*=\s*'[^']*'"
        ],
        alias="REDACTION_PATTERNS"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


settings = get_settings()
