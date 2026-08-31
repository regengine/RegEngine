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

Downgrade (#2884): non-destructive by design. The original downgrade rewrote
every non-legacy ``status`` to ``'pending'`` and then dropped ``sent_at`` /
``provider_message_id`` / ``attempts`` / ``claimed_at`` / ``last_error`` /
``next_attempt_at``. That destroyed the record of which supplier
notifications had actually been delivered, and — because the drainer claims
rows by status — re-armed already-sent rows for a second send, re-minting
(and thereby revoking) tokens buyers had already received. It also
contradicted this migration's own upgrade rationale above, which refuses to
touch historical rows for exactly that reason, and the ``UPDATE`` would in
any case raise under FORCE RLS on a migration role with no tenant GUC.

So the downgrade now:

* RETAINS every delivery column. A wider column set than v095 expects is
  harmless — v095-era code simply does not reference them — whereas lost
  delivery receipts are unrecoverable.
* Restores the narrow v095 status CHECK, but adds it ``NOT VALID`` first and
  then attempts ``VALIDATE CONSTRAINT``. A ``NOT VALID`` CHECK is still
  enforced on every INSERT and UPDATE, so the v095 write contract is back in
  force immediately; only pre-existing delivered rows are exempted. On a
  database with no delivery history the VALIDATE succeeds and the constraint
  ends up fully valid, identical to v095. Where delivered rows exist the
  VALIDATE raises ``check_violation``, which is caught and downgraded to a
  WARNING naming the situation — the receipts stay, and the constraint stays
  ``NOT VALID`` rather than the rows being rewritten.
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
    # #2884: retain the delivery columns and every delivered row's receipt.
    # See the module docstring for why this deliberately does not restore the
    # exact v095 column set.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('fsma.notification_outbox') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.notification_outbox
                DROP CONSTRAINT IF EXISTS notification_outbox_status_check;

            -- NOT VALID still constrains every INSERT and UPDATE, so the v095
            -- status vocabulary is enforced again from here on; it only
            -- exempts rows that already carry a delivery status. Rewriting
            -- those rows to 'pending' would destroy the delivery receipt and
            -- make already-sent notifications re-sendable.
            ALTER TABLE fsma.notification_outbox
                ADD CONSTRAINT notification_outbox_status_check
                CHECK (status IN {_STATUSES_OLD}) NOT VALID;

            BEGIN
                -- Succeeds (leaving a fully valid, v095-identical constraint)
                -- on any database that never delivered anything.
                ALTER TABLE fsma.notification_outbox
                    VALIDATE CONSTRAINT notification_outbox_status_check;
            EXCEPTION WHEN check_violation THEN
                RAISE WARNING
                    'fsma.notification_outbox holds rows with post-v095 delivery '
                    'statuses; notification_outbox_status_check left NOT VALID so '
                    'their delivery receipts are preserved (#2884). New writes are '
                    'still restricted to the v095 vocabulary.';
            END;

            -- Delivery columns are intentionally NOT dropped.
        END $$;
        """
    )
