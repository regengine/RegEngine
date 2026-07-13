"""Regression tests for shared cloud environment detection."""

from __future__ import annotations

import importlib
import os

import pytest

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
    # #2512: non-Railway/Vercel cloud markers must also force production.
    "RENDER",
    "FLY_APP_NAME",
    "KUBERNETES_SERVICE_HOST",
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


# ─── #2512: non-Railway/Vercel cloud markers force production ────────────────


@pytest.mark.parametrize("marker", ["RENDER", "FLY_APP_NAME", "KUBERNETES_SERVICE_HOST"])
def test_non_railway_cloud_marker_forces_production(monkeypatch, marker):
    """On Render/Fly/Kubernetes (no RAILWAY_*/VERCEL_*) with REGENGINE_ENV unset,
    the central gate must still force production — otherwise dev auth fallbacks
    (ephemeral JWT keys, in-memory sessions) silently activate on a deployed
    host (#2512)."""
    for key in _ENV_MARKERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(marker, "1")

    env = _reload_env_module()

    assert os.environ["REGENGINE_ENV"] == "production"
    assert env.is_production() is True


def test_shared_marker_constant_is_single_source_of_truth():
    """database.py and invite_routes.py must reference the same CLOUD_ENV_VARS
    tuple from shared.env — no divergent copies that can drift (#2512).

    Asserted at the source level (not by importing the admin DB module, which
    initializes a real engine at import time) so the check stays a fast unit
    test: the two modules must import the shared constant and must NOT carry a
    private hard-coded ``"RENDER"`` literal list of their own.
    """
    import shared.env as env

    # The broadened markers live in the shared constant.
    for marker in ("RENDER", "FLY_APP_NAME", "KUBERNETES_SERVICE_HOST"):
        assert marker in env.CLOUD_ENV_VARS

    # env.__file__ -> services/shared/env.py; two dirnames up -> services/.
    services_dir = os.path.dirname(os.path.dirname(env.__file__))
    for rel in ("admin/app/database.py", "admin/app/invite_routes.py"):
        source = open(os.path.join(services_dir, rel), encoding="utf-8").read()
        assert "CLOUD_ENV_VARS" in source, f"{rel} must import the shared CLOUD_ENV_VARS"
        # No divergent local copy: the old hard-coded tuples listed "RENDER".
        assert '"RENDER"' not in source, f"{rel} still defines a divergent cloud-marker list"
