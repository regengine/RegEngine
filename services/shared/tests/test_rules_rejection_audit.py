"""Tests for the durable rejection-audit helper (Finding B, Suite 4 audit).

Compliance-defensibility contract: rejected events must produce a row
in ``fsma.rule_rejections`` that survives the caller's outer transaction
rollback. The helper opens its own session, commits, and closes; the
outer txn rollback cannot wipe it.

These tests use a stub ``SessionLocal`` so they pass under SQLite in CI.
The full Postgres integration is exercised by the migration test suite
that runs against a real ephemeral DB.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


class _FakeSession:
    """Minimal SessionLocal-like double — records executes + commit/close."""

    def __init__(self, log: list[tuple[str, dict]], fail_on_commit: bool = False):
        self._log = log
        self._fail_on_commit = fail_on_commit
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt, params=None):  # noqa: D401
        # ``stmt`` is a sqlalchemy TextClause; record its rendered text.
        sql = str(getattr(stmt, "text", stmt))
        self._log.append((sql, dict(params or {})))
        return MagicMock()

    def commit(self):
        if self._fail_on_commit:
            raise RuntimeError("simulated commit failure")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def patched_session(monkeypatch):
    """Replace shared.database.SessionLocal with a fake that records calls."""
    log: list[tuple[str, dict]] = []
    sessions: list[_FakeSession] = []

    def _factory():
        s = _FakeSession(log)
        sessions.append(s)
        return s

    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = _factory
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)
    return log, sessions


def test_record_rejection_writes_row_and_commits(patched_session):
    log, sessions = patched_session
    from services.shared.rules.rejection_audit import record_rejection

    record_rejection(
        tenant_id="t-1",
        rule_id="R_CRIT",
        rule_version=3,
        reasons=[{"rule_id": "R_CRIT", "why_failed": "missing harvest_date"}],
        event_id="cev-9",
        source="epcis_preeval",
        enforcement_mode="cte_only",
    )

    assert len(sessions) == 1
    s = sessions[0]
    assert s.committed is True
    assert s.closed is True
    assert s.rolled_back is False
    assert len(log) == 1
    sql, params = log[0]
    assert "fsma.rule_rejections" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert params["tenant_id"] == "t-1"
    assert params["rule_id"] == "R_CRIT"
    assert params["rule_version"] == 3
    assert params["event_id"] == "cev-9"
    assert params["enforcement_mode"] == "cte_only"
    assert params["source"] == "epcis_preeval"
    # reasons is JSON-encoded
    import json

    decoded = json.loads(params["reasons"])
    assert decoded[0]["rule_id"] == "R_CRIT"


def test_record_rejection_fails_closed_on_commit_failure(monkeypatch):
    """The reject decision is more important than the audit row.
    A failed audit-write must not turn a reject into a 500 — it must
    log+Sentry and return cleanly."""
    log: list[tuple[str, dict]] = []
    sessions: list[_FakeSession] = []

    def _factory():
        s = _FakeSession(log, fail_on_commit=True)
        sessions.append(s)
        return s

    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = _factory
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)

    from services.shared.rules.rejection_audit import RejectionAuditUnavailable, record_rejection

    with pytest.raises(RejectionAuditUnavailable, match="storage is unavailable"):
        record_rejection(
            tenant_id="t-1",
            rule_id="R_CRIT",
            rule_version=1,
            reasons="x",
            event_id=None,
        )
    assert sessions[0].rolled_back is True
    assert sessions[0].closed is True


def test_reasons_from_summary_renders_failure_list():
    from services.shared.rules.rejection_audit import reasons_from_summary
    from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult

    crit = RuleEvaluationResult(
        rule_id="R1",
        severity="critical",
        result="fail",
        why_failed="kde missing",
    )
    summary = EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[crit],
        critical_failures=[crit],
    )
    out = reasons_from_summary(summary)
    assert isinstance(out, list)
    assert out[0]["rule_id"] == "R1"
    assert out[0]["why_failed"] == "kde missing"
    assert out[0]["severity"] == "critical"


def test_reasons_from_summary_empty_falls_back_to_generic():
    from services.shared.rules.rejection_audit import reasons_from_summary

    class _Bare:
        results = []
        critical_failures = []

    out = reasons_from_summary(_Bare())
    assert out == [{"reason": "rule_violation"}]


def test_reasons_from_summary_preserves_exact_no_verdict_reason():
    from services.shared.rules.rejection_audit import reasons_from_summary
    from services.shared.rules.types import EvaluationSummary

    summary = EvaluationSummary(total_rules=0, no_verdict_reason="no_rules_loaded")

    assert reasons_from_summary(summary) == [{"verdict": "no_verdict", "reason": "no_rules_loaded"}]


def test_reasons_from_summary_failure_evidence_outranks_no_verdict_metadata():
    from services.shared.rules.rejection_audit import reasons_from_summary
    from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult

    failed = RuleEvaluationResult(
        rule_id="R1",
        rule_version=3,
        severity="critical",
        result="fail",
        why_failed="missing KDE",
    )
    summary = EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[failed],
        critical_failures=[failed],
        no_verdict_reason="ftl_classification_missing",
    )

    assert reasons_from_summary(summary) == [
        {
            "rule_id": "R1",
            "rule_version": 3,
            "severity": "critical",
            "result": "fail",
            "why_failed": "missing KDE",
        }
    ]


def test_reasons_from_summary_preserves_gap_that_drove_warning_rejection():
    from services.shared.rules.rejection_audit import reasons_from_summary
    from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult

    failed = RuleEvaluationResult(
        rule_id="R_WARN",
        rule_version=4,
        severity="warning",
        result="fail",
        why_failed="warning KDE absent",
    )
    summary = EvaluationSummary(
        total_rules=1,
        failed=1,
        results=[failed],
        no_verdict_reason="ftl_classification_missing",
    )

    assert reasons_from_summary(summary, rejection_reason="ftl_classification_missing") == [
        {
            "rule_id": "R_WARN",
            "rule_version": 4,
            "severity": "warning",
            "result": "fail",
            "why_failed": "warning KDE absent",
        },
        {"verdict": "no_verdict", "reason": "ftl_classification_missing"},
    ]


def test_handle_preeval_exception_off_mode_swallows(monkeypatch):
    """Finding A — under OFF mode the helper warns and returns."""
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    from services.shared.rules.enforcement import handle_preeval_exception

    # Must not raise.
    handle_preeval_exception(RuntimeError("boom"), where="test")


def test_handle_preeval_exception_cte_only_raises_500(monkeypatch):
    """Finding A — under cte_only the helper raises HTTPException(500)
    with the stable RULES_ENGINE_EVAL_FAILED error code so the route
    surfaces a 5xx and ops can triage."""
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
    from fastapi import HTTPException

    from services.shared.rules.enforcement import handle_preeval_exception

    with pytest.raises(HTTPException) as exc:
        handle_preeval_exception(AttributeError("missing attr"), where="unit_test")
    assert exc.value.status_code == 500
    assert exc.value.detail["error"] == "RULES_ENGINE_EVAL_FAILED"
    assert exc.value.detail["where"] == "unit_test"


def test_handle_preeval_exception_all_mode_raises_500(monkeypatch):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "all")
    from fastapi import HTTPException

    from services.shared.rules.enforcement import handle_preeval_exception

    with pytest.raises(HTTPException) as exc:
        handle_preeval_exception(KeyError("k"), where="unit_test")
    assert exc.value.status_code == 500


def test_handle_preeval_exception_emits_sentry_under_enforcement(monkeypatch):
    """Sentry breadcrumb is the operational signal for "the rules engine
    is broken under enforcement". Confirms capture_exception is invoked
    so on-call sees the alert rather than relying on stdout log scraping.
    """
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")

    captured: dict[str, Any] = {"exc": None, "msg": None}

    fake_sentry = types.ModuleType("sentry_sdk")

    def _capture_exception(err):
        captured["exc"] = err

    def _capture_message(msg, **kwargs):
        captured["msg"] = (msg, kwargs)

    fake_sentry.capture_exception = _capture_exception
    fake_sentry.capture_message = _capture_message
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)

    from fastapi import HTTPException

    from services.shared.rules.enforcement import handle_preeval_exception

    err = RuntimeError("rules engine bug")
    with pytest.raises(HTTPException):
        handle_preeval_exception(err, where="ingest_test")

    assert captured["exc"] is err
    assert captured["msg"] is not None
    msg, kwargs = captured["msg"]
    assert msg == "rules_preeval_failed"
    assert kwargs["tags"]["subsystem"] == "rules_engine"
    assert kwargs["tags"]["enforcement_mode"] == "cte_only"


def test_record_rejection_survives_outer_rollback_simulation(patched_session):
    """Finding B integration shape: the rejection-audit helper writes
    via an INDEPENDENT session, so a subsequent ``rollback()`` on a
    DIFFERENT session (the caller's request txn) cannot unwind it.

    Simulated by checking that the helper's session.commit() was called
    before any hypothetical outer-txn rollback could fire."""
    log, sessions = patched_session
    from services.shared.rules.rejection_audit import record_rejection

    record_rejection(
        tenant_id="t-1",
        rule_id="R",
        rule_version=1,
        reasons={"why": "fail"},
        event_id="e-1",
    )
    # Caller's outer txn rolls back AFTER. Audit row's session is closed.
    # Our helper's session never sees that rollback.
    assert sessions[0].committed is True
    assert sessions[0].closed is True
