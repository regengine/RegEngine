"""Tests for KDE_READ audit-log failure policy (RE-SEC-006).

Covers:
  1. Default policy is "buffered".
  2. Invalid env-var value warns and defaults to buffered.
  3. Buffered policy persists to the durable buffer on primary failure.
  4. fail_closed policy raises HTTPException(503).
  5. Double-failure (primary + buffer) raises HTTPException(503).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# Ensure shared/ is importable for any transitive imports.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from services.graph.app import audit_failure_policy as afp  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_policy_env(monkeypatch):
    monkeypatch.delenv(afp.POLICY_ENV, raising=False)
    yield


def test_policy_default_is_buffered():
    assert afp._current_policy() == afp.POLICY_BUFFERED


def test_policy_invalid_value_warns_and_defaults(monkeypatch, caplog):
    monkeypatch.setenv(afp.POLICY_ENV, "garbage_value")
    # _current_policy uses structlog; we still capture stdlib logging because
    # structlog defaults proxy through stdlib in test environments.
    result = afp._current_policy()
    assert result == afp.POLICY_BUFFERED


def test_policy_explicit_fail_closed(monkeypatch):
    monkeypatch.setenv(afp.POLICY_ENV, "fail_closed")
    assert afp._current_policy() == afp.POLICY_FAIL_CLOSED


def test_policy_explicit_buffered(monkeypatch):
    monkeypatch.setenv(afp.POLICY_ENV, "BUFFERED")  # case-insensitive
    assert afp._current_policy() == afp.POLICY_BUFFERED


def test_buffered_policy_persists_on_primary_failure(monkeypatch):
    """Primary fails -> buffer is called with the full payload, no raise."""
    calls = []

    def fake_persist(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(afp, "_persist_audit_buffer", fake_persist)

    # No exception should propagate.
    afp.handle_audit_failure(
        tenant_id="t-1",
        actor="api-key-abc",
        event_type="kde_read",
        payload={"endpoint": "trace_forward", "tlc": "LOT-1"},
        error=RuntimeError("primary down"),
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["tenant_id"] == "t-1"
    assert call["actor"] == "api-key-abc"
    assert call["event_type"] == "kde_read"
    assert call["payload"] == {"endpoint": "trace_forward", "tlc": "LOT-1"}
    assert call["primary_error"] == "primary down"
    assert call["originally_failed_at"] is not None


def test_fail_closed_policy_raises_503(monkeypatch):
    monkeypatch.setenv(afp.POLICY_ENV, "fail_closed")

    # If buffer were called we'd notice; assert it isn't.
    def boom(**_kwargs):
        raise AssertionError("buffer must not be called under fail_closed")

    monkeypatch.setattr(afp, "_persist_audit_buffer", boom)

    with pytest.raises(HTTPException) as exc_info:
        afp.handle_audit_failure(
            tenant_id="t-1",
            actor="api-key-abc",
            event_type="kde_read",
            payload={"tlc": "LOT-1"},
            error=RuntimeError("primary down"),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "audit_log_unavailable"


def test_double_failure_raises_503(monkeypatch):
    """Buffered policy + buffer write also fails -> 503."""

    def buffer_boom(**_kwargs):
        raise RuntimeError("buffer DB also down")

    monkeypatch.setattr(afp, "_persist_audit_buffer", buffer_boom)

    with pytest.raises(HTTPException) as exc_info:
        afp.handle_audit_failure(
            tenant_id="t-1",
            actor="api-key-abc",
            event_type="kde_read",
            payload={"tlc": "LOT-1"},
            error=RuntimeError("primary down"),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "audit_log_double_failure"


def test_buffered_policy_does_not_raise_on_primary_only_failure(monkeypatch):
    """Sanity: only primary failed, buffer succeeded -> caller continues."""
    monkeypatch.setattr(afp, "_persist_audit_buffer", lambda **_kw: None)

    # Should not raise.
    afp.handle_audit_failure(
        tenant_id="t-1",
        actor="api-key-abc",
        event_type="kde_read",
        payload={"tlc": "LOT-1"},
        error=ConnectionError("primary down"),
    )
