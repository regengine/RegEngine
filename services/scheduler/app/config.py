"""Configuration management for the scheduler service."""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from shared.base_config import BaseServiceSettings

_logger = logging.getLogger(__name__)

_DEV_DATABASE_URL = "postgresql://regengine:regengine@postgres:5432/regengine"


class SchedulerSettings(BaseServiceSettings):
    """Scheduler service configuration."""

    # Database
    database_url: str = Field(
        default="",
        description="PostgreSQL connection URL",
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="redpanda:9092",
        description="Kafka bootstrap servers",
    )
    kafka_topic_enforcement: str = Field(
        default="enforcement.changes",
        description="Topic for enforcement change events",
    )
    kafka_topic_alerts: str = Field(
        default="alerts.regulatory",
        description="Topic for alert events",
    )
    kafka_topic_fsma: str = Field(
        default="fsma.events.extracted",
        description="Topic for FSMA trace events (consumed by graph service)",
    )

    # Redis (for circuit breaker state)
    redis_url: str = Field(
        default="rediss://redis:6379/1",
        description="Redis URL for circuit breaker state",
    )

    # API Keys
    scheduler_api_key: str = Field(
        default="",
        description="API key for calling internal services",
    )

    # Ingestion service
    ingestion_service_url: str = Field(
        default="http://ingestion-service:8000",
        description="Ingestion service base URL",
    )

    # Scraping intervals (minutes)
    fda_warning_letters_interval: int = Field(
        default=60,
        description="FDA Warning Letters polling interval in minutes",
    )
    fda_import_alerts_interval: int = Field(
        default=120,
        description="FDA Import Alerts polling interval in minutes",
    )
    fda_recalls_interval: int = Field(
        default=30,
        description="FDA Recalls polling interval in minutes",
    )
    regulatory_discovery_interval: int = Field(
        default=1440,
        description="Regulatory Discovery bulk sync interval in minutes (Nightly)",
    )
    discovery_timeout_seconds: int = Field(
        default=300,
        description="Timeout for regulatory discovery requests",
    )

    # Webhooks
    webhook_urls: str = Field(
        default="",
        description="Comma-separated webhook URLs for notifications",
    )
    webhook_timeout_seconds: int = Field(
        default=10,
        description="Webhook delivery timeout",
    )
    webhook_max_retries: int = Field(
        default=3,
        description="Maximum webhook delivery retries",
    )
    # #1150 — path to on-disk JSONL outbox for persisted failed
    # deliveries. Leave empty to disable persistence (dead-letter stays
    # in-memory only and is lost on restart — the legacy behavior).
    # In production this should point to a mounted volume so retries
    # survive container restarts.
    webhook_outbox_path: str = Field(
        default="",
        description=(
            "Filesystem path for the persistent webhook outbox (JSONL). "
            "Empty disables persistence (legacy behavior)."
        ),
    )
    # #1150 — how often to drain the outbox. 60s is a good default: long
    # enough that transient issues resolve between passes, short enough
    # that delivery latency stays modest once the endpoint recovers.
    webhook_outbox_drain_interval_seconds: int = Field(
        default=60,
        description="Interval (seconds) between outbox drain passes",
    )

    # Circuit breaker
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Number of failures before circuit opens",
    )
    circuit_breaker_recovery_timeout: int = Field(
        default=300,
        description="Seconds before attempting recovery after circuit opens",
    )

    # Health check
    health_port: int = Field(
        default=8600,
        description="Port for health check HTTP server",
    )

    # Metrics
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics",
    )

    @property
    def webhook_url_list(self) -> List[str]:
        """Parse webhook URLs from comma-separated string."""
        if not self.webhook_urls:
            return []
        return [url.strip() for url in self.webhook_urls.split(",") if url.strip()]


@lru_cache(maxsize=1)
def get_settings() -> SchedulerSettings:
    """Get cached settings instance."""
    settings = SchedulerSettings()

    _regengine_env = os.getenv("REGENGINE_ENV", "").lower()
    _is_prod = (
        _regengine_env == "production"
        or os.getenv("ENV", "").lower() == "production"
    )

    # --- C-2: database_url must not use hardcoded dev credentials in prod ---
    if not settings.database_url or settings.database_url == _DEV_DATABASE_URL:
        if _is_prod:
            raise ValueError(
                "DATABASE_URL environment variable must be set in production. "
                "Refusing to start with default credentials."
            )
        _logger.warning(
            "DATABASE_URL not set — using dev default. Do NOT use in production."
        )
        settings.database_url = _DEV_DATABASE_URL

    # --- S-3: scheduler_api_key must not use hardcoded dev key in prod ---
    if not settings.scheduler_api_key or settings.scheduler_api_key == "dev-scheduler-key":
        if _is_prod:
            raise ValueError(
                "SCHEDULER_API_KEY must be set in production. "
                "Refusing to start with default API key."
            )
        generated_key = secrets.token_urlsafe(32)
        _logger.warning(
            "SCHEDULER_API_KEY not set — generating random dev key. "
            "Do NOT use in production."
        )
        settings.scheduler_api_key = generated_key

    return settings
