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

Downgrade guard (#2827): reverting this revision is destructive. The
tightened CHECK cannot be re-applied while ``result='error'`` rows exist, so
the downgrade DELETEs them — and ``fsma.rule_evaluations`` is described by
``alembic/sql/V044__versioned_rules_engine.sql`` as "the evidentiary record
that a specific check was run". Deleting the error verdicts destroys exactly
the evidence that a check ran and failed to complete, and dropping
``traceability_events.evaluation_error`` / ``evaluated_at`` destroys the
recorded reason. That is unrecoverable FDA evidentiary data, so the
downgrade now requires the same explicit two-variable acknowledgement the
baseline downgrade uses (#1264) rather than running unguarded. Note that
``alembic/env.py:_guard_baseline_downgrade`` only covers ``downgrade base``;
a targeted ``alembic downgrade -1`` reaches this revision without it.
"""

import os

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


def _require_destructive_downgrade_ack() -> None:
    """Refuse to run the destructive downgrade without an explicit opt-in.

    Same shape and same two variables as the baseline downgrade guard
    (``20260324_97588ba8edf3_baseline...py``): ``REGENGINE_ENV`` must name a
    non-production environment AND ``REGENGINE_ALLOW_BASELINE_DOWNGRADE``
    must be ``1``. In production or staging the recovery path is a snapshot
    restore, not a destructive downgrade.

    To override (dev only)::

        REGENGINE_ENV=development \\
        REGENGINE_ALLOW_BASELINE_DOWNGRADE=1 \\
        alembic downgrade a43b0fb1edd0
    """
    env = os.environ.get("REGENGINE_ENV", "unset").lower()
    ack = os.environ.get("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "0")
    if env in {"development", "dev", "test", "ci"} and ack == "1":
        return
    raise RuntimeError(
        "v108 downgrade blocked (#2827). Reverting this revision DELETEs every "
        "fsma.rule_evaluations row with result='error' — the evidentiary record "
        "that a rule check was run (V044) — and drops "
        "fsma.traceability_events.evaluation_error / evaluated_at, which hold "
        "the recorded reason. None of it is recoverable.\n\n"
        "To proceed in a development environment, set BOTH:\n"
        "  REGENGINE_ENV=development\n"
        "  REGENGINE_ALLOW_BASELINE_DOWNGRADE=1\n\n"
        "For production rollback, restore from a database snapshot rather than "
        "running this downgrade.\n\n"
        f"Current: REGENGINE_ENV={env!r}, "
        f"REGENGINE_ALLOW_BASELINE_DOWNGRADE={ack!r}"
    )


def downgrade() -> None:
    _require_destructive_downgrade_ack()
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
