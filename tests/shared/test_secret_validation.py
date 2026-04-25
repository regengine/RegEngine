"""
SEC-004: Tests for current environment validation.
"""

from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).parent.parent.parent
SPEC = importlib.util.spec_from_file_location("validate_env", ROOT / "scripts" / "validate_env.py")
assert SPEC and SPEC.loader
validate_env_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_env_module
SPEC.loader.exec_module(validate_env_module)
validate_env = validate_env_module.validate_env


def base_env(**overrides):
    env = {
        "REGENGINE_ENV": "production",
        "AUTH_SECRET_KEY": "auth-secret-with-enough-entropy",
        "ADMIN_MASTER_KEY": "admin-master-key-with-enough-entropy",
        "POSTGRES_PASSWORD": "postgres-password-with-enough-entropy",
        "AUTH_TEST_BYPASS_TOKEN": "",
        "SCHEDULER_API_KEY": "scheduler-key-with-enough-entropy",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "prod-access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "prod-secret-key-with-enough-entropy",
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
                POSTGRES_PASSWORD="password",
                SCHEDULER_API_KEY="",
                OBJECT_STORAGE_ACCESS_KEY_ID="",
                OBJECT_STORAGE_SECRET_ACCESS_KEY="",
            )
        )

        assert result.ok
        assert result.warnings


class TestEnvExample:
    def test_env_example_has_no_real_secrets(self):
        env_example_path = Path(__file__).parent.parent.parent / ".env.example"
        content = env_example_path.read_text()

        for line in content.split("\n"):
            if line.startswith("ADMIN_MASTER_KEY="):
                value = line.split("=", 1)[1].strip()
                assert value == "" or "your-" in value.lower() or value.startswith("#"), \
                    f"ADMIN_MASTER_KEY should be empty in example: {line}"


class TestDevCompose:
    def test_dev_compose_exists(self):
        dev_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
        assert dev_compose_path.exists(), "docker-compose.dev.yml should exist"

    def test_dev_compose_is_postgres_only(self):
        content = (Path(__file__).parent.parent.parent / "docker-compose.dev.yml").read_text()

        assert "postgres:" in content
        assert "redpanda" not in content.lower()
        assert "neo4j" not in content.lower()
