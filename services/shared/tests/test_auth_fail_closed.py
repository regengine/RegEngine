"""Tests for auth config validation at service startup."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVICES_DIR = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = (
    "import os, sys; "
    f"sys.path.insert(0, {str(SERVICES_DIR)!r}); "
    "from shared.auth import validate_auth_config; "
    "validate_auth_config(); "
    "print('STARTED_OK')"
)


def _run_validate(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Run validate_auth_config() in a subprocess with the given env vars."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_ENVIRONMENT_NAME",
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_NAME",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_NAME",
            "RAILWAY_SERVICE_ID",
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
        result = _run_validate(
            {
                "RAILWAY_ENVIRONMENT": "production",
                "AUTH_SECRET_KEY": "a-valid-secret-key-long-enough",
            }
        )
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_rejects_short_jwt_secret_in_production(self):
        """Production with a too-short JWT secret logs the issue.

        Startup only hard-fails outside CI when REGENGINE_ENV is explicitly
        production. The shared CI shard runs with CI/GITHUB_ACTIONS set, so we
        assert the validation signal rather than a subprocess exit.
        """
        result = _run_validate(
            {
                "CI": "true",
                "GITHUB_ACTIONS": "true",
                "REGENGINE_ENV": "production",
                "AUTH_SECRET_KEY": "short",
            }
        )
        assert result.returncode == 0
        assert "auth_config_validation_failed" in result.stdout
        assert "AUTH_SECRET_KEY is too short" in result.stdout
        assert "STARTED_OK" in result.stdout

    def test_rejects_default_jwt_secret_in_production(self):
        """Production with a known-default JWT secret logs the issue."""
        result = _run_validate(
            {
                "CI": "true",
                "GITHUB_ACTIONS": "true",
                "REGENGINE_ENV": "production",
                "AUTH_SECRET_KEY": "changeme",
            }
        )
        assert result.returncode == 0
        assert "auth_config_validation_failed" in result.stdout
        assert "AUTH_SECRET_KEY is too short" in result.stdout
        assert "STARTED_OK" in result.stdout

    def test_rejects_bypass_token_in_production(self):
        """Production with AUTH_TEST_BYPASS_TOKEN logs the issue."""
        result = _run_validate(
            {
                "CI": "true",
                "GITHUB_ACTIONS": "true",
                "REGENGINE_ENV": "production",
                "AUTH_SECRET_KEY": "a-valid-secret-key-long-enough",
                "AUTH_TEST_BYPASS_TOKEN": "some-bypass-token",
            }
        )
        assert result.returncode == 0
        assert "auth_config_validation_failed" in result.stdout
        assert "AUTH_TEST_BYPASS_TOKEN is set in production" in result.stdout
        assert "STARTED_OK" in result.stdout

    # ── #2512: cloud-marker + ephemeral-secret fail-fast ─────────────────────

    def test_cloud_marker_non_production_env_with_ephemeral_secret_hard_fails(self):
        """Defense-in-depth: a cloud marker present with an explicit
        non-production environment the central gate leaves alone (staging on a
        non-Railway host) AND an ephemeral signing key active (no AUTH_SECRET_KEY
        / TOOL_ACCESS_SECRET) must refuse to boot rather than serve
        restart-forgeable sessions (#2512). Outside CI.

        Note REGENGINE_ENV=development would be *forced* to production by the
        central gate (and thus start cleanly); staging is the genuine bypass
        case the gate intentionally does not force."""
        result = _run_validate(
            {
                "CI": "",
                "GITHUB_ACTIONS": "",
                "RENDER": "1",
                "REGENGINE_ENV": "staging",
            }
        )
        assert result.returncode != 0
        assert "ephemeral signing key is active" in result.stderr
        assert "STARTED_OK" not in result.stdout

    def test_cloud_marker_development_env_is_forced_production_and_starts(self):
        """A cloud marker with REGENGINE_ENV=development is forced to production
        by the central gate, so the ephemeral-secret branch is skipped and
        startup proceeds — proving the fail-fast aligns with the gate (#2512)."""
        result = _run_validate(
            {
                "CI": "",
                "GITHUB_ACTIONS": "",
                "RENDER": "1",
                "REGENGINE_ENV": "development",
            }
        )
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_marker_with_explicit_secrets_starts(self):
        """The same bypass-shaped config is fine once real secrets are provided —
        only the ephemeral-key case fails (#2512)."""
        result = _run_validate(
            {
                "CI": "",
                "GITHUB_ACTIONS": "",
                "RENDER": "1",
                "REGENGINE_ENV": "staging",
                "AUTH_SECRET_KEY": "a-valid-secret-key-long-enough",
                "TOOL_ACCESS_SECRET": "another-valid-secret-key-long-enough",
            }
        )
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_no_cloud_marker_ephemeral_secret_still_starts(self):
        """Truly-local dev (no cloud marker) with no secrets keeps starting —
        the fail-fast must not regress local development (#2512)."""
        result = _run_validate(
            {
                "CI": "",
                "GITHUB_ACTIONS": "",
                "REGENGINE_ENV": "development",
                # Clear any cloud markers the CI host itself might inject so the
                # "truly local" assertion is honest.
                "RENDER": "",
                "FLY_APP_NAME": "",
                "KUBERNETES_SERVICE_HOST": "",
            }
        )
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout
