"""v101 -- delivery tracking on fsma.notification_outbox.

The remediation notification outbox was preview-only (v095: status CHECK
allowed only 'pending'/'previewed' and nothing ever updated a row). The
drainer in ``services/ingestion/app/remediation/delivery.py`` now delivers
entries by email, so the table needs delivery bookkeeping:

* ``attempts`` / ``next_attempt_at`` -- retry counter + backoff schedule,
  same shape as ``webhook_outbox``.
* ``claimed_at`` -- set when a drainer claims a row (``status='sending'``);
  lets a restarted drainer reclaim rows stranded by a crash mid-send.
* ``sent_at`` / ``provider_message_id`` -- delivery receipt.
* ``last_error`` -- most recent failure/skip reason.
* status CHECK widened with 'queued', 'sending', 'sent', 'failed',
  'skipped'.

Deliverable entries are enqueued as ``'queued'`` (a NEW status) rather than
reusing ``'pending'``: rows enqueued before this migration were delivered
by hand under the preview-only regime, and the drainer re-mints (revokes)
tokens at send time -- draining the historical backlog would revoke links
buyers already delivered manually. Legacy ``'pending'`` rows therefore stay
preview-only forever, which also keeps this migration free of cross-tenant
UPDATEs (the table is FORCE RLS; a backfill would raise under a
non-superuser migration role).

RLS: the table already has FORCE RLS + the v095 tenant policy; ALTERs here
add columns only and do not touch policies. Guarded with to_regclass in the
v095 style so environments without the fsma slice no-op cleanly.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "7c4d9a1f2e8b"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "3ba0291a69f2"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUSES_NEW = "('pending', 'previewed', 'queued', 'sending', 'sent', 'failed', 'skipped')"
_STATUSES_OLD = "('pending', 'previewed')"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('fsma.notification_outbox') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.notification_outbox
                ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS last_error TEXT,
                ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
            ALTER TABLE fsma.notification_outbox
                DROP CONSTRAINT IF EXISTS notification_outbox_status_check;
            ALTER TABLE fsma.notification_outbox
                ADD CONSTRAINT notification_outbox_status_check
                CHECK (status IN {_STATUSES_NEW});
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('fsma.notification_outbox') IS NULL THEN
                RETURN;
            END IF;
            -- Delivery statuses have no v095 equivalent; collapse them to
            -- 'pending' so the narrow CHECK can be restored.
            UPDATE fsma.notification_outbox
                SET status = 'pending'
                WHERE status NOT IN {_STATUSES_OLD};
            ALTER TABLE fsma.notification_outbox
                DROP CONSTRAINT IF EXISTS notification_outbox_status_check;
            ALTER TABLE fsma.notification_outbox
                ADD CONSTRAINT notification_outbox_status_check
                CHECK (status IN {_STATUSES_OLD});
            ALTER TABLE fsma.notification_outbox
                DROP COLUMN IF EXISTS attempts,
                DROP COLUMN IF EXISTS next_attempt_at,
                DROP COLUMN IF EXISTS claimed_at,
                DROP COLUMN IF EXISTS sent_at,
                DROP COLUMN IF EXISTS last_error,
                DROP COLUMN IF EXISTS provider_message_id;
        END $$;
        """
    )
