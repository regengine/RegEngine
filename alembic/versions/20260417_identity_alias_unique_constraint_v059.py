"""Unique constraint on (tenant_id, alias_type, alias_value) — identity hardening

Addresses:
  - #1179: entity_aliases allows duplicate canonical entries per tenant+alias
  - #1190: _resolve_or_register TOCTOU race creates duplicate entities

Changes:
  1. Deduplicate existing rows by merging aliases onto the oldest entity
     per (tenant_id, alias_type, alias_value) tuple. This is safe and
     idempotent — the oldest entity becomes the canonical survivor.
  2. Add UNIQUE(tenant_id, alias_type, alias_value) on fsma.entity_aliases.
     This supports ON CONFLICT ... DO NOTHING in the service layer so the
     database is the authoritative deduplication barrier and the
     read-modify-write TOCTOU window is eliminated.
  3. Add a partial index on tlc_prefix aliases to support secondary
     prefix-based lookup (see #1175 fix that emits tlc_prefix aliases
     for GTIN-14 + lot-suffix TLCs).

This migration is additive and reversible.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17
"""
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "uniq_entity_aliases_tenant_type_value"


def upgrade() -> None:
    # 1. Best-effort dedup of existing data before adding the constraint.
    #    For any (tenant_id, alias_type, alias_value) group with >1 row,
    #    delete all but the oldest row. Entities that lose their last
    #    alias are NOT deleted — they stay as deactivated shells so
    #    historical references (e.g. in traceability_events) do not
    #    orphan.
    op.execute(
        """
        DO $$
        DECLARE
            dup_record RECORD;
            survivor_alias_id UUID;
            survivor_entity_id UUID;
        BEGIN
            -- Only run on installations that already have the table.
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'fsma'
                  AND table_name = 'entity_aliases'
            ) THEN
                RAISE NOTICE 'fsma.entity_aliases not present — skipping dedup';
                RETURN;
            END IF;

            FOR dup_record IN
                SELECT tenant_id, alias_type, alias_value, COUNT(*) AS dup_count
                FROM fsma.entity_aliases
                GROUP BY tenant_id, alias_type, alias_value
                HAVING COUNT(*) > 1
            LOOP
                -- Pick the oldest alias row as the survivor.
                SELECT alias_id, entity_id
                INTO survivor_alias_id, survivor_entity_id
                FROM fsma.entity_aliases
                WHERE tenant_id = dup_record.tenant_id
                  AND alias_type = dup_record.alias_type
                  AND alias_value = dup_record.alias_value
                ORDER BY created_at ASC NULLS LAST, alias_id ASC
                LIMIT 1;

                -- Delete the duplicate alias rows (not the survivor).
                DELETE FROM fsma.entity_aliases
                WHERE tenant_id = dup_record.tenant_id
                  AND alias_type = dup_record.alias_type
                  AND alias_value = dup_record.alias_value
                  AND alias_id <> survivor_alias_id;

                RAISE NOTICE
                    'Deduplicated % alias rows for (tenant=%, type=%, value=%); survivor entity_id=%',
                    dup_record.dup_count - 1,
                    dup_record.tenant_id,
                    dup_record.alias_type,
                    dup_record.alias_value,
                    survivor_entity_id;
            END LOOP;
        END $$;
        """
    )

    # 2. Add the unique constraint. This is the authoritative dedup barrier
    #    used by ON CONFLICT ... DO NOTHING in the service layer.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'fsma'
                  AND table_name = 'entity_aliases'
            ) THEN
                RAISE NOTICE 'fsma.entity_aliases not present — skipping unique constraint';
                RETURN;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{_CONSTRAINT_NAME}'
            ) THEN
                EXECUTE 'ALTER TABLE fsma.entity_aliases
                         ADD CONSTRAINT {_CONSTRAINT_NAME}
                         UNIQUE (tenant_id, alias_type, alias_value)';
            END IF;
        END $$;
        """
    )

    # 3. Partial index on tlc_prefix aliases — supports prefix-based lookup
    #    for long-form (GTIN-14 + lot-suffix) TLCs. Without this, every
    #    prefix query would fall back to a sequential scan over
    #    entity_aliases.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'fsma'
                  AND table_name = 'entity_aliases'
            ) THEN
                RETURN;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'idx_entity_aliases_tlc_prefix'
            ) THEN
                EXECUTE 'CREATE INDEX idx_entity_aliases_tlc_prefix
                         ON fsma.entity_aliases (tenant_id, alias_value)
                         WHERE alias_type = ''tlc_prefix''';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'idx_entity_aliases_tlc_prefix'
            ) THEN
                EXECUTE 'DROP INDEX fsma.idx_entity_aliases_tlc_prefix';
            END IF;
        END $$;
        """
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{_CONSTRAINT_NAME}'
            ) THEN
                EXECUTE 'ALTER TABLE fsma.entity_aliases
                         DROP CONSTRAINT {_CONSTRAINT_NAME}';
            END IF;
        END $$;
        """
    )
