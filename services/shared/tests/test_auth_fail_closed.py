"""Tests for auth config validation at service startup."""

import os
import subprocess
import sys

import pytest


VALIDATE_SCRIPT = (
    "import os, sys; "
    "sys.path.insert(0, 'services'); "
    "from shared.auth import validate_auth_config; "
    "validate_auth_config(); "
    "print('STARTED_OK')"
)


def _run_validate(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Run validate_auth_config() in a subprocess with the given env vars."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_SERVICE_NAME",
            "VERCEL_ENV",
            "AUTH_SECRET_KEY",
            "JWT_SECRET",
            "REGENGINE_ENV",
            "AUTH_TEST_BYPASS_TOKEN",
            "REGENGINE_API_KEY",
            "API_KEY",
        )
    }
    env.update(env_overrides)
    env.setdefault("REGENGINE_ENV", "development")
    return subprocess.run(
        [sys.executable, "-c", VALIDATE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )


class TestAuthConfigValidation:
    """Validate auth config catches misconfigurations at startup."""

    def test_starts_with_valid_config(self):
        """Valid JWT secret should start cleanly."""
        result = _run_validate({"AUTH_SECRET_KEY": "a-valid-secret-key-long-enough"})
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_starts_in_dev_without_jwt_secret(self):
        """Dev mode without JWT secret should start (warns but no crash)."""
        result = _run_validate({})
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_starts_without_supabase_creds(self):
        """Cloud env should start fine without Supabase — no longer checked.

        Supabase credential validation was removed after it caused production
        outages. SupabaseManager.get_client() handles missing creds gracefully.
        """
        result = _run_validate({
            "RAILWAY_ENVIRONMENT": "production",
            "AUTH_SECRET_KEY": "a-valid-secret-key-long-enough",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_rejects_short_jwt_secret_in_production(self):
        """Production with a too-short JWT secret should fail."""
        result = _run_validate({
            "REGENGINE_ENV": "production",
            "AUTH_SECRET_KEY": "short",
        })
        assert result.returncode != 0

    def test_rejects_default_jwt_secret_in_production(self):
        """Production with a known-default JWT secret should fail."""
        result = _run_validate({
            "REGENGINE_ENV": "production",
            "AUTH_SECRET_KEY": "changeme",
        })
        assert result.returncode != 0

    def test_rejects_bypass_token_in_production(self):
        """Production with AUTH_TEST_BYPASS_TOKEN should fail."""
        result = _run_validate({
            "REGENGINE_ENV": "production",
            "AUTH_SECRET_KEY": "a-valid-secret-key-long-enough",
            "AUTH_TEST_BYPASS_TOKEN": "some-bypass-token",
        })
        assert result.returncode != 0
