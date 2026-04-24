"""v066 — audit_logs append-only trigger (ISO 27001 12.4.2).

Ports the BEFORE UPDATE / BEFORE DELETE trigger from Flyway V30 into
Alembic. Railway runs Alembic only, so V30's triggers never existed in
production — the SHA-256 hash chain was protected by application code
alone. This migration closes the gap using the same authorized-
correction pattern established by V053 for FSMA CTE tables.

Legitimate break-glass access requires an explicit session GUC:

    SET LOCAL audit.allow_break_glass = 'true';
    -- ... emergency correction ...

The GUC name is distinct from V053's ``fsma.allow_mutation`` because the
two grants have fundamentally different semantics: FSMA CTE amendments
happen in the normal course of business (regulator-directed
corrections); audit log modifications are break-glass only and should
trigger a security review whenever the GUC is used.

Downgrade drops the trigger and function. It does NOT restore any
previously grandfathered V30 trigger — that trigger only existed in
Flyway, which Railway does not run.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-04-24
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "d8e9f0a1b2c3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    sql = (_SQL_DIR / "V066__audit_logs_append_only.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.audit_logs') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS audit_append_only ON public.audit_logs;
            END IF;
            DROP FUNCTION IF EXISTS prevent_audit_modification();
        END$$;
        """
    )
