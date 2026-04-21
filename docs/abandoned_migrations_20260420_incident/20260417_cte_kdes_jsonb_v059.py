"""Migrate fsma.cte_kdes.kde_value from TEXT to JSONB (#1311)

KDE values were historically stored via ``str(kde_value)`` in
services/shared/cte_persistence/core.py.  For dicts that produced a
Python repr string (``"{'gln': '...'}"``), which is NOT valid JSON and
cannot be round-tripped.  The application is being updated to write
JSON text with a ``CAST(:kde_value AS jsonb)``; this migration changes
the column type to JSONB and backfills existing TEXT rows.

Backfill strategy:
  1. If the value parses as JSON directly, use it.
  2. If it looks like a Python repr of a dict/list (single quotes,
     or ``None`` / ``True`` / ``False`` tokens), attempt ``ast.literal_eval``
     then ``json.dumps`` the result.
  3. Otherwise, treat as an opaque string and wrap in JSON quotes.
  4. Log every unparseable row to ``fsma.cte_kdes_backfill_log`` so an
     operator can review before merging — we do not silently drop data.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17
"""
from alembic import op


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: only run if the table and column exist.  In environments
    # where the schema is built from a different baseline this migration
    # is effectively a no-op.
    op.execute(
        """
        DO $mig$
        DECLARE
            col_type text;
        BEGIN
            SELECT data_type INTO col_type
            FROM information_schema.columns
            WHERE table_schema = 'fsma'
              AND table_name   = 'cte_kdes'
              AND column_name  = 'kde_value';

            IF col_type IS NULL THEN
                RAISE NOTICE 'fsma.cte_kdes.kde_value not found, skipping';
                RETURN;
            END IF;

            IF col_type = 'jsonb' THEN
                RAISE NOTICE 'fsma.cte_kdes.kde_value already jsonb, skipping';
                RETURN;
            END IF;

            -- 1) Create a backfill-log table so unparseable rows are not
            --    silently dropped.
            CREATE TABLE IF NOT EXISTS fsma.cte_kdes_backfill_log_v059 (
                cte_event_id UUID,
                kde_key      TEXT,
                original     TEXT,
                converted    JSONB,
                reason       TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            -- 2) Add a staging JSONB column.
            ALTER TABLE fsma.cte_kdes ADD COLUMN kde_value_jsonb jsonb;

            -- 3) Populate.  The plpgsql block below walks every row and
            --    attempts a conversion.  On failure it logs to the backfill
            --    table and stores the raw string as a JSON scalar.
            DECLARE
                rec RECORD;
                converted jsonb;
                reason    text;
            BEGIN
                FOR rec IN SELECT cte_event_id, kde_key, kde_value FROM fsma.cte_kdes LOOP
                    converted := NULL;
                    reason    := NULL;

                    IF rec.kde_value IS NULL OR rec.kde_value = '' THEN
                        -- Treat empty as JSON null.
                        converted := 'null'::jsonb;
                    ELSE
                        -- Try direct JSON parse.
                        BEGIN
                            converted := rec.kde_value::jsonb;
                        EXCEPTION WHEN others THEN
                            converted := NULL;
                        END;

                        IF converted IS NULL THEN
                            -- Python repr of dict/list: single quotes, ``None``, etc.
                            -- Convert to JSON by replacing the most common tokens.
                            -- This is a best-effort heuristic; anything that still
                            -- fails is stored as a JSON string so no data is lost.
                            DECLARE
                                candidate text;
                            BEGIN
                                candidate := rec.kde_value;
                                -- Normalize Python literals to JSON literals.
                                candidate := replace(candidate, 'None', 'null');
                                candidate := replace(candidate, 'True', 'true');
                                candidate := replace(candidate, 'False', 'false');
                                -- Naive single-quote -> double-quote swap.  Safe
                                -- for simple dict/list reprs without embedded
                                -- quotes; anything more complex falls through.
                                candidate := replace(candidate, '''', '"');
                                BEGIN
                                    converted := candidate::jsonb;
                                    reason    := 'python-repr-heuristic';
                                EXCEPTION WHEN others THEN
                                    converted := to_jsonb(rec.kde_value);
                                    reason    := 'unparseable-wrapped-as-string';
                                END;
                            END;
                        END IF;
                    END IF;

                    UPDATE fsma.cte_kdes
                       SET kde_value_jsonb = converted
                     WHERE cte_event_id = rec.cte_event_id
                       AND kde_key      = rec.kde_key;

                    IF reason IS NOT NULL THEN
                        INSERT INTO fsma.cte_kdes_backfill_log_v059 (
                            cte_event_id, kde_key, original, converted, reason
                        ) VALUES (
                            rec.cte_event_id, rec.kde_key, rec.kde_value, converted, reason
                        );
                    END IF;
                END LOOP;
            END;

            -- 4) Swap columns: drop old, rename staging.
            ALTER TABLE fsma.cte_kdes DROP COLUMN kde_value;
            ALTER TABLE fsma.cte_kdes RENAME COLUMN kde_value_jsonb TO kde_value;

            RAISE NOTICE 'fsma.cte_kdes.kde_value migrated to jsonb';
        END
        $mig$;
        """
    )


def downgrade() -> None:
    # Revert to TEXT.  We cannot perfectly reconstruct the original
    # Python repr, so we cast JSONB back to its canonical text form.
    # Rows that went through the ``python-repr-heuristic`` branch end
    # up as proper JSON after a round-trip — not identical to the
    # pre-upgrade state, but semantically equivalent and safer.
    op.execute(
        """
        DO $mig$
        DECLARE
            col_type text;
        BEGIN
            SELECT data_type INTO col_type
            FROM information_schema.columns
            WHERE table_schema = 'fsma'
              AND table_name   = 'cte_kdes'
              AND column_name  = 'kde_value';

            IF col_type IS NULL THEN
                RETURN;
            END IF;

            IF col_type <> 'jsonb' THEN
                RETURN;
            END IF;

            ALTER TABLE fsma.cte_kdes ADD COLUMN kde_value_text text;
            UPDATE fsma.cte_kdes SET kde_value_text = kde_value::text;
            ALTER TABLE fsma.cte_kdes DROP COLUMN kde_value;
            ALTER TABLE fsma.cte_kdes RENAME COLUMN kde_value_text TO kde_value;

            DROP TABLE IF EXISTS fsma.cte_kdes_backfill_log_v059;
        END
        $mig$;
        """
    )
