"""
Tests for the Scheduler service.

Validates configuration loading, scraper initialization, and
circuit breaker behavior.
"""

import os
import pytest
from pathlib import Path


class TestSchedulerConfig:
    """Test configuration loading and defaults."""

    def test_default_settings_load(self):
        """Config class should instantiate with sensible defaults."""
        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.database_url.startswith("postgresql://")
        assert settings.kafka_bootstrap_servers == "redpanda:9092"
        assert settings.fda_warning_letters_interval == 60
        assert settings.fda_recalls_interval == 30
        assert settings.health_port == 8600

    def test_webhook_url_parsing_empty(self):
        """Empty webhook string should yield empty list."""
        from app.config import SchedulerSettings

        settings = SchedulerSettings(webhook_urls="")
        assert settings.webhook_url_list == []

    def test_webhook_url_parsing_multiple(self):
        """Comma-separated URLs should be split correctly."""
        from app.config import SchedulerSettings

        settings = SchedulerSettings(webhook_urls="https://a.com/hook, https://b.com/hook")
        assert len(settings.webhook_url_list) == 2
        assert settings.webhook_url_list[0] == "https://a.com/hook"
        assert settings.webhook_url_list[1] == "https://b.com/hook"

    def test_get_settings_cached(self):
        """get_settings should return the same cached instance."""
        from app.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestSchedulerDirectoryStructure:
    """Verify the scheduler service has the expected layout."""

    def test_app_directory_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "app").is_dir(), "Missing app/ directory"

    def test_requirements_file_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "requirements.txt").is_file(), "Missing requirements.txt"

    def test_config_module_exists(self):
        service_dir = Path(__file__).resolve().parent.parent
        assert (service_dir / "app" / "config.py").is_file(), "Missing app/config.py"


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration."""

    def test_defaults(self):
        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.circuit_breaker_failure_threshold == 5
        assert settings.circuit_breaker_recovery_timeout == 300

    def test_can_override_via_env(self, monkeypatch):
        """Circuit breaker values should be overridable via env vars."""
        monkeypatch.setenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "10")
        monkeypatch.setenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "600")

        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.circuit_breaker_failure_threshold == 10
        assert settings.circuit_breaker_recovery_timeout == 600


class TestKafkaTopicConfig:
    """Verify Kafka topic configuration defaults."""

    def test_enforcement_topic(self):
        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.kafka_topic_enforcement == "enforcement.changes"

    def test_alerts_topic(self):
        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.kafka_topic_alerts == "alerts.regulatory"

    def test_fsma_topic(self):
        from app.config import SchedulerSettings

        settings = SchedulerSettings()
        assert settings.kafka_topic_fsma == "fsma.events.extracted"
