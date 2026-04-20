"""Add webhook_outbox table for durable per-tenant webhook delivery (#1408).

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-04-20

Why
---
``services/admin/app/metrics.py::_notify_webhook`` posts the full
serialized review (including reviewer notes and provenance) to a single
global ``HALLUCINATION_WEBHOOK_URL`` env var, with HMAC-signing left
optional, and swallows every exception. That breaks cleanly for a
multi-tenant deploy:

  * Every tenant's approvals fan out to the same URL — Buyer A sees
    Buyer B's review notes.
  * A single ``except Exception`` with no outbox / retry means a 5xx,
    a timeout, or a DNS blip loses the event forever.
  * No signature is required, so downstream receivers can't
    distinguish "RegEngine notified us" from a cross-site forgery.

Fix (code-side, shipping alongside this migration):

  * ``tenant.settings.review_webhook_url`` + ``review_webhook_secret``
    resolve per-tenant; the env var is a last-resort single-tenant
    fallback.
  * SSRF guard rejects private / loopback / metadata-service targets
    (same classifier as ``services/ingestion/app/models.py``).
  * HMAC signing via ``shared/webhook_security`` is mandatory — no
    secret, no dispatch.
  * On any non-2xx / timeout / connection error, the payload is
    written to this ``webhook_outbox`` table and a separate drainer
    retries with exponential backoff.

Design mirrors ``graph_outbox`` (#1398, migration
``20260417_graph_outbox_v060``) so the operational story is uniform:
one drainer pattern, one reconcile call, one set of per-row metrics.

RLS
---
Tenant-scoped rows carry ``tenant_id UUID NOT NULL`` (webhook delivery
is always tenant-bound — unlike graph writes there is no legitimate
"global" webhook target). RLS is enabled with the same tenant-isolation
policy as ``graph_outbox``; sysadmin bypass is gated on the
``regengine_sysadmin`` DB role + ``regengine.is_sysadmin`` GUC.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_outbox (
            id              BIGSERIAL PRIMARY KEY,
            tenant_id       UUID NOT NULL,
            event_type      TEXT NOT NULL,
            -- Canonical target. Captured at enqueue time so a later change
            -- to tenant.settings doesn't redirect an already-queued event.
            target_url      TEXT NOT NULL,
            -- JSON body as stored-for-replay; signing happens at dispatch
            -- using the tenant's current review_webhook_secret so rotation
            -- doesn't strand pending rows behind a revoked secret.
            payload         JSONB NOT NULL,
            -- Optional stable dedupe key (e.g. review_id + status) so a
            -- retry-on-enqueue collapses into an upsert instead of
            -- double-delivering.
            dedupe_key      TEXT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'delivered', 'failed')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 10,
            last_error      TEXT NULL,
            last_status_code INTEGER NULL,
            enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            delivered_at    TIMESTAMPTZ NULL,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Drainer claims pending rows oldest-first by (next_attempt_at, id).
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_webhook_outbox_pending
        ON webhook_outbox (next_attempt_at ASC, id ASC)
        WHERE status = 'pending'
    """)

    # Operator drift query: "how many failed rows for tenant X".
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_webhook_outbox_tenant_status
        ON webhook_outbox (tenant_id, status)
    """)

    # Idempotency guard: same (event_type, dedupe_key) collapses.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_outbox_dedupe
        ON webhook_outbox (event_type, dedupe_key)
        WHERE dedupe_key IS NOT NULL
    """)

    op.execute("ALTER TABLE webhook_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_webhook_outbox ON webhook_outbox
        USING (
            tenant_id::text = current_setting('app.tenant_id', true)
            OR (
                current_user = 'regengine_sysadmin'
                AND current_setting('regengine.is_sysadmin', true) = 'true'
            )
        )
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_webhook_outbox ON webhook_outbox"
    )
    op.execute("DROP INDEX IF EXISTS uq_webhook_outbox_dedupe")
    op.execute("DROP INDEX IF EXISTS idx_webhook_outbox_tenant_status")
    op.execute("DROP INDEX IF EXISTS idx_webhook_outbox_pending")
    op.execute("DROP TABLE IF EXISTS webhook_outbox")
