"""v105 — durable dead-letter for rule-evaluation persistence (WS-8, #2709).

The #2705 salvage path retries a failed evaluation batch row-by-row and
marks still-failing rows via ``traceability_events.evaluation_error`` —
but the evaluation RESULT itself (rule id/version, verdict, evidence)
was lost. For audit defensibility the verdict must survive: rows that
fail even the salvage insert are copied here verbatim, and the
``rule_evaluation_deadletter_replay`` scheduler job re-attempts them
into ``fsma.rule_evaluations`` (marking ``replayed_at`` on success).

Follows the v103 evidence-snapshots template exactly: IF-NOT-EXISTS
DDL, ENABLE+FORCE RLS with the fail-closed tenant predicate, role
guards for environments provisioned without the app roles.

Revision ID: 323c945cf68d
Revises: 7c1f2c8ffe05
Create Date: 2026-08-01
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "323c945cf68d"  # pragma: allowlist secret
down_revision = "7c1f2c8ffe05"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "fsma.rule_evaluation_deadletter"
_POLICY = "tenant_isolation_rule_evaluation_deadletter"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            evaluation_id   TEXT NOT NULL,
            event_id        TEXT NOT NULL,
            rule_id         TEXT NOT NULL,
            rule_version    INTEGER NOT NULL,
            result          TEXT NOT NULL,
            why_failed      TEXT,
            evidence        JSONB,
            confidence      DOUBLE PRECISION,
            persist_error   TEXT NOT NULL,
            replay_attempts INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            replayed_at     TIMESTAMPTZ
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_rule_eval_deadletter_pending
            ON {_TABLE} (tenant_id, created_at)
            WHERE replayed_at IS NULL
        """
    )

    # Fail-closed tenant isolation (v095 pattern): FORCE so even the table
    # owner cannot bypass.
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )

    # Client-role lockdown + app-role grants (v092/v098/v103 pattern).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;

            EXECUTE 'REVOKE ALL ON {_TABLE} FROM PUBLIC';
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM authenticated';
            END IF;

            EXECUTE 'GRANT USAGE ON SCHEMA fsma TO regengine, regengine_sysadmin';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON {_TABLE} TO regengine, regengine_sysadmin';
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
