"""Coverage for app/config.py — environment-driven settings + lru_cache getter.

Locks the field shape of Settings and the production guardrails in
get_settings() (API_KEY warning + AUTH_TEST_BYPASS_TOKEN force-to-None).

Issue: #1342
"""

from __future__ import annotations

import warnings

import pytest

from app import config as cfg
from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """get_settings is @lru_cache(maxsize=1) — flush between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def _clear_env(monkeypatch):
    """Strip config-relevant env vars so the default values take effect."""
    for var in (
        "RAW_DATA_BUCKET", "PROCESSED_DATA_BUCKET", "KAFKA_BOOTSTRAP_SERVERS",
        "KAFKA_TOPIC_NORMALIZED", "API_KEY", "AUTH_TEST_BYPASS_TOKEN",
        "ENV", "ALLOWED_ORIGINS", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
        "GROQ_API_KEY", "REDIS_URL", "GOOGLE_API_KEY", "GOOGLE_CX",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class TestSettingsDefaults:
    def test_kafka_dlq_default(self, _clear_env):
        s = Settings()
        assert s.kafka_topic_dlq == "ingest.dlq"

    def test_google_keys_none_by_default(self, _clear_env):
        s = Settings()
        assert s.google_api_key is None
        assert s.google_cx is None

    def test_discovery_query_default(self, _clear_env):
        s = Settings()
        assert "FSMA" in s.discovery_query

    def test_bucket_defaults(self, _clear_env):
        s = Settings()
        assert s.raw_bucket == "reg-engine-raw-data-dev"
        assert s.processed_bucket == "reg-engine-processed-data-dev"

    def test_kafka_bootstrap_default(self, _clear_env):
        s = Settings()
        assert s.kafka_bootstrap_servers == "redpanda:9092"

    def test_kafka_topic_normalized_default(self, _clear_env):
        s = Settings()
        assert s.kafka_topic_normalized == "ingest.normalized"

    def test_api_key_none_by_default(self, _clear_env):
        s = Settings()
        assert s.api_key is None

    def test_auth_test_bypass_none_by_default(self, _clear_env):
        s = Settings()
        assert s.auth_test_bypass_token is None

    def test_env_default_development(self, _clear_env):
        s = Settings()
        assert s.env == "development"

    def test_allowed_origins_default(self, _clear_env):
        s = Settings()
        assert "regengine.co" in s.allowed_origins

    def test_neo4j_defaults(self, _clear_env):
        s = Settings()
        assert s.neo4j_uri == "bolt://neo4j:7687"
        assert s.neo4j_user == "neo4j"
        assert s.neo4j_password == ""

    def test_groq_key_none_default(self, _clear_env):
        s = Settings()
        assert s.groq_api_key is None

    def test_redis_url_default(self, _clear_env):
        s = Settings()
        assert s.redis_url == "rediss://redis:6379/0"


class TestSettingsEnvOverrides:
    def test_api_key_from_env(self, monkeypatch, _clear_env):
        monkeypatch.setenv("API_KEY", "secret-123")
        s = Settings()
        assert s.api_key == "secret-123"

    def test_raw_bucket_from_env(self, monkeypatch, _clear_env):
        monkeypatch.setenv("RAW_DATA_BUCKET", "my-bucket")
        s = Settings()
        assert s.raw_bucket == "my-bucket"

    def test_processed_bucket_from_env(self, monkeypatch, _clear_env):
        monkeypatch.setenv("PROCESSED_DATA_BUCKET", "processed-xyz")
        s = Settings()
        assert s.processed_bucket == "processed-xyz"

    def test_env_from_env_var(self, monkeypatch, _clear_env):
        monkeypatch.setenv("ENV", "production")
        s = Settings()
        assert s.env == "production"

    def test_allowed_origins_override(self, monkeypatch, _clear_env):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://custom.com")
        s = Settings()
        assert s.allowed_origins == "https://custom.com"

    def test_neo4j_password_from_env(self, monkeypatch, _clear_env):
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        s = Settings()
        assert s.neo4j_password == "secret"

    def test_auth_test_bypass_from_env(self, monkeypatch, _clear_env):
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "bypass-abc")
        s = Settings()
        assert s.auth_test_bypass_token == "bypass-abc"


# ---------------------------------------------------------------------------
# get_settings() — lru_cache + production guardrails
# ---------------------------------------------------------------------------


class TestGetSettingsCaching:
    def test_returns_settings_instance(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: False)
        result = get_settings()
        assert isinstance(result, Settings)

    def test_caches_same_instance(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: False)
        first = get_settings()
        second = get_settings()
        assert first is second

    def test_cache_survives_until_clear(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: False)
        first = get_settings()
        get_settings.cache_clear()
        second = get_settings()
        # Different instance after cache_clear
        assert first is not second


class TestGetSettingsProductionGuardrails:
    def test_missing_api_key_in_production_warns(self, _clear_env, monkeypatch, caplog):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            with caplog.at_level("WARNING"):
                get_settings()
            # Warning emitted both to stdlib warnings and logger
            assert any("API_KEY" in str(w.message) for w in recorded)

    def test_missing_api_key_in_production_logs_warning(self, _clear_env, monkeypatch, caplog):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        with caplog.at_level("WARNING"):
            get_settings()
        assert any("API_KEY" in rec.message for rec in caplog.records)

    def test_api_key_present_in_production_no_warning(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        monkeypatch.setenv("API_KEY", "valid-key")
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            s = get_settings()
        api_warnings = [w for w in recorded if "API_KEY" in str(w.message)]
        assert api_warnings == []
        assert s.api_key == "valid-key"

    def test_regengine_api_key_present_in_production_no_warning(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        monkeypatch.setenv("REGENGINE_API_KEY", "valid-key")
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            s = get_settings()
        api_warnings = [w for w in recorded if "API_KEY" in str(w.message)]
        assert api_warnings == []
        assert s.api_key is None

    def test_missing_api_key_in_dev_no_warning(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: False)
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            s = get_settings()
        api_warnings = [w for w in recorded if "API_KEY" in str(w.message)]
        assert api_warnings == []
        assert s.api_key is None

    def test_auth_bypass_token_forced_none_in_production(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        monkeypatch.setenv("API_KEY", "x")  # suppress the API_KEY warning
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "should-be-killed")
        s = get_settings()
        assert s.auth_test_bypass_token is None

    def test_auth_bypass_token_forced_none_logs_warning(self, _clear_env, monkeypatch, caplog):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        monkeypatch.setenv("API_KEY", "x")
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "should-be-killed")
        with caplog.at_level("WARNING"):
            get_settings()
        assert any("AUTH_TEST_BYPASS_TOKEN" in rec.message for rec in caplog.records)

    def test_auth_bypass_preserved_in_dev(self, _clear_env, monkeypatch):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: False)
        monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "dev-bypass")
        s = get_settings()
        assert s.auth_test_bypass_token == "dev-bypass"

    def test_auth_bypass_none_in_production_does_not_warn(self, _clear_env, monkeypatch, caplog):
        import shared.env as shared_env
        monkeypatch.setattr(shared_env, "is_production", lambda: True)
        monkeypatch.setenv("API_KEY", "x")
        # AUTH_TEST_BYPASS_TOKEN not set -> None
        with caplog.at_level("WARNING"):
            get_settings()
        bypass_warnings = [r for r in caplog.records if "AUTH_TEST_BYPASS_TOKEN" in r.message]
        assert bypass_warnings == []


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_exports(self):
        assert hasattr(cfg, "Settings")
        assert hasattr(cfg, "get_settings")

    def test_settings_inherits_mixins(self):
        from shared.base_config import BaseServiceSettings, ObjectStorageMixin
        assert issubclass(Settings, BaseServiceSettings)
        assert issubclass(Settings, ObjectStorageMixin)
