"""entity_merge_history: alias_snapshot for lossless split — #1207.

Before: ``split_entity`` moved back only the canonical-name alias by
exact-string match. All GLN/GTIN/FDA registration aliases that
originally belonged to the source entity stayed on the target
silently. For FSMA 204 audit reversal this gave a false sense of
rollback — the merge history said "reversed" but the source entity
came back as a crippled shell missing its identifiers.

Fix:

1. Add ``alias_snapshot JSONB`` to ``fsma.entity_merge_history``.
2. ``merge_entities`` now captures the full pre-merge alias set of
   each source entity into the snapshot before re-pointing aliases.
3. ``split_entity`` replays the snapshot — every alias that was on
   the source at merge time goes back to the source on split.
4. Pre-migration merges (``alias_snapshot IS NULL``) cannot be
   safely split; the application raises a loud error rather than
   silently losing data (the pre-v069 behavior).

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-04-18
"""
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent DO block — add the column if it's missing and back-
    # annotate with a COMMENT that spells out the semantics for any
    # operator reading pg_catalog.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'entity_merge_history'
            ) THEN
                RAISE NOTICE 'fsma.entity_merge_history does not exist - skipping #1207 migration';
                RETURN;
            END IF;

            ALTER TABLE fsma.entity_merge_history
                ADD COLUMN IF NOT EXISTS alias_snapshot JSONB;

            COMMENT ON COLUMN fsma.entity_merge_history.alias_snapshot IS
                'Pre-merge alias snapshot keyed by source entity_id — JSON object '
                '{"<uuid>": [{"alias_type":"gln","alias_value":"..."}, ...]}. '
                'Populated by merge_entities so split_entity can replay the exact '
                'alias set back to the source entity. NULL for merges recorded '
                'before v069 — those merges cannot be safely split and the '
                'application raises instead of silently losing aliases (#1207).';
        END $$;
        """
    )


def downgrade() -> None:
    # Dropping the column is destructive — it erases the only record
    # of which aliases belonged to which source at merge time. Kept
    # here for completeness; production roll-back should use a
    # corrective forward-migration instead.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'entity_merge_history'
            ) THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.entity_merge_history
                DROP COLUMN IF EXISTS alias_snapshot;
        END $$;
        """
    )
