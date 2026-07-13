"""v091 -- request_signoffs unique constraint + rule category CHECK widening.

Two code/schema drifts caught by tests/test_e2e_tenant_isolation.py on an
alembic-head database:

1. ``AssemblyMixin.add_signoff`` records signoffs with ``INSERT ... ON
   CONFLICT (tenant_id, request_case_id, signoff_type) DO NOTHING``
   (services/shared/request_workflow/assembly.py), but neither the V046
   legacy SQL nor the alembic tree ever created a matching unique
   constraint, so every signoff INSERT fails with InvalidColumnReference.
   Duplicate rows are removed first (keeping the earliest signoff) so the
   constraint can be added to databases that accumulated duplicates while
   the constraint was missing.

2. The rule seeds (services/shared/rules/seeds.py) and engine gained the
   ``ftl_scoping`` (#1346) and ``operational_quality`` categories without a
   migration widening V044's ``rule_definitions_category_check``, so
   seeding fails with CheckViolation on a migrated schema.

Revision ID: 127a24ffb54c
Revises: a128f7f95db8
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "127a24ffb54c"
down_revision = "a128f7f95db8"
branch_labels = None
depends_on = None

_CONSTRAINT = "uq_request_signoffs_tenant_case_type"


def upgrade() -> None:
    # Remove duplicates first (keep the earliest signoff of each type), else
    # ADD CONSTRAINT fails on databases that collected duplicates while the
    # constraint was missing.
    op.execute(
        """
        DELETE FROM fsma.request_signoffs a
        USING fsma.request_signoffs b
        WHERE a.tenant_id = b.tenant_id
          AND a.request_case_id = b.request_case_id
          AND a.signoff_type = b.signoff_type
          AND (a.signed_at > b.signed_at
               OR (a.signed_at = b.signed_at AND a.id > b.id))
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{_CONSTRAINT}'
                  AND conrelid = 'fsma.request_signoffs'::regclass
            ) THEN
                ALTER TABLE fsma.request_signoffs
                    ADD CONSTRAINT {_CONSTRAINT}
                    UNIQUE (tenant_id, request_case_id, signoff_type);
            END IF;
        END
        $$;
        """
    )


    # Widen the rule category CHECK to the categories the engine and seeds
    # actually use (ftl_scoping from #1346, operational_quality).
    op.execute(
        """
        ALTER TABLE fsma.rule_definitions
            DROP CONSTRAINT IF EXISTS rule_definitions_category_check;
        ALTER TABLE fsma.rule_definitions
            ADD CONSTRAINT rule_definitions_category_check CHECK (category IN (
                'kde_presence',
                'temporal_ordering',
                'lot_linkage',
                'source_reference',
                'identifier_format',
                'quantity_consistency',
                'entity_resolution',
                'record_completeness',
                'chain_integrity',
                'ftl_scoping',
                'operational_quality'
            ));
        """
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE fsma.request_signoffs DROP CONSTRAINT IF EXISTS {_CONSTRAINT}"
    )
    # Restore the V044 category set. Rows using the widened categories must
    # be retired/edited first or this downgrade will (correctly) fail.
    op.execute(
        """
        ALTER TABLE fsma.rule_definitions
            DROP CONSTRAINT IF EXISTS rule_definitions_category_check;
        ALTER TABLE fsma.rule_definitions
            ADD CONSTRAINT rule_definitions_category_check CHECK (category IN (
                'kde_presence',
                'temporal_ordering',
                'lot_linkage',
                'source_reference',
                'identifier_format',
                'quantity_consistency',
                'entity_resolution',
                'record_completeness',
                'chain_integrity'
            ));
        """
    )
