"""Tests for production safety locks around local E2E affordances."""

from __future__ import annotations

import pytest
import importlib.util
from pathlib import Path

from services.admin.app.e2e_safety import CriticalSecurityError, e2e_mode_enabled


def test_e2e_mode_fatally_rejected_in_production(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(CriticalSecurityError, match="E2E mode is strictly forbidden in production"):
        e2e_mode_enabled()


def test_passwordless_seed_script_fatally_rejects_e2e_mode_in_production(monkeypatch):
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_passwordless_e2e_user.py"
    spec = importlib.util.spec_from_file_location("seed_passwordless_e2e_user", script_path)
    assert spec and spec.loader
    seed_passwordless_e2e_user = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed_passwordless_e2e_user)

    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(CriticalSecurityError, match="E2E mode is strictly forbidden in production"):
        seed_passwordless_e2e_user._require_e2e_mode()


def test_e2e_mode_allowed_in_test_environment(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert e2e_mode_enabled() is True
