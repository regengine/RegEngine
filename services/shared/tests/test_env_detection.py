"""Regression tests for shared cloud environment detection."""

from __future__ import annotations

import importlib
import os

_ENV_MARKERS = (
    "DATABASE_URL",
    "ENV",
    "REGENGINE_ENV",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_PROJECT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_SERVICE_ID",
    "VERCEL_ENV",
    "VERCEL_URL",
)


def _reload_env_module():
    import shared.env as env

    return importlib.reload(env)


def test_railway_environment_name_forces_production_when_regengine_env_missing(
    monkeypatch,
):
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")

    env = _reload_env_module()

    assert os.environ["REGENGINE_ENV"] == "production"
    assert env.is_production() is True


def test_railway_service_id_forces_production_when_env_is_development(monkeypatch):
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "b5ba1aad-b19d-45a4-80e2-48f2b05f7730")

    env = _reload_env_module()

    assert os.environ["REGENGINE_ENV"] == "production"
    assert env.is_production() is True


def test_railway_production_environment_forces_production_when_env_is_staging(
    monkeypatch,
):
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")

    env = _reload_env_module()

    assert os.environ["REGENGINE_ENV"] == "production"
    assert env.is_production() is True


def test_railway_staging_environment_keeps_explicit_staging(monkeypatch):
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")

    env = _reload_env_module()

    assert os.environ["REGENGINE_ENV"] == "staging"
    assert env.is_production() is False


def test_no_cloud_markers_and_no_regengine_env_remains_non_production(monkeypatch):
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)

    env = _reload_env_module()

    assert "REGENGINE_ENV" not in os.environ
    assert env.is_production() is False
