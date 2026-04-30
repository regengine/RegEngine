"""v073 — Postgres-backed Inflow Workbench store.

Creates tenant-scoped storage for Inflow Lab preflight scenarios, saved runs,
fix queue items, and commit-gate decisions. These records are evidence-adjacent:
they do not become production traceability evidence, but they preserve the
inputs, validation results, hashes, and gate outcomes that prove why data was
or was not eligible to move forward.

Revision ID: b8c9d0e1f2a3
Revises: 71e79e111c5d
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b8c9d0e1f2a3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "71e79e111c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""


def _enable_rls(table: str, policy: str) -> None:
    op.execute(f"ALTER TABLE fsma.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE fsma.{table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {policy} ON fsma.{table}")
    op.execute(
        f"""
        CREATE POLICY {policy} ON fsma.{table}
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_scenarios (
            scenario_id TEXT NOT NULL,
            tenant_id UUID NOT NULL,
            name TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT 'Custom scenario',
            record_count_label TEXT NOT NULL DEFAULT '0 CTE records',
            csv_text TEXT NOT NULL,
            built_in BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, scenario_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_runs (
            run_id TEXT PRIMARY KEY,
            tenant_id UUID NOT NULL,
            source TEXT NOT NULL DEFAULT 'inflow-lab',
            csv_text TEXT NOT NULL DEFAULT '',
            result_payload JSONB NOT NULL,
            readiness_payload JSONB NOT NULL,
            commit_gate_payload JSONB NOT NULL,
            input_hash TEXT,
            result_hash TEXT,
            saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_inflow_run_input_hash
                CHECK (input_hash IS NULL OR input_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT chk_inflow_run_result_hash
                CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$')
        )
        """
    )
    op.execute("ALTER TABLE fsma.inflow_workbench_runs ADD COLUMN IF NOT EXISTS input_hash TEXT")
    op.execute("ALTER TABLE fsma.inflow_workbench_runs ADD COLUMN IF NOT EXISTS result_hash TEXT")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_fix_items (
            item_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES fsma.inflow_workbench_runs(run_id),
            tenant_id UUID NOT NULL,
            title TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            severity TEXT NOT NULL DEFAULT 'warning',
            impact TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_inflow_fix_status
                CHECK (status IN ('open', 'waiting', 'corrected', 'accepted')),
            CONSTRAINT chk_inflow_fix_severity
                CHECK (severity IN ('blocked', 'warning', 'info'))
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.inflow_workbench_commit_decisions (
            decision_id TEXT PRIMARY KEY,
            run_id TEXT REFERENCES fsma.inflow_workbench_runs(run_id),
            tenant_id UUID NOT NULL,
            mode TEXT NOT NULL,
            allowed BOOLEAN NOT NULL DEFAULT FALSE,
            export_eligible BOOLEAN NOT NULL DEFAULT FALSE,
            reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            next_state TEXT NOT NULL,
            input_hash TEXT,
            result_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_inflow_commit_mode
                CHECK (mode IN ('simulation', 'preflight', 'staging', 'production_evidence')),
            CONSTRAINT chk_inflow_commit_input_hash
                CHECK (input_hash IS NULL OR input_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT chk_inflow_commit_result_hash
                CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$')
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inflow_scenarios_tenant_created "
        "ON fsma.inflow_workbench_scenarios (tenant_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inflow_runs_tenant_saved "
        "ON fsma.inflow_workbench_runs (tenant_id, saved_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inflow_fix_items_tenant_status "
        "ON fsma.inflow_workbench_fix_items (tenant_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inflow_fix_items_run "
        "ON fsma.inflow_workbench_fix_items (run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inflow_commit_decisions_tenant_created "
        "ON fsma.inflow_workbench_commit_decisions (tenant_id, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_inflow_runs_tenant_run "
        "ON fsma.inflow_workbench_runs (tenant_id, run_id)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
        RETURNS TRIGGER AS $fn$
        BEGIN
            RAISE EXCEPTION 'Inflow workbench run and commit-decision records are append-only';
        END;
        $fn$ LANGUAGE plpgsql
        """
    )
    for table, trigger in (
        ("inflow_workbench_runs", "trg_inflow_runs_append_only"),
        ("inflow_workbench_commit_decisions", "trg_inflow_commit_decisions_append_only"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON fsma.{table}")
        op.execute(
            f"""
            CREATE TRIGGER {trigger}
                BEFORE UPDATE OR DELETE ON fsma.{table}
                FOR EACH ROW EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
            """
        )
    for table, trigger in (
        ("inflow_workbench_runs", "trg_inflow_runs_no_truncate"),
        ("inflow_workbench_commit_decisions", "trg_inflow_commit_decisions_no_truncate"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON fsma.{table}")
        op.execute(
            f"""
            CREATE TRIGGER {trigger}
                BEFORE TRUNCATE ON fsma.{table}
                FOR EACH STATEMENT EXECUTE FUNCTION fsma.prevent_inflow_workbench_evidence_update()
            """
        )

    _enable_rls("inflow_workbench_scenarios", "tenant_isolation_inflow_scenarios")
    _enable_rls("inflow_workbench_runs", "tenant_isolation_inflow_runs")
    _enable_rls("inflow_workbench_fix_items", "tenant_isolation_inflow_fix_items")
    _enable_rls("inflow_workbench_commit_decisions", "tenant_isolation_inflow_commit_decisions")


def downgrade() -> None:
    for table, trigger in (
        ("inflow_workbench_commit_decisions", "trg_inflow_commit_decisions_no_truncate"),
        ("inflow_workbench_runs", "trg_inflow_runs_no_truncate"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON fsma.{table}")
    for table, trigger in (
        ("inflow_workbench_commit_decisions", "trg_inflow_commit_decisions_append_only"),
        ("inflow_workbench_runs", "trg_inflow_runs_append_only"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON fsma.{table}")
    op.execute("DROP FUNCTION IF EXISTS fsma.prevent_inflow_workbench_evidence_update()")
    op.execute("DROP TABLE IF EXISTS fsma.inflow_workbench_commit_decisions")
    op.execute("DROP TABLE IF EXISTS fsma.inflow_workbench_fix_items")
    op.execute("DROP TABLE IF EXISTS fsma.inflow_workbench_runs")
    op.execute("DROP TABLE IF EXISTS fsma.inflow_workbench_scenarios")
