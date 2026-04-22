"""Regression for webhook_router_v2._verify_api_key gate.

Before this change the inline gate only consulted the ``API_KEY`` env
var. Railway prod sets ``REGENGINE_API_KEY`` instead, so the gate
``elif _is_production(): raise 401`` branch fired on every request
and 401'd valid per-tenant keys that the principal path was designed
to validate.

The gate now only requires (a) a header to be present and (b) at
least one credential env var to be configured in prod. It no longer
attempts to validate the key itself — that's the principal path's job.
"""
import os

import pytest
from fastapi import HTTPException

import app.webhook_router_v2 as wr


def _reset_settings_cache(monkeypatch):
    """Drop the lru_cache so `get_settings()` picks up the new env."""
    from app import config
    config.get_settings.cache_clear()


def test_header_required(monkeypatch):
    """No header → 401 regardless of env."""
    monkeypatch.setenv("REGENGINE_API_KEY", "secret")
    _reset_settings_cache(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        wr._verify_api_key(x_regengine_api_key=None)
    assert exc.value.status_code == 401


def test_header_present_passes_in_prod_with_regengine_api_key(monkeypatch):
    """REGENGINE_API_KEY set, header present → pass (principal validates later)."""
    monkeypatch.setenv("REGENGINE_API_KEY", "secret")
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("API_KEY", raising=False)
    _reset_settings_cache(monkeypatch)
    # No exception — principal path does the real validation.
    wr._verify_api_key(x_regengine_api_key="rge_any.anything")


def test_header_present_passes_in_prod_with_api_key(monkeypatch):
    """API_KEY (legacy env) also satisfies the configuration check."""
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    _reset_settings_cache(monkeypatch)
    wr._verify_api_key(x_regengine_api_key="rge_any.anything")


def test_prod_with_no_credential_configured_rejects(monkeypatch):
    """Neither env var set in prod → 401 (fail-closed on misconfig)."""
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")
    _reset_settings_cache(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        wr._verify_api_key(x_regengine_api_key="rge_any.anything")
    assert exc.value.status_code == 401


def test_dev_with_no_credential_configured_passes(monkeypatch):
    """Dev / test env with no credential → pass (loose mode)."""
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "development")
    # DATABASE_URL heuristic must not fire as "prod"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _reset_settings_cache(monkeypatch)
    wr._verify_api_key(x_regengine_api_key="rge_any.anything")
