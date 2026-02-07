"""
SEC-004: Tests for secret validation script.
Tests the check_required_secrets.sh behavior.
"""

import subprocess
import os
import pytest
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "check_required_secrets.sh"


class TestSecretValidationScript:
    """Test the secret validation script behavior."""

    def test_script_exists_and_is_executable(self):
        """Script file should exist and be executable."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"
        assert os.access(SCRIPT_PATH, os.X_OK), "Script is not executable"

    def test_fails_with_no_secrets_in_production(self):
        """Script should fail when required secrets are missing in production."""
        env = os.environ.copy()
        env["REGENGINE_ENV"] = "production"
        env.pop("NEO4J_PASSWORD", None)
        env.pop("ADMIN_MASTER_KEY", None)
        env.pop("REGENGINE_SKIP_SECRET_CHECK", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Should fail in production without secrets. Output: {result.stdout}"
        assert "ERROR" in result.stdout or "error" in result.stdout.lower()

    def test_warns_but_continues_in_development_without_secrets(self):
        """Script should warn but continue in development mode without secrets."""
        env = os.environ.copy()
        env["REGENGINE_ENV"] = "development"
        env.pop("NEO4J_PASSWORD", None)
        env.pop("ADMIN_MASTER_KEY", None)
        env.pop("REGENGINE_SKIP_SECRET_CHECK", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            env=env,
            capture_output=True,
            text=True,
        )

        # Development mode should exit 0 even with warnings
        assert result.returncode == 0, f"Should continue in development. Output: {result.stdout}"

    def test_passes_with_valid_secrets(self):
        """Script should pass when all required secrets are set properly."""
        env = os.environ.copy()
        env["REGENGINE_ENV"] = "production"
        env["NEO4J_PASSWORD"] = "my-super-secure-neo4j-pwd-123"
        env["ADMIN_MASTER_KEY"] = "my-super-secure-admin-key-456"
        env["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
        env["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        env.pop("REGENGINE_SKIP_SECRET_CHECK", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Should pass with valid secrets. Output: {result.stdout}"
        assert "passed" in result.stdout.lower() or "✓" in result.stdout

    def test_fails_with_default_password_patterns(self):
        """Script should reject passwords matching insecure patterns."""
        # Only exact matches of insecure values should be rejected
        insecure_values = [
            "change-me-in-production",
            "password",
            "secret",
            "test",
            "demo",
            "default",
            "neo4j",  # default neo4j password
        ]

        for insecure_value in insecure_values:
            env = os.environ.copy()
            env["REGENGINE_ENV"] = "production"
            env["NEO4J_PASSWORD"] = insecure_value
            env["ADMIN_MASTER_KEY"] = "valid-admin-key-here-secure"
            env["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
            env["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            env.pop("REGENGINE_SKIP_SECRET_CHECK", None)

            result = subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                env=env,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1, f"Should reject insecure value '{insecure_value}'. Output: {result.stdout}"

    def test_skip_check_bypasses_validation(self):
        """REGENGINE_SKIP_SECRET_CHECK=true should bypass all checks."""
        env = os.environ.copy()
        env["REGENGINE_ENV"] = "production"
        env["REGENGINE_SKIP_SECRET_CHECK"] = "true"
        env.pop("NEO4J_PASSWORD", None)
        env.pop("ADMIN_MASTER_KEY", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Should bypass with skip flag. Output: {result.stdout}"
        assert "bypassed" in result.stdout.lower() or "skip" in result.stdout.lower()

    def test_detects_test_aws_credentials_in_production(self):
        """Should reject 'test' AWS credentials in production."""
        env = os.environ.copy()
        env["REGENGINE_ENV"] = "production"
        env["NEO4J_PASSWORD"] = "valid-password-here"
        env["ADMIN_MASTER_KEY"] = "valid-admin-key-here"
        env["AWS_ACCESS_KEY_ID"] = "test"
        env["AWS_SECRET_ACCESS_KEY"] = "test"
        env.pop("REGENGINE_SKIP_SECRET_CHECK", None)

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Should reject 'test' AWS creds in production. Output: {result.stdout}"


class TestDockerComposeSecrets:
    """Test docker-compose.yml secret requirements."""

    def test_docker_compose_requires_secrets(self):
        """docker-compose.yml should use required variable syntax."""
        compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
        content = compose_path.read_text()

        # Check for required variable syntax (${VAR:?message})
        assert "NEO4J_PASSWORD:?" in content, "NEO4J_PASSWORD should be required"
        assert "ADMIN_MASTER_KEY:?" in content, "ADMIN_MASTER_KEY should be required"
        assert "AWS_ACCESS_KEY_ID:?" in content, "AWS_ACCESS_KEY_ID should be required"
        assert "AWS_SECRET_ACCESS_KEY:?" in content, "AWS_SECRET_ACCESS_KEY should be required"

    def test_no_insecure_defaults_in_compose(self):
        """docker-compose.yml should not contain insecure default patterns."""
        compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
        content = compose_path.read_text()

        insecure_patterns = [
            ":-change-me",
            ":-password",
            ":-secret",
            ":-test",
            ":-demo",
            ":-default",
            ":-dev-admin-key",
        ]

        for pattern in insecure_patterns:
            assert pattern not in content, f"Insecure default pattern found: {pattern}"

    def test_env_example_has_no_real_secrets(self):
        """The .env.example file should not contain real secret values."""
        env_example_path = Path(__file__).parent.parent.parent / ".env.example"
        content = env_example_path.read_text()

        # Check that required fields are empty or have placeholder text
        lines = content.split("\n")
        for line in lines:
            if line.startswith("NEO4J_PASSWORD="):
                value = line.split("=", 1)[1].strip()
                assert value == "" or "your-" in value.lower() or value.startswith("#"), \
                    f"NEO4J_PASSWORD should be empty in example: {line}"
            if line.startswith("ADMIN_MASTER_KEY="):
                value = line.split("=", 1)[1].strip()
                assert value == "" or "your-" in value.lower() or value.startswith("#"), \
                    f"ADMIN_MASTER_KEY should be empty in example: {line}"


class TestDevComposeOverride:
    """Test docker-compose.dev.yml provides development defaults."""

    def test_dev_compose_exists(self):
        """Development compose override should exist."""
        dev_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
        assert dev_compose_path.exists(), "docker-compose.dev.yml should exist"

    def test_dev_compose_has_dev_credentials(self):
        """Development compose should provide non-production credentials."""
        dev_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
        content = dev_compose_path.read_text()

        # Should contain development-specific values
        assert "dev-" in content or "not-for-prod" in content, \
            "Dev compose should have clearly labeled dev credentials"
        assert "REGENGINE_SKIP_SECRET_CHECK" in content, \
            "Dev compose should skip secret checks"
