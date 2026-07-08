"""v091 -- unique signoff per (tenant, case, type) on fsma.request_signoffs.

``services/shared/request_workflow/assembly.py`` upserts scope-approval
signoffs with ``ON CONFLICT (tenant_id, request_case_id, signoff_type)
DO NOTHING``, but no migration ever created a matching unique
constraint. Postgres rejects that statement with InvalidColumnReference
("there is no unique or exclusion constraint matching the ON CONFLICT
specification") the first time the code path runs — surfaced by
``tests/test_e2e_tenant_isolation.py::test_09`` in the repo-root CI
suite, and the production schema is identical so the live
package-assembly path fails the same way.

Verified against production before authoring: zero duplicate
``(tenant_id, request_case_id, signoff_type)`` rows exist, so adding
the constraint is safe without a dedup pass.

Also extends ``rule_definitions_category_check`` with the
``ftl_scoping`` and ``operational_quality`` categories.
``shared/rules/seeds.py`` (FSMA_RULE_SEEDS — the canonical rule
provisioning path) ships rules in both categories, but the CHECK
constraint predates them, so ``seed_rule_definitions()`` fails with a
CheckViolation on any schema at alembic head — production included.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a91b3c5d24"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a128f7f95db8"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "uq_request_signoffs_tenant_case_type"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('fsma.request_signoffs') IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                   FROM pg_constraint
                   WHERE conname = '{_CONSTRAINT}'
                     AND conrelid = 'fsma.request_signoffs'::regclass
               ) THEN
                ALTER TABLE fsma.request_signoffs
                    ADD CONSTRAINT {_CONSTRAINT}
                    UNIQUE (tenant_id, request_case_id, signoff_type);
            END IF;
        END $$;
        """
    )


    # Rule categories shipped by shared/rules/seeds.py that the original
    # CHECK predates. Rebuild the constraint with the full set.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.rule_definitions') IS NOT NULL THEN
                ALTER TABLE fsma.rule_definitions
                    DROP CONSTRAINT IF EXISTS rule_definitions_category_check;
                ALTER TABLE fsma.rule_definitions
                    ADD CONSTRAINT rule_definitions_category_check
                    CHECK (category = ANY (ARRAY[
                        'kde_presence'::text,
                        'temporal_ordering'::text,
                        'lot_linkage'::text,
                        'source_reference'::text,
                        'identifier_format'::text,
                        'quantity_consistency'::text,
                        'entity_resolution'::text,
                        'record_completeness'::text,
                        'chain_integrity'::text,
                        'ftl_scoping'::text,
                        'operational_quality'::text
                    ]));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE fsma.request_signoffs DROP CONSTRAINT IF EXISTS {_CONSTRAINT};"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.rule_definitions') IS NOT NULL THEN
                ALTER TABLE fsma.rule_definitions
                    DROP CONSTRAINT IF EXISTS rule_definitions_category_check;
                ALTER TABLE fsma.rule_definitions
                    ADD CONSTRAINT rule_definitions_category_check
                    CHECK (category = ANY (ARRAY[
                        'kde_presence'::text,
                        'temporal_ordering'::text,
                        'lot_linkage'::text,
                        'source_reference'::text,
                        'identifier_format'::text,
                        'quantity_consistency'::text,
                        'entity_resolution'::text,
                        'record_completeness'::text,
                        'chain_integrity'::text
                    ]));
            END IF;
        END $$;
        """
    )
