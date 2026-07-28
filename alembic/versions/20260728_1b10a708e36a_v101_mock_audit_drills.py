"""v101 — persist mock FDA audit drills.

The mock-audit drill simulator (services/ingestion/app/mock_audit.py) stored
drills in an in-process dict, so every restart erased the drill history and no
longitudinal time-to-completion / grade dataset could exist. This table is the
durable store: one row per drill, written at start and updated at submit.

Tenant-scoped with the standard fsma RLS pattern (see v074
supplier_integration_profiles): NOT NULL tenant_id, ENABLE + FORCE ROW LEVEL
SECURITY, and a tenant policy on get_tenant_context() with the sysadmin arm.

Revision ID: 1b10a708e36a
Revises: 3ba0291a69f2
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "1b10a708e36a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "3ba0291a69f2"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.mock_audit_drills (
            drill_id TEXT NOT NULL,
            tenant_id UUID NOT NULL,
            scenario JSONB NOT NULL DEFAULT '{}'::jsonb,
            target_tlc TEXT,
            demo_mode BOOLEAN NOT NULL DEFAULT false,
            status TEXT NOT NULL DEFAULT 'active',
            grade TEXT,
            score INTEGER,
            started_at TIMESTAMPTZ NOT NULL,
            deadline TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, drill_id),
            CONSTRAINT chk_mock_audit_drill_status
                CHECK (status IN ('active', 'completed', 'expired')),
            CONSTRAINT chk_mock_audit_drill_grade
                CHECK (grade IN ('A', 'B', 'C', 'D', 'F')),
            CONSTRAINT chk_mock_audit_drill_score
                CHECK (score >= 0 AND score <= 100)
        )
        """
    )
    # Drill status/submit routes address drills by drill_id alone (RLS scopes
    # the read to the caller's tenant at runtime).
    op.execute("CREATE INDEX IF NOT EXISTS idx_mock_audit_drills_drill_id ON fsma.mock_audit_drills (drill_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mock_audit_drills_tenant_started "
        "ON fsma.mock_audit_drills (tenant_id, started_at DESC)"
    )

    op.execute("ALTER TABLE fsma.mock_audit_drills ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.mock_audit_drills FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_mock_audit_drills ON fsma.mock_audit_drills")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_mock_audit_drills
            ON fsma.mock_audit_drills
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )

    op.execute(
        """
        COMMENT ON TABLE fsma.mock_audit_drills IS
            'Mock FDA audit drill history (21 CFR 1.1455 simulator) — durable per-drill record of scenario, deadline, grade, and time-to-completion.'
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_mock_audit_drills ON fsma.mock_audit_drills")
    op.execute("DROP TABLE IF EXISTS fsma.mock_audit_drills")
