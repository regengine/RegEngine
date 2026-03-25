# ============================================================================
# COMPLIANCE CONTROL PLANE — V043 through V047
# ============================================================================
# Adds the five workstream tables for the FSMA 204 Compliance Control Plane:
#   V043: Canonical TraceabilityEvent model
#   V044: Versioned Rules Engine
#   V045: Exception & Remediation Queue
#   V046: Request-Response Workflow
#   V047: Identity Resolution
#
# For existing databases, apply after the baseline migration:
#     alembic upgrade head
# ============================================================================

"""compliance control plane — V043 through V047

Revision ID: a1b2c3d4e5f6
Revises: 97588ba8edf3
Create Date: 2026-03-25 08:00:00.000000

"""
from typing import Sequence, Union
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '97588ba8edf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Path to the migration files
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Ordered list of SQL files to apply
_SQL_FILES = [
    "V043__canonical_traceability_events.sql",
    "V044__versioned_rules_engine.sql",
    "V045__exception_remediation_queue.sql",
    "V046__request_response_workflow.sql",
    "V047__identity_resolution.sql",
]


def upgrade() -> None:
    for sql_file in _SQL_FILES:
        sql_path = _MIGRATIONS_DIR / sql_file
        if not sql_path.exists():
            raise FileNotFoundError(
                f"Migration file not found: {sql_path}\n"
                f"Expected in: {_MIGRATIONS_DIR}"
            )
        sql = sql_path.read_text(encoding="utf-8")
        # Strip BEGIN/COMMIT — Alembic manages its own transactions
        sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
        op.execute(sql)


def downgrade() -> None:
    # Drop in reverse order to respect foreign key constraints
    op.execute("DROP TABLE IF EXISTS fsma.identity_review_queue CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.entity_merge_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.entity_aliases CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.canonical_entities CASCADE;")

    op.execute("DROP TABLE IF EXISTS fsma.request_signoffs CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.submission_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.response_packages CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.request_cases CASCADE;")

    op.execute("DROP TABLE IF EXISTS fsma.exception_signoffs CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.exception_attachments CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.exception_comments CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.exception_cases CASCADE;")

    op.execute("DROP TABLE IF EXISTS fsma.rule_audit_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.rule_evaluations CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.rule_definitions CASCADE;")

    op.execute("DROP TABLE IF EXISTS fsma.evidence_attachments CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.traceability_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS fsma.ingestion_runs CASCADE;")
