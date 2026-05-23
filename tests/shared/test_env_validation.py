"""Tests for shared.env_validation helpers.

Covers ``assert_legacy_entrypoint_not_in_production``, the Phase 4
guard added to every per-service ``services/<svc>/main.py`` so a stray
production deploy of a legacy entrypoint fails fast instead of
silently serving from a partial router surface.
"""

from __future__ import annotations

import pytest

from shared.env_validation import assert_legacy_entrypoint_not_in_production


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip any env vars the guard inspects so each test starts pristine."""
    for var in (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_ENVIRONMENT",
        "REGENGINE_ENV",
        "ALLOW_LEGACY_ENTRYPOINT_IN_PROD",
    ):
        monkeypatch.delenv(var, raising=False)


def test_passes_when_no_production_signal():
    # All env vars unset — local dev or pytest. Must NOT raise.
    assert_legacy_entrypoint_not_in_production("ingestion") is None


def test_passes_when_env_signals_non_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("REGENGINE_ENV", "development")
    assert_legacy_entrypoint_not_in_production("admin") is None


@pytest.mark.parametrize(
    "env_var",
    ["RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "REGENGINE_ENV"],
)
def test_raises_when_any_prod_signal_present(monkeypatch, env_var):
    monkeypatch.setenv(env_var, "production")
    with pytest.raises(RuntimeError, match="legacy entrypoint"):
        assert_legacy_entrypoint_not_in_production("graph")


def test_message_names_the_service_for_operator_triage(monkeypatch):
    """The operator who hits this in prod needs to know WHICH legacy
    entry tripped — naming the service in the error is load-bearing."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(RuntimeError) as exc_info:
        assert_legacy_entrypoint_not_in_production("scheduler")
    assert "services/scheduler/main.py" in str(exc_info.value)
    assert "server.main:app" in str(exc_info.value)


@pytest.mark.parametrize("opt_out_value", ["1", "true", "TRUE", "yes", "on"])
def test_opt_out_env_bypasses_guard_in_prod(monkeypatch, opt_out_value):
    """ALLOW_LEGACY_ENTRYPOINT_IN_PROD lets operators run a legacy
    entrypoint deliberately (e.g. one-shot recovery / surgery)."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("ALLOW_LEGACY_ENTRYPOINT_IN_PROD", opt_out_value)
    assert assert_legacy_entrypoint_not_in_production("nlp") is None


def test_opt_out_falsy_values_do_not_bypass(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    # Falsy / unrecognized values must still trip the guard.
    for value in ("0", "false", "", "no", "off"):
        monkeypatch.setenv("ALLOW_LEGACY_ENTRYPOINT_IN_PROD", value)
        with pytest.raises(RuntimeError):
            assert_legacy_entrypoint_not_in_production("compliance")


def test_case_insensitive_production_match(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "PRODUCTION")
    with pytest.raises(RuntimeError):
        assert_legacy_entrypoint_not_in_production("ingestion")


def test_whitespace_in_production_value(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "  production  ")
    with pytest.raises(RuntimeError):
        assert_legacy_entrypoint_not_in_production("ingestion")
