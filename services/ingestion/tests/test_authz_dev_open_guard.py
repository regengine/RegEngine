"""Deploy-time guard for the ingestion dev-open auth fallback.

The dev-open fallback in ``app.authz.get_ingestion_principal`` activates on
the environment name alone (``REGENGINE_ENV`` of ``development``/``test``).
These tests lock two properties:

- Production-like environment names never satisfy the dev gate.
- A development/test name combined with a strict-auth signal (a cloud
  platform marker or ``REGENGINE_AUTH_STRICT=1``) requires an API key and
  fails the deploy-time assertion instead of opening the fallback.
"""

from __future__ import annotations

import pytest
from app import authz
from app.authz import (
    IngestionPrincipal,
    _is_dev_env,
    assert_dev_open_disabled_in_production,
    get_ingestion_principal,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from shared.env import CLOUD_ENV_VARS


@pytest.fixture(autouse=True)
def _reset_auth_limiter(monkeypatch):
    """Give every test a fresh auth-failure limiter (no Redis)."""
    from shared.rate_limit import BruteForceLimiter

    limiter = BruteForceLimiter(
        namespace="test-authz-dev-open-guard",
        max_failures=authz._AUTH_FAIL_MAX,
        window_seconds=authz._AUTH_FAIL_WINDOW,
        redis_client=None,
    )
    limiter._redis = None
    monkeypatch.setattr(authz, "_auth_limiter", limiter)
    yield


@pytest.fixture
def _clean_env(monkeypatch):
    """Clear every variable that drives the dev-open decision."""
    for var in (
        "REGENGINE_ENV",
        "ENV",
        "DATABASE_URL",
        "REGENGINE_AUTH_STRICT",
        *CLOUD_ENV_VARS,
    ):
        monkeypatch.delenv(var, raising=False)


def _build_app():
    app = FastAPI()

    @app.get("/whoami")
    async def _whoami(principal: IngestionPrincipal = Depends(get_ingestion_principal)):
        return {
            "key_id": principal.key_id,
            "scopes": principal.scopes,
            "tenant_id": principal.tenant_id,
            "auth_mode": principal.auth_mode,
        }

    return app


@pytest.mark.parametrize(
    "env_name",
    ["production", "PRODUCTION", "prod", "staging", "preview", "", "live", "  prod  "],
)
def test_production_like_names_never_enable_dev_open(_clean_env, monkeypatch, env_name):
    monkeypatch.setenv("REGENGINE_ENV", env_name)
    assert _is_dev_env() is False
    assert_dev_open_disabled_in_production() is None


def test_local_dev_name_still_allows_dev_open(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "development")
    assert_dev_open_disabled_in_production() is None
    response = TestClient(_build_app()).get("/whoami")
    assert response.status_code == 200
    assert response.json()["auth_mode"] == "dev_open"


def test_dev_name_with_cloud_marker_requires_api_key(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-env-id")
    response = TestClient(_build_app()).get("/whoami")
    assert response.status_code == 401


def test_dev_name_with_strict_flag_requires_api_key(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("REGENGINE_AUTH_STRICT", "1")
    response = TestClient(_build_app()).get("/whoami")
    assert response.status_code == 401


def test_assertion_raises_for_dev_name_on_cloud(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-env-id")
    with pytest.raises(RuntimeError):
        assert_dev_open_disabled_in_production()


def test_assertion_raises_for_dev_name_with_strict_flag(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("REGENGINE_AUTH_STRICT", "true")
    with pytest.raises(RuntimeError):
        assert_dev_open_disabled_in_production()


def test_assertion_passes_for_production(_clean_env, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-env-id")
    assert_dev_open_disabled_in_production() is None
