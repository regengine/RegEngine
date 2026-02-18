"""Configuration management for the scheduler service."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class SchedulerSettings(BaseSettings):
    """Scheduler service configuration."""

    # Database
    database_url: str = Field(
        default="postgresql://regengine:regengine@postgres:5432/regengine",
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
        default="redis://redis:6379/1",
        description="Redis URL for circuit breaker state",
    )

    # API Keys
    scheduler_api_key: str = Field(
        default="dev-scheduler-key",
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

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> SchedulerSettings:
    """Get cached settings instance."""
    return SchedulerSettings()
