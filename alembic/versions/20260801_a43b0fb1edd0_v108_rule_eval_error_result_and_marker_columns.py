"""v108 — persistable result='error' + the v105 marker columns that never shipped.

Two schema gaps that together defeated the WS-8 evaluation-durability
chain (#2709) whenever a rule evaluator crashed:

1. ``fsma.rule_evaluations.result`` is CHECK-constrained to
   pass/fail/warn/skip, but #1354 changed the engine to emit
   ``result='error'`` for evaluator crashes. Every batch containing an
   error verdict failed the INSERT wholesale (CheckViolation), routing
   ALL rows — healthy ones included — into the salvage path. Extend the
   constraint to include 'error'.

2. The salvage path's re-evaluation marker
   (``RulesEngine._mark_event_evaluation_error``) updates
   ``fsma.traceability_events.evaluation_error`` / ``evaluated_at`` —
   columns referenced by the v105 docstring but never created by any
   migration. The UPDATE raised UndefinedColumn on a connection with no
   savepoint, aborting the outer transaction and taking the v105
   dead-letter INSERT down with it: an evaluator crash lost the entire
   evaluation batch. Create the columns (the engine-side savepoint fix
   lands in the same change set).

Revision ID: a43b0fb1edd0
Revises: c35358cae7d4
Create Date: 2026-08-01
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a43b0fb1edd0"  # pragma: allowlist secret
down_revision = "c35358cae7d4"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE fsma.rule_evaluations
            DROP CONSTRAINT IF EXISTS rule_evaluations_result_check
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.rule_evaluations
            ADD CONSTRAINT rule_evaluations_result_check
            CHECK (result IN ('pass', 'fail', 'warn', 'skip', 'error'))
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.traceability_events
            ADD COLUMN IF NOT EXISTS evaluation_error TEXT,
            ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    # Remove any 'error' rows first or the tightened constraint fails to apply.
    op.execute("DELETE FROM fsma.rule_evaluations WHERE result = 'error'")
    op.execute(
        """
        ALTER TABLE fsma.rule_evaluations
            DROP CONSTRAINT IF EXISTS rule_evaluations_result_check
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.rule_evaluations
            ADD CONSTRAINT rule_evaluations_result_check
            CHECK (result IN ('pass', 'fail', 'warn', 'skip'))
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.traceability_events
            DROP COLUMN IF EXISTS evaluation_error,
            DROP COLUMN IF EXISTS evaluated_at
        """
    )
