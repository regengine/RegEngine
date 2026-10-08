"""QA deep pass: ``shared.secrets_manager`` behavior.

This module had no dedicated tests. These tests exercise it only
(product edits here belong to another worker). Covered:

1. ``get_secret`` namespace mapping, missing secret, invalid JSON,
   and ``lru_cache`` staleness behavior.
2. Credential getters and their localhost fallbacks.
3. ``validate_production_secrets`` skip/fail/pass matrix.
4. ``require_secure_secrets_in_production`` skip-check gate.
5. ``get_secrets_manager`` singleton.

No network, no disk. Env vars are monkeypatched per test.
"""

from __future__ import annotations

import pytest
from shared import secrets_manager as sm


@pytest.fixture(autouse=True)
def _fresh_singleton(monkeypatch):
    monkeypatch.setattr(sm, "_secrets_manager", None)
    mgr = sm.SecretsManager()
    mgr.get_secret.cache_clear()
    yield
    mgr.get_secret.cache_clear()
    sm._secrets_manager = None


def _mgr() -> sm.SecretsManager:
    mgr = sm.SecretsManager()
    mgr.get_secret.cache_clear()
    return mgr


# ---------------------------------------------------------------------------
# 1. get_secret
# ---------------------------------------------------------------------------


class TestGetSecret:
    def test_missing_secret_returns_empty_dict(self):
        assert _mgr().get_secret("regengine/test/missing") == {}

    def test_namespace_maps_to_env_key(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_DB", '{"user": "u"}')
        assert _mgr().get_secret("regengine/test/db") == {"user": "u"}

    def test_invalid_json_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_BAD", "not-json{{{")
        with pytest.raises(RuntimeError, match="Failed to retrieve secret"):
            _mgr().get_secret("regengine/test/bad")

    def test_result_is_cached_per_instance(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_C", '{"v": 1}')
        mgr = _mgr()
        first = mgr.get_secret("regengine/test/c")
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_C", '{"v": 2}')
        assert mgr.get_secret("regengine/test/c") == first == {"v": 1}

    def test_cache_clear_picks_up_rotation(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_R", '{"v": 1}')
        mgr = _mgr()
        assert mgr.get_secret("regengine/test/r") == {"v": 1}
        monkeypatch.setenv("REGENGINE_SECRET_REGENGINE_TEST_R", '{"v": 2}')
        mgr.get_secret.cache_clear()
        assert mgr.get_secret("regengine/test/r") == {"v": 2}


# ---------------------------------------------------------------------------
# 2. Credential getters
# ---------------------------------------------------------------------------


class TestCredentialGetters:
    def test_database_credentials_from_env(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "db.internal")
        monkeypatch.setenv("POSTGRES_USER", "app")
        monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        monkeypatch.setenv("POSTGRES_DB", "appdb")
        creds = _mgr().get_database_credentials()
        assert creds == {
            "username": "app",
            "password": "pw",
            "host": "db.internal",
            "port": "5433",
            "database": "appdb",
        }

    def test_database_host_defaults_to_localhost(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        assert _mgr().get_database_credentials()["host"] == "localhost"

    def test_neo4j_uri_and_url_fallbacks(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://neo:7687")
        assert _mgr().get_neo4j_credentials()["uri"] == "bolt://neo:7687"
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("NEO4J_URL", "bolt://neo2:7687")
        assert _mgr().get_neo4j_credentials()["uri"] == "bolt://neo2:7687"
        monkeypatch.delenv("NEO4J_URL", raising=False)
        assert _mgr().get_neo4j_credentials()["uri"] == "bolt://localhost:7687"

    def test_kafka_defaults(self, monkeypatch):
        monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
        creds = _mgr().get_kafka_credentials()
        assert creds["bootstrap_servers"] == "localhost:9092"
        assert creds["security_protocol"] == "PLAINTEXT"

    def test_s3_credentials_shape(self, monkeypatch):
        monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "AKID")
        monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "secret")
        creds = _mgr().get_s3_credentials()
        assert creds["access_key_id"] == "AKID"
        assert creds["secret_access_key"] == "secret"
        assert creds["region"] == "us-east-1"

    def test_module_convenience_functions_delegate(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "h")
        assert sm.get_database_credentials()["host"] == "h"
        assert "uri" in sm.get_neo4j_credentials()
        assert "bootstrap_servers" in sm.get_kafka_credentials()
        assert "access_key_id" in sm.get_s3_credentials()


# ---------------------------------------------------------------------------
# 3. validate_production_secrets
# ---------------------------------------------------------------------------


def _prod_env(monkeypatch, **overrides):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("NEO4J_PASSWORD", "a-strong-neo4j-password-value")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "a-strong-object-secret")
    for key, value in overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


class TestValidateProductionSecrets:
    def test_skipped_outside_production(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        sm.validate_production_secrets()

    def test_healthy_production_passes(self, monkeypatch):
        _prod_env(monkeypatch)
        sm.validate_production_secrets()

    def test_missing_secret_fails(self, monkeypatch):
        _prod_env(monkeypatch, NEO4J_PASSWORD=None)
        with pytest.raises(RuntimeError, match="NEO4J_PASSWORD is not set"):
            sm.validate_production_secrets()

    @pytest.mark.parametrize("weak", ["change-me", "password", "test", "test-key", "demo123"])
    def test_insecure_defaults_fail(self, monkeypatch, weak):
        _prod_env(monkeypatch, NEO4J_PASSWORD=weak)
        with pytest.raises(RuntimeError, match="insecure default"):
            sm.validate_production_secrets()

    def test_exact_test_storage_pair_fails(self, monkeypatch):
        _prod_env(
            monkeypatch,
            OBJECT_STORAGE_ACCESS_KEY_ID="test",
            OBJECT_STORAGE_SECRET_ACCESS_KEY="test",
        )
        with pytest.raises(RuntimeError, match="OBJECT_STORAGE"):
            sm.validate_production_secrets()


# ---------------------------------------------------------------------------
# 4. require_secure_secrets_in_production
# ---------------------------------------------------------------------------


class TestRequireSecureSecrets:
    def test_noop_outside_production(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("REGENGINE_SKIP_SECRET_CHECK", "true")
        sm.require_secure_secrets_in_production()

    def test_skip_flag_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.setenv("REGENGINE_SKIP_SECRET_CHECK", "true")
        with pytest.raises(RuntimeError, match="REGENGINE_SKIP_SECRET_CHECK"):
            sm.require_secure_secrets_in_production()

    def test_unset_flag_passes_in_production(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        monkeypatch.delenv("REGENGINE_SKIP_SECRET_CHECK", raising=False)
        sm.require_secure_secrets_in_production()


# ---------------------------------------------------------------------------
# 5. Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_secrets_manager_returns_singleton(self):
        assert sm.get_secrets_manager() is sm.get_secrets_manager()

    def test_region_name_retained(self):
        assert sm.get_secrets_manager(region_name="eu-west-1").region_name == "eu-west-1"
