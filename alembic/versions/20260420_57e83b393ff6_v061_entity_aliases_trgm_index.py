"""v061: pg_trgm GIN index on fsma.entity_aliases.alias_value (#1208).

Revision ID: 57e83b393ff6
Revises: eaba6af7ae2c
Create Date: 2026-04-20

Forward-port of the quarantined migration
``docs/abandoned_migrations_20260420_incident/20260418_v070_entity_aliases_trgm_index_1208.py``
orphaned by the 2026-04-20 revision-graph incident. Chained to v060.

Why
---
Before this index, ``IdentityResolutionService.find_potential_matches``
pulled every name/trade_name/abbreviation alias for the tenant into
Python and ran Ratcliff/Obershelp (``SequenceMatcher``) pairwise. For
a tenant with 100K aliases this is multi-second per call, and
``_resolve_or_register`` invokes it on every event ingestion -- an
ingestion-throughput hard ceiling.

This migration creates the ``pg_trgm`` extension (if not already
present) and a GIN index on ``fsma.entity_aliases.alias_value`` using
``gin_trgm_ops`` so SQL-side ``similarity()`` / ``%`` pre-filtering
reduces the candidate set from O(N) to O(100) before Python re-scores.

The service code stays defensive: if the extension or the index is
missing for any reason (e.g. running against a stripped-down test
Postgres), it falls back to the pre-#1208 full-scan path.

Prod state (verified 2026-04-20 via Supabase MCP):
  * fsma.entity_aliases -> exists
  * pg_trgm extension   -> already enabled
  * trgm index          -> missing (this migration creates it)
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "57e83b393ff6"
down_revision: Union[str, Sequence[str], None] = "eaba6af7ae2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent DO block -- skip gracefully when the extension is not
    # permitted (e.g. managed PG environments without CREATE EXTENSION)
    # and skip the index create when the table isn't present.
    op.execute(
        """
        DO $$ BEGIN
            -- pg_trgm ships with Postgres but requires a superuser/admin
            -- to enable. Create it if we can; if we can't, the index
            -- below will fail loudly and the service will fall back to
            -- the Python-only path -- which preserves correctness at the
            -- cost of the perf improvement.
            IF NOT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'
            ) THEN
                BEGIN
                    CREATE EXTENSION IF NOT EXISTS pg_trgm;
                EXCEPTION WHEN insufficient_privilege OR OTHERS THEN
                    RAISE NOTICE 'pg_trgm create skipped (insufficient privilege); #1208 fuzzy search will fall back to Python scan';
                    RETURN;
                END;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'entity_aliases'
            ) THEN
                RAISE NOTICE 'fsma.entity_aliases does not exist -- skipping #1208 index';
                RETURN;
            END IF;

            -- Case-insensitive match is authoritative in
            -- ``find_potential_matches`` (search_norm = lower(strip)).
            -- Index the lowered value so ``lower(alias_value) %%`` can
            -- use the GIN; the lowered expression is stable and
            -- deterministic.
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'ix_entity_aliases_alias_value_trgm'
            ) THEN
                CREATE INDEX ix_entity_aliases_alias_value_trgm
                    ON fsma.entity_aliases
                    USING gin (lower(alias_value) gin_trgm_ops);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # The index is cheap to drop; the extension we leave alone since
    # other code paths may start using it.
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'ix_entity_aliases_alias_value_trgm'
            ) THEN
                DROP INDEX fsma.ix_entity_aliases_alias_value_trgm;
            END IF;
        END $$;
        """
    )
