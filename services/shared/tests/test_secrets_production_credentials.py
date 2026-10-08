"""Production credential gates in ``shared.secrets_manager``.

Before this fix the credential getters silently fell back to localhost with
empty passwords no matter the environment, and ``validate_production_secrets``
only checked 3 variables, so a production deploy missing its secret wiring
would boot against localhost fallbacks. Now the getters raise in production
(central ``shared.env`` detection, explicit ``environment`` argument wins)
while local development keeps its localhost defaults, and the startup
validator requires ``DATABASE_URL`` plus only the credentials of enabled
subsystems (Kafka iff ``EVENT_BACKBONE=kafka``), while still rejecting insecure placeholders
whenever they are set (#3243).

All key material below is synthetic. Every test scrubs the credential and
environment-detection variables first so the host environment cannot make a
case accidentally pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from shared.secrets_manager import (
    REQUIRED_PRODUCTION_CREDENTIALS,
    SecretsManager,
    validate_production_secrets,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_MAIN = REPO_ROOT / "server" / "main.py"

_CRED_VARS = (
    "REGENGINE_ENV",
    "ENV",
    "ENVIRONMENT",
    "DATABASE_URL",
    "ENABLED_ROUTERS",
    "EVENT_BACKBONE",
    "REGENGINE_SKIP_SECRET_CHECK",
    "POSTGRES_HOST",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "NEO4J_URI",
    "NEO4J_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_USERNAME",
    "KAFKA_PASSWORD",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)

_SECURE_CREDS = {
    "DATABASE_URL": "postgresql://synthetic-prod-host:5432/regengine",
    "POSTGRES_HOST": "synthetic-postgres-host",
    "POSTGRES_PASSWORD": "synthetic-postgres-passphrase-7d1c",  # pragma: allowlist secret
    "NEO4J_URI": "bolt://synthetic-neo4j:7687",
    "NEO4J_PASSWORD": "synthetic-neo4j-passphrase-9f2a",  # pragma: allowlist secret
    "KAFKA_BOOTSTRAP_SERVERS": "synthetic-kafka:9092",
    "OBJECT_STORAGE_ACCESS_KEY_ID": "SYNTHETICACCESSKEYID",  # pragma: allowlist secret
    "OBJECT_STORAGE_SECRET_ACCESS_KEY": "synthetic-object-storage-secret",  # pragma: allowlist secret
}


@pytest.fixture
def clean_env(monkeypatch):
    """Scrub every credential and env-detection variable."""
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def production(clean_env):
    """Scrubbed environment pinned to production via REGENGINE_ENV."""
    clean_env.setenv("REGENGINE_ENV", "production")
    return clean_env


@pytest.fixture
def manager():
    return SecretsManager()


class TestDatabaseCredentials:
    def test_dev_falls_back_to_localhost(self, clean_env, manager):
        creds = manager.get_database_credentials()
        assert creds["host"] == "localhost"
        assert creds["password"] == ""

    def test_production_missing_raises(self, production, manager):
        with pytest.raises(RuntimeError) as exc_info:
            manager.get_database_credentials()
        message = str(exc_info.value)
        assert "POSTGRES_HOST" in message
        assert "POSTGRES_PASSWORD" in message

    def test_production_explicit_values_pass_through(self, production, manager):
        production.setenv("POSTGRES_HOST", "synthetic-postgres-host")
        production.setenv("POSTGRES_PASSWORD", "synthetic-pass")  # pragma: allowlist secret
        creds = manager.get_database_credentials()
        assert creds["host"] == "synthetic-postgres-host"
        assert creds["password"] == "synthetic-pass"  # pragma: allowlist secret

    def test_explicit_environment_argument_wins_over_env(self, clean_env, manager):
        clean_env.setenv("REGENGINE_ENV", "development")
        with pytest.raises(RuntimeError):
            manager.get_database_credentials(environment="production")
        clean_env.setenv("REGENGINE_ENV", "production")
        creds = manager.get_database_credentials(environment="development")
        assert creds["host"] == "localhost"


class TestNeo4jCredentials:
    def test_dev_falls_back_to_localhost(self, clean_env, manager):
        creds = manager.get_neo4j_credentials()
        assert creds["uri"] == "bolt://localhost:7687"
        assert creds["password"] == ""

    def test_production_missing_raises(self, production, manager):
        with pytest.raises(RuntimeError) as exc_info:
            manager.get_neo4j_credentials()
        message = str(exc_info.value)
        assert "NEO4J_URI" in message
        assert "NEO4J_PASSWORD" in message

    def test_production_legacy_url_alias_satisfies_uri(self, production, manager):
        production.setenv("NEO4J_URL", "bolt://synthetic-neo4j:7687")
        production.setenv("NEO4J_PASSWORD", "synthetic-pass")  # pragma: allowlist secret
        creds = manager.get_neo4j_credentials()
        assert creds["uri"] == "bolt://synthetic-neo4j:7687"

    def test_explicit_environment_argument_wins_over_env(self, clean_env, manager):
        clean_env.setenv("REGENGINE_ENV", "development")
        with pytest.raises(RuntimeError):
            manager.get_neo4j_credentials(environment="production")


class TestKafkaCredentials:
    def test_dev_falls_back_to_localhost(self, clean_env, manager):
        creds = manager.get_kafka_credentials()
        assert creds["bootstrap_servers"] == "localhost:9092"

    def test_production_missing_raises(self, production, manager):
        with pytest.raises(RuntimeError) as exc_info:
            manager.get_kafka_credentials()
        assert "KAFKA_BOOTSTRAP_SERVERS" in str(exc_info.value)

    def test_production_explicit_values_pass_through(self, production, manager):
        production.setenv("KAFKA_BOOTSTRAP_SERVERS", "synthetic-kafka:9092")
        creds = manager.get_kafka_credentials()
        assert creds["bootstrap_servers"] == "synthetic-kafka:9092"


class TestS3Credentials:
    def test_dev_allows_empty_keys(self, clean_env, manager):
        creds = manager.get_s3_credentials()
        assert creds["access_key_id"] == ""
        assert creds["secret_access_key"] == ""

    def test_production_missing_raises(self, production, manager):
        with pytest.raises(RuntimeError) as exc_info:
            manager.get_s3_credentials()
        message = str(exc_info.value)
        assert "OBJECT_STORAGE_ACCESS_KEY_ID" in message
        assert "OBJECT_STORAGE_SECRET_ACCESS_KEY" in message

    def test_production_explicit_values_pass_through(self, production, manager):
        production.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "SYNTHETICKEY")
        production.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "synthetic-secret")  # pragma: allowlist secret
        creds = manager.get_s3_credentials()
        assert creds["access_key_id"] == "SYNTHETICKEY"


class TestValidateProductionSecrets:
    def test_dev_is_no_op(self, clean_env):
        clean_env.setenv("REGENGINE_ENV", "development")
        validate_production_secrets()

    def test_production_database_url_only_passes(self, production):
        """#3243: disabled/absent optional subsystems must not block boot."""
        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        validate_production_secrets()

    def test_production_all_set_passes(self, production):
        for var, value in _SECURE_CREDS.items():
            production.setenv(var, value)
        validate_production_secrets()

    def test_production_missing_database_url_fails(self, production):
        with pytest.raises(RuntimeError) as exc_info:
            validate_production_secrets()
        message = str(exc_info.value)
        assert "DATABASE_URL is not set" in message
        for var in (
            "POSTGRES_HOST",
            "POSTGRES_PASSWORD",
            "NEO4J_PASSWORD",
            "KAFKA_BOOTSTRAP_SERVERS",
            "OBJECT_STORAGE_ACCESS_KEY_ID",
            "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        ):
            assert f"{var} is not set" not in message
        assert "NEO4J_URI / NEO4J_URL is not set" not in message

    def test_unapproved_graph_request_is_owned_by_router_policy(self, production):
        from server.router_policy import PRODUCTION_ENABLED_ROUTERS, RouterPolicy

        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        production.setenv("ENABLED_ROUTERS", ",".join(sorted(PRODUCTION_ENABLED_ROUTERS | {"graph"})))
        # A requested but unapproved router must not invent a credential
        # requirement. The existing router policy rejects this configuration.
        validate_production_secrets()
        with pytest.raises(RuntimeError, match="release-approved set"):
            RouterPolicy.from_environment(production=True)

    def test_production_kafka_enabled_without_config_rejected(self, production):
        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        production.setenv("EVENT_BACKBONE", "kafka")
        with pytest.raises(RuntimeError) as exc_info:
            validate_production_secrets()
        message = str(exc_info.value)
        assert "KAFKA_BOOTSTRAP_SERVERS is not set" in message
        assert "DATABASE_URL is not set" not in message
        assert "NEO4J_PASSWORD is not set" not in message
        assert "OBJECT_STORAGE_ACCESS_KEY_ID is not set" not in message

    def test_production_kafka_enabled_with_config_passes(self, production):
        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        production.setenv("EVENT_BACKBONE", "kafka")
        production.setenv("KAFKA_BOOTSTRAP_SERVERS", "synthetic-kafka:9092")
        validate_production_secrets()

    def test_production_detected_via_env_fallback(self, clean_env):
        """Central detection: ENV=production counts when REGENGINE_ENV is unset."""
        clean_env.setenv("ENV", "production")
        with pytest.raises(RuntimeError):
            validate_production_secrets()

    def test_production_detected_via_database_url_heuristic(self, clean_env):
        """Central detection: the Supabase pooler heuristic counts as production.

        DATABASE_URL itself satisfies the always-required slot, so Kafka
        is enabled to prove the heuristic flips the gate on.
        """
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@db.pooler.supabase.com:6543/d")
        clean_env.setenv("EVENT_BACKBONE", "kafka")
        with pytest.raises(RuntimeError) as exc_info:
            validate_production_secrets()
        assert "KAFKA_BOOTSTRAP_SERVERS is not set" in str(exc_info.value)

    def test_each_required_credential_is_checked(self, production):
        """Every required credential is individually load-bearing."""
        for var, value in _SECURE_CREDS.items():
            production.setenv(var, value)
        for alternatives in REQUIRED_PRODUCTION_CREDENTIALS:
            for var in alternatives:
                production.delenv(var, raising=False)
            with pytest.raises(RuntimeError):
                validate_production_secrets()
            for var in alternatives:
                if var in _SECURE_CREDS:
                    production.setenv(var, _SECURE_CREDS[var])
        validate_production_secrets()

    def test_insecure_default_still_rejected(self, production):
        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        production.setenv("NEO4J_PASSWORD", "neo4j")
        with pytest.raises(RuntimeError) as exc_info:
            validate_production_secrets()
        assert "NEO4J_PASSWORD is using an insecure default value" in str(exc_info.value)

    def test_insecure_storage_placeholder_rejected_when_set(self, production):
        """Storage is never startup-required, but a set placeholder still fails."""
        production.setenv("DATABASE_URL", _SECURE_CREDS["DATABASE_URL"])
        production.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "test")
        with pytest.raises(RuntimeError) as exc_info:
            validate_production_secrets()
        assert "OBJECT_STORAGE_ACCESS_KEY_ID is using an insecure default value" in str(exc_info.value)


class TestStartupWiring:
    def test_server_main_fails_closed_on_secrets(self):
        source = SERVER_MAIN.read_text(encoding="utf-8")
        assert "from shared.secrets_manager import" in source
        assert re.search(r"^require_secure_secrets_in_production\(\)", source, re.MULTILINE)
        assert re.search(r"^validate_production_secrets\(\)", source, re.MULTILINE)
