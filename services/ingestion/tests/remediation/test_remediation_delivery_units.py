"""Fast unit tests for ``app.remediation.delivery``.

Covers the pure helpers (URL shape, HTML rendering, token skip reasons,
dev/prod sender behavior) plus the drainer's row-level outcomes with a stub
session, so no Postgres, network, or Resend key is needed. The live-DB
semantics (RLS, SECURITY DEFINER lookups, concurrent claims) stay covered by
``test_remediation_outbox_delivery.py``; the suppression gate has its own
focused file in ``test_suppression_gate.py``.
"""

from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

from app.remediation import delivery  # noqa: E402
from app.remediation.delivery import NotificationOutboxDrainer  # noqa: E402

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CASE_ID = "33333333-3333-3333-3333-333333333333"
OUTBOX_ID = "22222222-2222-2222-2222-222222222222"
TOKEN_ID = "44444444-4444-4444-4444-444444444444"


class _StubResult:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row is not None else []


class _StubSession:
    """Minimal Session fake routing on SQL text.

    Handles the suppression lookup, token SELECT, and outbox UPDATEs used by
    the drainer. Records every statement for assertions.
    """

    def __init__(self, suppressed=(), token_rows=None):
        self._suppressed = {e.strip().lower() for e in suppressed}
        self._tokens = dict(token_rows or {})
        self.calls: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = dict(params or {})
        self.calls.append((sql, params))
        if "agent_org.email_suppressions" in sql:
            hit = params.get("email_address") in self._suppressed
            return _StubResult((1,) if hit else None)
        if "FROM fsma.remediation_tokens" in sql and sql.strip().upper().startswith("SELECT"):
            row = self._tokens.get(params.get("token_id"))
            return _StubResult(row)
        return _StubResult(None, rowcount=1)

    def commit(self):
        pass

    def rollback(self):
        pass


def _row(**overrides):
    row = {
        "id": OUTBOX_ID,
        "case_id": CASE_ID,
        "recipient": "supplier@example.com",
        "subject": "Correction needed",
        "body": "Please correct the record.",
        "payload": {},
        "attempts": 0,
    }
    row.update(overrides)
    return row


def _live_token_row(**overrides):
    token = {
        "id": TOKEN_ID,
        "case_id": CASE_ID,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "revoked_at": None,
        "superseded_by": None,
        "exchange_count": 0,
    }
    token.update(overrides)
    return token


def _token_tuple(token):
    return (
        token["id"],
        token["case_id"],
        token["expires_at"],
        token["revoked_at"],
        token["superseded_by"],
        token["exchange_count"],
    )


def _drainer(session, sender=None, audits=None):
    recorded = audits if audits is not None else []
    drainer = NotificationOutboxDrainer(session, email_sender=sender or (lambda *a: "msg-1"))
    return drainer, recorded


@pytest.fixture()
def no_audit(monkeypatch):
    seen = []
    monkeypatch.setattr(delivery, "audit_event", lambda *a, **k: seen.append(k))
    return seen


def test_correction_url_carries_token_in_fragment():
    url = delivery.correction_url("raw-token-123")
    assert url == f"{delivery.CORRECTION_URL_BASE}#raw-token-123"
    assert "#" in url


def test_render_html_escapes_body_and_includes_link():
    html = delivery._render_html('<script>alert("x")</script>', "https://example.com/form#abc")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Open secure correction link" in html
    assert "https://example.com/form#abc" in html


def test_render_html_without_link_omits_button():
    html = delivery._render_html("Plain body text.", None)
    assert "Plain body text." in html
    assert "Open secure correction link" not in html


@pytest.mark.parametrize(
    ("token_row", "expected"),
    [
        (None, "token_missing"),
        (
            {
                "superseded_by": "new-id",
                "revoked_at": None,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
                "exchange_count": 0,
            },
            "token_superseded",
        ),
        (
            {
                "superseded_by": None,
                "revoked_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
                "exchange_count": 0,
            },
            "token_revoked",
        ),
        (
            {
                "superseded_by": None,
                "revoked_at": None,
                "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
                "exchange_count": 0,
            },
            "token_expired",
        ),
        (
            {
                "superseded_by": None,
                "revoked_at": None,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
                "exchange_count": 99,
            },
            "token_already_exchanged",
        ),
    ],
)
def test_token_skip_reasons(token_row, expected):
    assert NotificationOutboxDrainer._token_skip_reason(token_row) == expected


def test_healthy_token_is_not_skipped():
    token = _live_token_row()
    assert NotificationOutboxDrainer._token_skip_reason(token) is None


def test_default_sender_dev_fallback_logs_and_returns_none(monkeypatch, caplog):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(delivery, "is_production", lambda: False)
    with caplog.at_level("WARNING", logger="remediation.delivery"):
        assert delivery.default_email_sender("supplier@example.com", "Subject", "<p>hi</p>") is None


def test_default_sender_prod_without_key_raises(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(delivery, "is_production", lambda: True)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        delivery.default_email_sender("supplier@example.com", "Subject", "<p>hi</p>")


def test_drain_one_skips_row_without_recipient(no_audit):
    session = _StubSession()
    sent = []

    def _must_not_send(*args):
        sent.append(args)
        return "msg-1"

    drainer, _ = _drainer(session, sender=_must_not_send)
    assert drainer._drain_one(TENANT_ID, _row(recipient=None)) == "skipped"
    assert sent == []
    assert session.calls, "expected the skip UPDATE to run"
    assert session.calls[-1][1]["reason"] == "no_recipient"


def test_drain_one_skips_missing_token(no_audit):
    session = _StubSession(token_rows={})
    drainer, _ = _drainer(session)
    outcome = drainer._drain_one(TENANT_ID, _row(payload={"token_id": TOKEN_ID}))
    assert outcome == "skipped"
    assert session.calls[-1][1]["reason"] == "token_missing"


def test_drain_one_skips_expired_token_without_sending(no_audit):
    expired = _live_token_row(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    session = _StubSession(token_rows={TOKEN_ID: _token_tuple(expired)})
    drainer, _ = _drainer(session, sender=lambda *a: pytest.fail("expired token must never send"))
    assert drainer._drain_one(TENANT_ID, _row(payload={"token_id": TOKEN_ID})) == "skipped"
    assert session.calls[-1][1]["reason"] == "token_expired"


def test_drain_one_sends_link_free_row_and_marks_sent(no_audit):
    session = _StubSession()
    sent = []
    drainer, _ = _drainer(session, sender=lambda r, s, h: (sent.append((r, s, h)), "msg-9")[1])
    assert drainer._drain_one(TENANT_ID, _row()) == "sent"
    assert len(sent) == 1
    recipient, _subject, html = sent[0]
    assert recipient == "supplier@example.com"
    assert "Please correct the record." in html
    assert "Open secure correction link" not in html
    update_sql, _params = session.calls[-1]
    assert "provider_message_id" in update_sql


def test_drain_one_remints_token_and_emails_fresh_link(monkeypatch, no_audit):
    session = _StubSession(token_rows={TOKEN_ID: _token_tuple(_live_token_row())})
    monkeypatch.setattr(delivery.tokens, "revoke_tokens_for_case", lambda *a, **k: [])
    monkeypatch.setattr(
        delivery.tokens,
        "issue_token",
        lambda *a, **k: {"token_id": "55555555-5555-5555-5555-555555555555", "token": "fresh-raw-token"},
    )
    sent = []
    drainer, _ = _drainer(session, sender=lambda r, s, h: (sent.append((r, s, h)), "msg-2")[1])
    assert drainer._drain_one(TENANT_ID, _row(payload={"token_id": TOKEN_ID})) == "sent"
    assert len(sent) == 1
    assert "fresh-raw-token" in sent[0][2]
    payload_updates = [(sql, params) for sql, params in session.calls if "token_id" in params and "payload" in sql]
    assert payload_updates, "expected the row to repoint at the fresh token before sending"
    assert payload_updates[0][1]["token_id"] == "55555555-5555-5555-5555-555555555555"


def test_drain_one_provider_failure_reschedules_with_backoff(no_audit):
    session = _StubSession()

    def _boom(*args):
        raise RuntimeError("provider unavailable")

    drainer, _ = _drainer(session, sender=_boom)
    assert drainer._drain_one(TENANT_ID, _row()) == "rescheduled"
    update_sql, params = session.calls[-1]
    assert params["attempts"] == 1
    assert "provider unavailable" in params["reason"]
    assert "next_attempt_at" in update_sql


def test_drain_one_marks_failed_after_max_attempts(no_audit):
    from app.remediation.delivery import MAX_ATTEMPTS

    session = _StubSession()

    def _boom(*args):
        raise RuntimeError("still down")

    drainer, _ = _drainer(session, sender=_boom)
    assert drainer._drain_one(TENANT_ID, _row(attempts=MAX_ATTEMPTS - 1)) == "failed"
    update_sql, params = session.calls[-1]
    assert "failed" in update_sql
    assert params["attempts"] == MAX_ATTEMPTS


def test_drain_tenant_once_aggregates_per_row_outcomes(monkeypatch):
    session = _StubSession()
    drainer = NotificationOutboxDrainer(session)
    monkeypatch.setattr(drainer, "_due_rows", lambda tenant_id, batch_size: [_row(), _row(), _row()])
    calls = {"n": 0}

    def _claim(tenant_id, outbox_id):
        calls["n"] += 1
        return True

    outcomes = iter(["sent", "skipped", "rescheduled"])
    monkeypatch.setattr(drainer, "_claim", _claim)
    monkeypatch.setattr(drainer, "_drain_one", lambda tenant_id, row: next(outcomes))
    summary = drainer.drain_tenant_once(TENANT_ID)
    assert summary == {"claimed": 3, "sent": 1, "skipped": 1, "failed": 0, "rescheduled": 1}


def test_drain_tenant_once_skips_rows_lost_to_another_drainer(monkeypatch):
    session = _StubSession()
    drainer = NotificationOutboxDrainer(session)
    monkeypatch.setattr(drainer, "_due_rows", lambda tenant_id, batch_size: [_row()])
    monkeypatch.setattr(drainer, "_claim", lambda tenant_id, outbox_id: False)
    monkeypatch.setattr(drainer, "_drain_one", lambda tenant_id, row: pytest.fail("unclaimed row must not drain"))
    assert drainer.drain_tenant_once(TENANT_ID) == {
        "claimed": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "rescheduled": 0,
    }


def test_drain_all_tenants_continues_past_tenant_failure(monkeypatch):
    session = _StubSession()
    import shared.maintenance_tenants as maintenance

    monkeypatch.setattr(maintenance, "list_maintenance_tenant_ids", lambda *a, **k: ["tenant-a", "tenant-b"])
    monkeypatch.setattr(delivery, "tenant_scope", lambda tid: nullcontext())
    monkeypatch.setattr(delivery, "set_tenant_guc", lambda session, tid: None)

    def _fake_drain(self, tenant_id, batch_size=50):
        if tenant_id == "tenant-a":
            raise RuntimeError("tenant a exploded")
        return {"claimed": 1, "sent": 1, "skipped": 0, "failed": 0, "rescheduled": 0}

    monkeypatch.setattr(NotificationOutboxDrainer, "drain_tenant_once", _fake_drain)
    totals = delivery.drain_all_tenants(session)
    assert totals["sent"] == 1
    assert totals["claimed"] == 1


def test_record_e2e_delivery_writes_jsonl(tmp_path, monkeypatch):
    outbox = tmp_path / "emails.jsonl"
    monkeypatch.setenv("REGENGINE_E2E_EMAIL_OUTBOX", str(outbox))
    delivery._record_e2e_delivery("supplier@example.com", "Correction needed", "https://x#tok")
    payload = json.loads(outbox.read_text(encoding="utf-8").strip())
    assert payload == {
        "kind": "delivered",
        "recipient": "supplier@example.com",
        "subject": "Correction needed",
        "link": "https://x#tok",
    }


def test_record_e2e_delivery_noop_without_env(monkeypatch):
    monkeypatch.delenv("REGENGINE_E2E_EMAIL_OUTBOX", raising=False)
    delivery._record_e2e_delivery("supplier@example.com", "Correction needed", None)
