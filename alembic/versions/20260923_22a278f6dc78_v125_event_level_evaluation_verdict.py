"""v125 — persist the event-level tri-state rules verdict.

``EvaluationSummary.compliant`` is tri-state (True / False / None) but
only the per-rule rows reach ``fsma.rule_evaluations``. The summary-level
no-verdict context — e.g. a non-FTL event whose only applicable meta-rules
passed (``no_verdict_reason='not_ftl_scoped'``) — was never persisted, so
every SQL consumer (FDA export v2, auditor event list) could only see
"some rows, none of them 'fail'" and stamped the event PASS / compliant.

Two nullable columns on ``fsma.traceability_events`` carry the verdict the
engine actually reached:

- ``evaluation_verdict``  — 'pass' | 'fail' | 'no_verdict'
- ``no_verdict_reason``   — e.g. 'not_ftl_scoped', 'ftl_classification_missing',
                            'no_rules_loaded', 'nothing_evaluated'

Rows evaluated before this migration keep NULL; consumers fall back to the
per-rule rows (which now distinguish 'error' from 'fail') for those.

Revision ID: 22a278f6dc78
Revises: 26d215418784
Create Date: 2026-09-10
"""

from alembic import op

revision = "22a278f6dc78"  # pragma: allowlist secret
down_revision = "26d215418784"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_CHECK = "traceability_events_evaluation_verdict_check"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE fsma.traceability_events
            ADD COLUMN IF NOT EXISTS evaluation_verdict TEXT,
            ADD COLUMN IF NOT EXISTS no_verdict_reason TEXT
        """
    )
    op.execute(f"ALTER TABLE fsma.traceability_events DROP CONSTRAINT IF EXISTS {_CHECK}")
    op.execute(
        f"""
        ALTER TABLE fsma.traceability_events
            ADD CONSTRAINT {_CHECK}
            CHECK (evaluation_verdict IS NULL OR evaluation_verdict IN ('pass', 'fail', 'no_verdict'))
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE fsma.traceability_events DROP CONSTRAINT IF EXISTS {_CHECK}")
    op.execute(
        """
        ALTER TABLE fsma.traceability_events
            DROP COLUMN IF EXISTS evaluation_verdict,
            DROP COLUMN IF EXISTS no_verdict_reason
        """
    )
