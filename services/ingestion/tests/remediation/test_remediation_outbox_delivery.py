"""Outbox drainer: real delivery with re-mint-at-send semantics.

Runs against the migrated scratch Postgres (v101 delivery columns) with the
non-superuser role, so FORCE RLS and the SECURITY DEFINER token lookups are
genuinely enforced during draining — not mocked.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from .conftest import requires_db, upload_fixture

pytestmark = requires_db

SUPPLIER_EMAIL = "logistics@valleyfarms.example"


class StubSender:
    """Records sends; optionally fails the first N calls."""

    def __init__(self, fail_times: int = 0):
        self.sent = []  # (recipient, subject, html)
        self.fail_times = fail_times

    def __call__(self, recipient, subject, html):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("provider unavailable")
        self.sent.append((recipient, subject, html))
        return f"msg-{len(self.sent)}"


@pytest.fixture()
def drain_session(app_engine):
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=app_engine)()
    yield db
    db.close()


def _case_with_link(client, supplier_email: str = SUPPLIER_EMAIL):
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    blocked = next(r for r in body["records"] if r["blocking"])
    case_id = blocked["remediation_case_id"]
    link = client.post(
        f"/api/v1/remediation/cases/{case_id}/link",
        json={"supplier_email": supplier_email},
    ).json()
    return case_id, link


def _drain(db, tenant_id, sender):
    from services.ingestion.app.remediation.delivery import NotificationOutboxDrainer
    from shared.tenant_context import set_tenant_guc, tenant_scope

    drainer = NotificationOutboxDrainer(db, email_sender=sender)
    with tenant_scope(tenant_id):
        set_tenant_guc(db, tenant_id)
        return drainer.drain_tenant_once(tenant_id)


def _outbox_rows(admin_engine, case_id):
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, status, attempts, sent_at, last_error, provider_message_id,
                       payload, next_attempt_at
                FROM fsma.notification_outbox
                WHERE case_id = CAST(:c AS uuid)
                ORDER BY created_at ASC
                """
            ),
            {"c": case_id},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def _token_from_email(html: str) -> str:
    match = re.search(r"supplier/form#([A-Za-z0-9_\-]+)", html)
    assert match, f"no correction link in email html: {html[:200]}"
    return match.group(1)


def test_drain_sends_fresh_link_and_supersedes_original(client, admin_engine, drain_session):
    case_id, link = _case_with_link(client)
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "queued"

    sender = StubSender()
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["sent"] == 1, summary

    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "sent"
    assert entry["sent_at"] is not None
    assert entry["provider_message_id"] == "msg-1"

    recipient, subject, html = sender.sent[0]
    assert recipient == SUPPLIER_EMAIL
    assert "Correction needed" in subject

    emailed_token = _token_from_email(html)
    assert emailed_token != link["token"], "drainer must mint a fresh token, not resend the buyer's copy"
    assert entry["payload"]["token_id"] != link["token_id"], "outbox row must repoint at the live token"

    with admin_engine.connect() as conn:
        original = conn.execute(
            text("SELECT revoked_at, superseded_by FROM fsma.remediation_tokens WHERE id = CAST(:t AS uuid)"),
            {"t": link["token_id"]},
        ).fetchone()
        assert original[0] is not None, "original token must be revoked on reissue"
        assert str(original[1]) == entry["payload"]["token_id"]

        # TTL respected: the fresh token expires when the original would have.
        fresh_expires = conn.execute(
            text("SELECT expires_at FROM fsma.remediation_tokens WHERE id = CAST(:t AS uuid)"),
            {"t": entry["payload"]["token_id"]},
        ).scalar()
    original_expires = datetime.fromisoformat(link["expires_at"])
    assert abs((fresh_expires - original_expires).total_seconds()) < 60

    # Hash-at-rest survives delivery: the emailed raw token is nowhere in the DB.
    with admin_engine.connect() as conn:
        outbox_dump = conn.execute(
            text("SELECT COALESCE(string_agg(row_to_json(n)::text, ''), '') FROM fsma.notification_outbox n")
        ).scalar()
        token_dump = conn.execute(
            text("SELECT COALESCE(string_agg(row_to_json(t)::text, ''), '') FROM fsma.remediation_tokens t")
        ).scalar()
    assert emailed_token not in outbox_dump
    assert emailed_token not in token_dump

    # The emailed link actually works: it mints a supplier session.
    exchange = client.post("/api/v1/remediation/supplier/exchange", json={"token": emailed_token})
    assert exchange.status_code == 200, exchange.text


def test_drain_is_idempotent_per_entry(client, admin_engine, drain_session):
    case_id, _link = _case_with_link(client)
    sender = StubSender()
    first = _drain(drain_session, client.tenant_a, sender)
    second = _drain(drain_session, client.tenant_a, sender)
    assert first["sent"] == 1
    assert second["claimed"] == 0
    assert len(sender.sent) == 1
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "sent"


def test_reissue_supersedes_older_outbox_entry(client, admin_engine, drain_session):
    case_id, _first_link = _case_with_link(client)
    second_link = client.post(
        f"/api/v1/remediation/cases/{case_id}/link",
        json={"supplier_email": SUPPLIER_EMAIL},
    ).json()
    assert second_link["token_id"]

    sender = StubSender()
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary == {"claimed": 2, "sent": 1, "skipped": 1, "failed": 0, "rescheduled": 0}
    assert len(sender.sent) == 1

    first_entry, second_entry = _outbox_rows(admin_engine, case_id)
    assert first_entry["status"] == "skipped"
    assert first_entry["last_error"] == "token_superseded"
    assert second_entry["status"] == "sent"


def test_expired_token_skipped_without_reissue(client, admin_engine, drain_session):
    case_id, link = _case_with_link(client)
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE fsma.remediation_tokens SET expires_at = now() - interval '1 hour' WHERE id = CAST(:t AS uuid)"
            ),
            {"t": link["token_id"]},
        )

    sender = StubSender()
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["skipped"] == 1
    assert not sender.sent

    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "skipped"
    assert entry["last_error"] == "token_expired"
    with admin_engine.connect() as conn:
        token_count = conn.execute(
            text("SELECT COUNT(*) FROM fsma.remediation_tokens WHERE case_id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).scalar()
    assert token_count == 1, "expiry recovery is a buyer reissue; the drainer must not mint"


def test_revoked_link_never_emailed(client, admin_engine, drain_session):
    case_id, _link = _case_with_link(client)
    revoke = client.post(f"/api/v1/remediation/cases/{case_id}/link/revoke")
    assert revoke.status_code == 200

    sender = StubSender()
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["skipped"] == 1
    assert not sender.sent
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["last_error"] == "token_revoked"


def test_exchanged_token_not_reemailed(client, admin_engine, drain_session):
    case_id, link = _case_with_link(client)
    exchange = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]})
    assert exchange.status_code == 200

    sender = StubSender()
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["skipped"] == 1
    assert not sender.sent
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["last_error"] == "token_already_exchanged"


def test_transient_failure_reschedules_then_delivers(client, admin_engine, drain_session):
    case_id, _link = _case_with_link(client)
    sender = StubSender(fail_times=1)

    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["rescheduled"] == 1
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "queued"
    assert entry["attempts"] == 1
    assert "provider unavailable" in entry["last_error"]
    assert entry["next_attempt_at"] > datetime.now(timezone.utc)

    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE fsma.notification_outbox SET next_attempt_at = now() WHERE case_id = CAST(:c AS uuid)"),
            {"c": case_id},
        )
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["sent"] == 1

    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "sent"
    # The retry superseded the token minted before the failed send; the
    # delivered link is the live one.
    emailed_token = _token_from_email(sender.sent[0][2])
    exchange = client.post("/api/v1/remediation/supplier/exchange", json={"token": emailed_token})
    assert exchange.status_code == 200, exchange.text


def test_max_attempts_flips_failed(client, admin_engine, drain_session):
    from services.ingestion.app.remediation.delivery import MAX_ATTEMPTS

    case_id, _link = _case_with_link(client)
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE fsma.notification_outbox SET attempts = :a WHERE case_id = CAST(:c AS uuid)"),
            {"a": MAX_ATTEMPTS - 1, "c": case_id},
        )

    sender = StubSender(fail_times=10)
    summary = _drain(drain_session, client.tenant_a, sender)
    assert summary["failed"] == 1
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "failed"
    assert entry["attempts"] == MAX_ATTEMPTS


def test_buyer_notification_without_recipient_stays_preview(client, admin_engine, drain_session):
    """recipient=None entries (buyer in-app previews) are never queued."""
    from services.ingestion.app.remediation import outbox
    from shared.tenant_context import set_tenant_guc, tenant_scope

    tid = client.tenant_a
    with tenant_scope(tid):
        set_tenant_guc(drain_session, tid)
        outbox.enqueue_preview(
            drain_session,
            tenant_id=tid,
            case_id=None,
            recipient=None,
            subject="Supplier correction released: manifest.csv (row 2)",
            body="The supplier corrected row 2.",
            payload={},
        )
        drain_session.commit()

        sender = StubSender()
        summary = _drain(drain_session, tid, sender)
    assert summary["claimed"] == 0
    assert not sender.sent

    with admin_engine.connect() as conn:
        status = conn.execute(
            text(
                "SELECT status FROM fsma.notification_outbox WHERE tenant_id = CAST(:t AS uuid) AND recipient IS NULL"
            ),
            {"t": tid},
        ).scalar()
    assert status == "pending"


def test_drain_all_tenants_iterates_and_delivers(client, admin_engine, drain_session):
    """The scheduler entry point discovers tenants and drains under RLS."""
    from services.ingestion.app.remediation.delivery import drain_all_tenants

    case_id, _link = _case_with_link(client)
    sender = StubSender()
    totals = drain_all_tenants(drain_session, email_sender=sender)
    assert totals["sent"] >= 1
    (entry,) = _outbox_rows(admin_engine, case_id)
    assert entry["status"] == "sent"
    assert any(r == SUPPLIER_EMAIL for r, _s, _h in sender.sent)


def test_outbox_listing_exposes_delivery_status(client, drain_session):
    case_id, _link = _case_with_link(client)
    _drain(drain_session, client.tenant_a, StubSender())

    notifications = client.get("/api/v1/remediation/outbox").json()["notifications"]
    entry = next(n for n in notifications if n["case_id"] == case_id)
    assert entry["status"] == "sent"
    assert entry["sent_at"] is not None
    assert entry["provider_message_id"] == "msg-1"
