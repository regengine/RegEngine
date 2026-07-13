"""v090 -- drop fsma.hash_chain.cte_event_id -> cte_events(id) FK.

Revision ID: 4c5d6e7f8a9b
Revises: 38e02636e340
Create Date: 2026-06-29

#2500: ``fsma.hash_chain.cte_event_id`` carried a
``NOT NULL REFERENCES fsma.cte_events(id)`` foreign key (V002 line 124).
The canonical writer (``canonical_persistence.writer``) chains events by
their ``traceability_events.event_id`` and, on the canonical-only path
(``CanonicalEventStore(dual_write=False)`` — used by webhook ingestion,
the EPCIS path, ``canonical_router``, etc.), never creates a matching
``cte_events`` row. The chain INSERT therefore referenced a
``cte_events`` row that did not exist and Postgres raised a foreign-key
``IntegrityError``, which the webhook handler's outer ``except Exception``
rolled back (wiping the already-committed primary CTE write too) and
re-raised as an HTTP 500. V043's header comment already claimed the chain
"references traceability_events.event_id", but no migration ever made the
schema match that intent.

Decision — DROP the FK rather than repoint it:
  The two writers populate ``hash_chain.cte_event_id`` from DIFFERENT
  tables. The legacy CTE writer (``cte_persistence.writes.store_event``)
  uses its own ``cte_events.id`` (a fresh uuid4, distinct from the
  canonical event_id); the canonical writer uses
  ``traceability_events.event_id``. No single FK target can reference
  both id spaces, so repointing to ``traceability_events`` would simply
  move the IntegrityError onto the legacy-only path. Both writers already
  guard their chain INSERT with an application-level
  ``WHERE EXISTS (... the event row ...)`` (see
  ``cte_persistence/writes.py`` and ``canonical_persistence/writer.py``
  ``_insert_chain_entry``), so the database FK is redundant integrity
  that actively breaks the canonical-only path. We drop it and keep the
  ``NOT NULL`` so the chain still requires an event reference.

  The dropped FK had NO ``ON DELETE CASCADE`` (V002 line 124), so no
  cascade-delete behaviour is lost — the retention DELETE in
  ``services/scheduler/service.py`` never relied on it.

Idempotent: the constraint is dropped only if present. The downgrade
re-adds it ``NOT VALID`` so existing canonical-only chain rows (which by
design have no ``cte_events`` twin) do not block the restore; a
subsequent ``VALIDATE CONSTRAINT`` is intentionally NOT issued because it
would fail on those rows — re-adding the broken FK is a best-effort
rollback only.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "4c5d6e7f8a9b"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "38e02636e340"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The FK was declared inline in V002 with no explicit name, so Postgres
# auto-generated ``hash_chain_cte_event_id_fkey``. Drop by that name but
# defensively discover any FK on (cte_event_id) -> cte_events(id) in case
# a re-create under a different name ever happened.
_UPGRADE_SQL = """
DO $mig$
DECLARE
    fk_name text;
BEGIN
    IF to_regclass('fsma.hash_chain') IS NULL THEN
        RETURN;
    END IF;

    SELECT con.conname INTO fk_name
    FROM pg_constraint con
    JOIN pg_class rel       ON rel.oid = con.conrelid
    JOIN pg_namespace nsp   ON nsp.oid = rel.relnamespace
    JOIN pg_class fref      ON fref.oid = con.confrelid
    JOIN pg_namespace fnsp  ON fnsp.oid = fref.relnamespace
    WHERE con.contype = 'f'
      AND nsp.nspname = 'fsma'
      AND rel.relname = 'hash_chain'
      AND fnsp.nspname = 'fsma'
      AND fref.relname = 'cte_events'
    LIMIT 1;

    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE fsma.hash_chain DROP CONSTRAINT %I', fk_name);
    END IF;
END
$mig$;
"""

# Re-add the FK on downgrade. NOT VALID so the restore does not fail on
# pre-existing canonical-only chain rows that legitimately have no
# cte_events twin.
_DOWNGRADE_SQL = """
DO $mig$
BEGIN
    IF to_regclass('fsma.hash_chain') IS NULL
       OR to_regclass('fsma.cte_events') IS NULL THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel     ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE con.contype = 'f'
          AND nsp.nspname = 'fsma'
          AND rel.relname = 'hash_chain'
          AND con.conname = 'hash_chain_cte_event_id_fkey'
    ) THEN
        ALTER TABLE fsma.hash_chain
            ADD CONSTRAINT hash_chain_cte_event_id_fkey
            FOREIGN KEY (cte_event_id) REFERENCES fsma.cte_events(id)
            NOT VALID;
    END IF;
END
$mig$;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
