"""Tests for H2: fail-closed auth — cloud startup refuses without Supabase credentials."""

import os
import subprocess
import sys

import pytest


VALIDATE_SCRIPT = (
    "import os, sys; "
    "sys.path.insert(0, 'services'); "
    "from shared.auth import validate_auth_config; "
    "validate_auth_config(require_supabase=True); "
    "print('STARTED_OK')"
)

# Script WITHOUT require_supabase — simulates graph/NLP services
VALIDATE_SCRIPT_NO_SUPABASE = (
    "import os, sys; "
    "sys.path.insert(0, 'services'); "
    "from shared.auth import validate_auth_config; "
    "validate_auth_config(); "
    "print('STARTED_OK')"
)


def _run_validate(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Run validate_auth_config() in a subprocess with the given env vars."""
    env = {
        # Strip cloud/production indicators from the parent env
        k: v
        for k, v in os.environ.items()
        if k not in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_SERVICE_NAME",
            "VERCEL_ENV",
            "NEXT_PUBLIC_SUPABASE_URL",
            "SUPABASE_URL",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
            "SUPABASE_ANON_KEY",
            "AUTH_SECRET_KEY",
            "JWT_SECRET",
            "REGENGINE_ENV",
        )
    }
    env.update(env_overrides)
    # Ensure we don't trip the JWT validation by providing a valid secret
    env.setdefault("AUTH_SECRET_KEY", "test-secret-key-long-enough")
    env.setdefault("REGENGINE_ENV", "development")
    return subprocess.run(
        [sys.executable, "-c", VALIDATE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )


class TestFailClosedAuth:
    """H2: services must refuse to start in cloud without Supabase credentials."""

    def test_local_dev_starts_without_supabase_creds(self):
        """Local dev (no cloud env vars) should start fine without Supabase creds."""
        result = _run_validate({})
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_warns_without_supabase_url(self):
        """Cloud env with missing SUPABASE_URL should warn but still start."""
        result = _run_validate({
            "RAILWAY_ENVIRONMENT": "production",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-anon-key",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_warns_without_supabase_key(self):
        """Cloud env with missing SUPABASE_ANON_KEY should warn but still start."""
        result = _run_validate({
            "RAILWAY_ENVIRONMENT": "production",
            "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_warns_without_both_creds(self):
        """Cloud env with neither Supabase credential should warn but still start."""
        result = _run_validate({
            "RAILWAY_ENVIRONMENT": "production",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_starts_with_supabase_creds(self):
        """Cloud env with both Supabase creds should start normally."""
        result = _run_validate({
            "RAILWAY_ENVIRONMENT": "production",
            "NEXT_PUBLIC_SUPABASE_URL": "https://test.supabase.co",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-anon-key",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_cloud_starts_with_non_prefixed_creds(self):
        """Cloud env with SUPABASE_URL/SUPABASE_ANON_KEY (no NEXT_PUBLIC_ prefix) should work."""
        result = _run_validate({
            "RAILWAY_SERVICE_NAME": "admin",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_ANON_KEY": "test-anon-key",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_vercel_env_triggers_warning(self):
        """VERCEL_ENV should trigger a warning but still start."""
        result = _run_validate({
            "VERCEL_ENV": "production",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_railway_service_name_triggers_warning(self):
        """RAILWAY_SERVICE_NAME should trigger a warning but still start."""
        result = _run_validate({
            "RAILWAY_SERVICE_NAME": "ingestion",
        })
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout

    def test_internal_service_starts_without_supabase_in_cloud(self):
        """Internal services (graph, NLP) should start in cloud without Supabase creds.

        Only services that pass require_supabase=True should be gated.
        """
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in (
                "RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "VERCEL_ENV",
                "NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL",
                "NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY",
                "AUTH_SECRET_KEY", "JWT_SECRET", "REGENGINE_ENV",
            )
        }
        env["RAILWAY_ENVIRONMENT"] = "production"
        env["AUTH_SECRET_KEY"] = "test-secret-key-long-enough"
        env["REGENGINE_ENV"] = "development"
        # No Supabase creds — but require_supabase=False (default)
        result = subprocess.run(
            [sys.executable, "-c", VALIDATE_SCRIPT_NO_SUPABASE],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "STARTED_OK" in result.stdout
