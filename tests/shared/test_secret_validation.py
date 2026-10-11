"""
SEC-004: Tests for current environment validation.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SPEC = importlib.util.spec_from_file_location(
    "_tests_validate_env",
    ROOT / "scripts" / "validate_env.py",
)
assert SPEC and SPEC.loader
validate_env_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_env_module
SPEC.loader.exec_module(validate_env_module)
validate_env = validate_env_module.validate_env


def base_env(**overrides):
    env = {
        "REGENGINE_ENV": "production",
        "AUTH_SECRET_KEY": "auth-secret-with-enough-entropy",  # pragma: allowlist secret
        "POSTGRES_PASSWORD": "postgres-password-with-enough-entropy",  # pragma: allowlist secret
        "DATABASE_URL": "postgresql://regengine:password@localhost:5432/regengine",  # pragma: allowlist secret
        "AUTH_TEST_BYPASS_TOKEN": "",
        "SCHEDULER_API_KEY": "scheduler-key-with-enough-entropy",  # pragma: allowlist secret
        "OBJECT_STORAGE_ACCESS_KEY_ID": "prod-access-key",  # pragma: allowlist secret
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "prod-secret-key-with-enough-entropy",  # pragma: allowlist secret
        "TOOL_ACCESS_SECRET": "tool-access-secret-with-enough-entropy",  # pragma: allowlist secret
        "AUTH_OTP_HMAC_SECRET": "auth-otp-hmac-secret-with-enough-entropy",  # pragma: allowlist secret
        "RESEND_API_KEY": "resend-api-key-with-enough-entropy",  # pragma: allowlist secret
        "STRIPE_WEBHOOK_SECRET": "stripe-webhook-secret-with-enough-entropy",  # pragma: allowlist secret
        "AUDIT_PII_HASH_SALT": "audit-pii-salt-with-enough-entropy",  # pragma: allowlist secret
        "WEBAUTHN_EXPECTED_ORIGIN": "https://app.example.com",
    }
    env.update(overrides)
    return env


class TestEnvValidation:
    def test_fails_with_missing_production_secrets(self):
        result = validate_env(env={"REGENGINE_ENV": "production"})

        assert not result.ok
        assert any("AUTH_SECRET_KEY" in error for error in result.errors)
        assert any("OBJECT_STORAGE_SECRET_ACCESS_KEY" in error for error in result.errors)

    def test_passes_with_valid_production_secrets(self):
        result = validate_env(env=base_env())

        assert result.ok

    def test_production_requires_audit_pii_salt(self):
        env = base_env()
        del env["AUDIT_PII_HASH_SALT"]
        result = validate_env(env=env)

        assert not result.ok
        assert any("AUDIT_PII_HASH_SALT" in error for error in result.errors)

    def test_production_requires_webauthn_expected_origin(self):
        env = base_env()
        del env["WEBAUTHN_EXPECTED_ORIGIN"]
        result = validate_env(env=env)

        assert not result.ok
        assert any("WEBAUTHN_EXPECTED_ORIGIN" in error for error in result.errors)

    def test_staging_requires_audit_pii_salt(self):
        env = base_env(REGENGINE_ENV="staging")
        del env["AUDIT_PII_HASH_SALT"]
        result = validate_env(env=env)

        assert not result.ok
        assert any("AUDIT_PII_HASH_SALT" in error for error in result.errors)

    def test_staging_passes_with_salt_set(self):
        result = validate_env(env=base_env(REGENGINE_ENV="staging"))

        assert result.ok

    def test_rejects_weak_values_in_production(self):
        for insecure_value in [
            "change-me-in-production",
            "password",
            "secret",
            "test",
            "demo",
            "default",
            "neo4j",
        ]:
            result = validate_env(env=base_env(POSTGRES_PASSWORD=insecure_value))
            assert not result.ok, f"Should reject insecure value {insecure_value!r}"

    def test_rejects_test_object_storage_credentials_in_production(self):
        result = validate_env(
            env=base_env(
                OBJECT_STORAGE_ACCESS_KEY_ID="test",
                OBJECT_STORAGE_SECRET_ACCESS_KEY="test",
            )
        )

        assert not result.ok
        assert any("OBJECT_STORAGE" in error for error in result.errors)

    def test_warns_for_weak_values_in_development(self):
        result = validate_env(
            env=base_env(
                REGENGINE_ENV="development",
                POSTGRES_PASSWORD="password",  # pragma: allowlist secret
                SCHEDULER_API_KEY="",
                OBJECT_STORAGE_ACCESS_KEY_ID="",
                OBJECT_STORAGE_SECRET_ACCESS_KEY="",
            )
        )

        assert result.ok
        assert result.warnings

    def test_weak_value_messages_never_echo_the_credential(self):
        weak_value = "change-me-in-production"
        dev_result = validate_env(env=base_env(REGENGINE_ENV="development", POSTGRES_PASSWORD=weak_value))
        assert dev_result.ok
        assert dev_result.warnings
        assert any("POSTGRES_PASSWORD" in w for w in dev_result.warnings)
        assert all(weak_value not in w for w in dev_result.warnings)

        prod_result = validate_env(env=base_env(POSTGRES_PASSWORD=weak_value))
        assert not prod_result.ok
        assert any("POSTGRES_PASSWORD" in e for e in prod_result.errors)
        assert all(weak_value not in e for e in prod_result.errors)


class TestDevCompose:
    def test_dev_compose_exists(self):
        dev_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
        assert dev_compose_path.exists(), "docker-compose.dev.yml should exist"

    def test_dev_compose_is_postgres_only(self):
        content = (Path(__file__).parent.parent.parent / "docker-compose.dev.yml").read_text()

        assert "postgres:" in content
        assert "redpanda" not in content.lower()
        assert "neo4j" not in content.lower()
