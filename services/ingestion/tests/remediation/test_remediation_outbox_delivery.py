"""Data-free outbox preview behavior for a migrated scratch Postgres."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from .conftest import requires_db

pytestmark = requires_db


class StubSender:
    def __init__(self):
        self.sent = []

    def __call__(self, recipient, subject, html):
        self.sent.append((recipient, subject, html))
        return ""


@pytest.fixture()
def drain_session(app_engine):
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=app_engine)()
    yield db
    db.close()


def _drain(db, tenant_id, sender):
    from app.remediation.delivery import NotificationOutboxDrainer
    from shared.tenant_context import set_tenant_guc, tenant_scope

    drainer = NotificationOutboxDrainer(db, email_sender=sender)
    with tenant_scope(tenant_id):
        set_tenant_guc(db, tenant_id)
        return drainer.drain_tenant_once(tenant_id)


def test_buyer_notification_without_recipient_stays_preview(client, admin_engine, drain_session):
    from app.remediation import outbox
    from shared.tenant_context import set_tenant_guc, tenant_scope

    tid = client.tenant_a
    with tenant_scope(tid):
        set_tenant_guc(drain_session, tid)
        outbox.enqueue_preview(
            drain_session,
            tenant_id=tid,
            case_id=None,
            recipient=None,
            subject="Supplier correction released: manifest.csv",
            body="A correction was released.",
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
