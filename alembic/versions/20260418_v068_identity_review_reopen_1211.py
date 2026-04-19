"""identity_review_queue: reopen-after-distinct support — #1211.

v047 created ``fsma.identity_review_queue`` with

    UNIQUE (entity_a_id, entity_b_id)

which blocks an operator from re-queueing a pair that was previously
resolved ``confirmed_distinct`` when fresh evidence warrants another
look. ``service.queue_for_review`` then amplified the problem: its
idempotency check returned ANY existing row — including closed
``confirmed_distinct`` and ``confirmed_match`` rows — as the
"already queued" result, so a re-suggestion silently no-op'd.

Fix:

1. Drop the full-table UNIQUE constraint.
2. Replace it with a partial UNIQUE INDEX that only restricts
   ``status IN ('pending', 'deferred')`` — the active-review states.
   Closed rows (``confirmed_*``) no longer block fresh queueing of
   the same pair.
3. Add ``previous_review_id UUID`` (nullable, FK to ``review_id``)
   so a new review can link back to the closed review that preceded
   it, preserving the audit trail ("this pair was ruled distinct on
   X; a re-review was opened on Y because of fresh signal Z").

Application code (``services/shared/identity_resolution/service.py``)
scopes its idempotency check to ``status IN ('pending','deferred')``
and populates ``previous_review_id`` from the most-recent closed
row when re-queueing.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-04-18
"""
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Single DO block so the migration is idempotent and survives
    # environments where v047 was never applied (e.g. partially-reset
    # test DBs). Each step guards with IF EXISTS/NOT EXISTS checks.
    op.execute(
        """
        DO $$
        DECLARE
            _constraint_name text;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'identity_review_queue'
            ) THEN
                RAISE NOTICE 'fsma.identity_review_queue does not exist - skipping #1211 migration';
                RETURN;
            END IF;

            -- 1. Add previous_review_id column (idempotent).
            ALTER TABLE fsma.identity_review_queue
                ADD COLUMN IF NOT EXISTS previous_review_id UUID
                    REFERENCES fsma.identity_review_queue(review_id)
                    ON DELETE SET NULL;

            COMMENT ON COLUMN fsma.identity_review_queue.previous_review_id IS
                'Link to the prior closed review for this entity pair, when the pair was '
                're-queued after a confirmed_* resolution. Preserves audit trail across '
                'reopen cycles (#1211).';

            -- 2. Drop the full-table UNIQUE constraint if present.
            -- v047 may have emitted either a named constraint or an
            -- auto-named one ("identity_review_queue_entity_a_id_entity_b_id_key").
            -- Discover it dynamically rather than hard-code the name.
            SELECT c.conname INTO _constraint_name
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'fsma'
              AND t.relname = 'identity_review_queue'
              AND c.contype = 'u'
              AND c.conkey @> (
                  SELECT ARRAY(
                      SELECT a.attnum FROM pg_attribute a
                      WHERE a.attrelid = t.oid
                        AND a.attname IN ('entity_a_id', 'entity_b_id')
                  )
              )
            LIMIT 1;

            IF _constraint_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE fsma.identity_review_queue DROP CONSTRAINT %I',
                    _constraint_name
                );
                RAISE NOTICE 'Dropped legacy UNIQUE constraint %', _constraint_name;
            END IF;

            -- 3. Partial UNIQUE — only "open" rows block duplicates.
            -- Idempotent — drop-then-create keeps reruns safe.
            DROP INDEX IF EXISTS fsma.uq_identity_review_open_pair;
            CREATE UNIQUE INDEX uq_identity_review_open_pair
                ON fsma.identity_review_queue (entity_a_id, entity_b_id)
                WHERE status IN ('pending', 'deferred');
        END $$;
        """
    )


def downgrade() -> None:
    # Downgrade restores the full-table UNIQUE, which will FAIL if
    # multiple rows for the same (a,b) pair already exist (which is
    # the whole point of v068). Operators must manually prune closed
    # rows before downgrading. Kept here for completeness only —
    # roll forward with a corrective migration in production.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'identity_review_queue'
            ) THEN
                RETURN;
            END IF;

            DROP INDEX IF EXISTS fsma.uq_identity_review_open_pair;

            -- Try to restore the unique constraint. Will error if
            -- duplicates exist; operator must clean up first.
            ALTER TABLE fsma.identity_review_queue
                ADD CONSTRAINT identity_review_queue_entity_a_id_entity_b_id_key
                UNIQUE (entity_a_id, entity_b_id);

            ALTER TABLE fsma.identity_review_queue
                DROP COLUMN IF EXISTS previous_review_id;
        END $$;
        """
    )
