"""Tests for production safety locks around local E2E affordances."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from services.admin.app.e2e_safety import CriticalSecurityError, e2e_mode_enabled


def _load_passwordless_seed_script():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_passwordless_e2e_user.py"
    spec = importlib.util.spec_from_file_location("seed_passwordless_e2e_user", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2e_mode_fatally_rejected_in_production(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(CriticalSecurityError, match="E2E mode is strictly forbidden in production"):
        e2e_mode_enabled()


def test_passwordless_seed_script_fatally_rejects_e2e_mode_in_production(monkeypatch):
    seed_passwordless_e2e_user = _load_passwordless_seed_script()

    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(CriticalSecurityError, match="E2E mode is strictly forbidden in production"):
        seed_passwordless_e2e_user._require_e2e_mode()


def test_passwordless_seed_assurance_override_is_narrowly_allowlisted(monkeypatch):
    seed_passwordless_e2e_user = _load_passwordless_seed_script()

    monkeypatch.delenv("REGENGINE_E2E_SESSION_AUTH_METHOD", raising=False)
    assert seed_passwordless_e2e_user._session_auth_method() is None

    monkeypatch.setenv("REGENGINE_E2E_SESSION_AUTH_METHOD", "sso")
    assert seed_passwordless_e2e_user._session_auth_method() == "sso"

    monkeypatch.setenv("REGENGINE_E2E_SESSION_AUTH_METHOD", "password")
    with pytest.raises(SystemExit, match="must be email_otp, webauthn, or sso"):
        seed_passwordless_e2e_user._session_auth_method()


def test_e2e_mode_allowed_in_test_environment(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert e2e_mode_enabled() is True
