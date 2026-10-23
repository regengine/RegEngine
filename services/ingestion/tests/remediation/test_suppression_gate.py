"""Unit test for the agent_org suppression gate in ``NotificationOutboxDrainer``.

Unit-level, no live DB. The suppression gate is one parameterized SELECT
plus a pure Python branch, so it is exercised here with a stub session.

Per ``DESIGN_agent-org.md`` section 4: the gate must run unconditionally,
before any token reminting or provider call, for every row the drainer would
otherwise send. ``email_sender=lambda *a: pytest.fail(...)`` is the actual
proof required by the spec ("a suppressed address must never receive mail
from that path") — if the gate is ever removed or reordered after the send
call, this test fails immediately because the stub sender is invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure `app.remediation...` resolves from the ingestion service.
service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

from app.remediation.delivery import NotificationOutboxDrainer  # noqa: E402

TENANT_ID = "11111111-1111-1111-1111-111111111111"


class _StubResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _StubSession:
    """Fakes just enough of Session.execute for is_suppressed() plus the
    drainer's own UPDATE statements. Records every call so tests can assert
    on the recorded skip reason without a real database."""

    def __init__(self, suppressed_emails):
        self._suppressed = set(suppressed_emails)
        self.calls: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = dict(params or {})
        self.calls.append((sql, params))
        if "agent_org.email_suppressions" in sql:
            hit = params.get("email_address") in self._suppressed
            return _StubResult((1,) if hit else None)
        # Any other statement (e.g. the _finish_skipped/_finish_sent UPDATE)
        # — no callers here inspect its return value.
        return _StubResult(None)

    def commit(self):
        pass

    def rollback(self):  # pragma: no cover — not exercised by this gate
        pass


def _row(recipient: str, **overrides) -> dict:
    row = {
        "id": "22222222-2222-2222-2222-222222222222",
        "case_id": "33333333-3333-3333-3333-333333333333",
        "recipient": recipient,
        "subject": "Correction needed",
        "body": "Please correct the record.",
        "payload": {},
        "attempts": 0,
    }
    row.update(overrides)
    return row


def test_drain_one_skips_suppressed_recipient_without_sending():
    session = _StubSession({"blocked@example.com"})

    def _must_not_send(*_args):
        pytest.fail("suppressed recipient must never reach the email sender")

    drainer = NotificationOutboxDrainer(session, email_sender=_must_not_send)
    outcome = drainer._drain_one(TENANT_ID, _row("blocked@example.com"))

    assert outcome == "skipped"
    # The recorded skip reason must be the new agent_org-specific one, not a
    # generic failure — and the UPDATE must have actually run.
    update_calls = [(sql, params) for sql, params in session.calls if "notification_outbox" in sql]
    assert update_calls, "expected the outbox row to be updated with a skip reason"
    _, update_params = update_calls[-1]
    assert update_params["reason"] == "recipient_suppressed"


def test_drain_one_matches_suppression_case_and_whitespace_insensitively():
    # is_suppressed() normalizes with strip().lower() on both write and read
    # paths (see shared/agent_org/suppression.py) — the gate must honor that
    # normalization, not just an exact byte-for-byte match.
    session = _StubSession({"blocked@example.com"})

    def _must_not_send(*_args):
        pytest.fail("suppressed recipient must never reach the email sender")

    drainer = NotificationOutboxDrainer(session, email_sender=_must_not_send)
    outcome = drainer._drain_one(TENANT_ID, _row("  Blocked@Example.com  "))

    assert outcome == "skipped"


def test_drain_one_sends_when_recipient_is_not_suppressed():
    session = _StubSession({"blocked@example.com"})
    sent = []

    def _record_send(recipient, subject, html):
        sent.append((recipient, subject, html))
        return "msg-1"

    drainer = NotificationOutboxDrainer(session, email_sender=_record_send)
    # No token_id in payload, so the drainer sends directly without a link.
    outcome = drainer._drain_one(TENANT_ID, _row("allowed@example.com"))

    assert outcome == "sent"
    assert sent and sent[0][0] == "allowed@example.com"


def test_suppression_check_runs_before_token_lookup():
    # The gate is a hard, unconditional pre-check: even a row carrying a
    # payload.token_id must be skipped for suppression before any token
    # table lookup happens (proving ordering, not just the end outcome).
    session = _StubSession({"blocked@example.com"})

    def _must_not_send(*_args):
        pytest.fail("suppressed recipient must never reach the email sender")

    drainer = NotificationOutboxDrainer(session, email_sender=_must_not_send)
    row = _row("blocked@example.com", payload={"token_id": "44444444-4444-4444-4444-444444444444"})
    outcome = drainer._drain_one(TENANT_ID, row)

    assert outcome == "skipped"
    token_lookups = [sql for sql, _ in session.calls if "remediation_tokens" in sql]
    assert not token_lookups, "suppression gate must short-circuit before any token lookup"
