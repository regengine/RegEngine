"""v103 -- fsma.compliance_evidence_snapshots (Compliance Snapshots backend).

The Compliance Snapshots UI (frontend/src/app/compliance/snapshots/page.tsx)
ships freeze / attest / verify / refreeze / audit-pack flows whose proxies
forward to ``/v1/compliance/snapshots/{tenant_id}`` on the compliance
service — a route that never existed server-side; only the dev-only
in-memory fallback (frontend/src/lib/dev-compliance-snapshots.ts) answered.
This migration adds the persistence for the real router
(services/compliance/app/snapshots.py).

NOT the same thing as ``fsma.compliance_snapshots`` (v078): that table is a
per-day *scoring* snapshot (snapshot_date, overall_score, ...) with a
UNIQUE(tenant_id, snapshot_date) index. This feature is a point-in-time
*evidence freeze* — many named snapshots per day, each with a content hash
and an attestation trail — hence the separate table.

RLS follows the v095 pattern: tenant_id UUID NOT NULL, ENABLE + FORCE ROW
LEVEL SECURITY, and a fail-closed ``tenant_id = get_tenant_context()``
policy (satisfies tests/migrations/test_rls_coverage.py). Client-role
lockdown mirrors v092/v098: REVOKE from PUBLIC/anon/authenticated, DML
grants to the regengine app roles only.

Originally authored as v101 on 3ba0291a69f2 (v100); PR #2673/#2672 landed
v101 (7c4d9a1f2e8b) and v102 (1b10a708e36a) first, so this reparents onto
the v102 head as v103 — same content, new position in the chain.

Revision ID: fcf558aeb1e2 (random hex, not a credential)
Revises: 1b10a708e36a
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op

revision: str = "fcf558aeb1e2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "1b10a708e36a"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "fsma.compliance_evidence_snapshots"
_POLICY = "tenant_isolation_evidence_snapshots"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id            UUID NOT NULL,
            snapshot_name        TEXT NOT NULL,
            snapshot_reason      TEXT,
            created_by           TEXT NOT NULL,
            trigger_alert_id     TEXT,
            is_auto_created      BOOLEAN NOT NULL DEFAULT FALSE,
            deadline             TIMESTAMPTZ,
            regulatory_citation  TEXT,
            is_attested          BOOLEAN NOT NULL DEFAULT FALSE,
            attested_by          TEXT,
            attested_at          TIMESTAMPTZ,
            attestation_title    TEXT,
            compliance_status    TEXT NOT NULL DEFAULT 'COMPLIANT',
            active_alert_count   INTEGER NOT NULL DEFAULT 0,
            critical_alert_count INTEGER NOT NULL DEFAULT 0,
            content_hash         TEXT NOT NULL,
            snapshot_state       TEXT NOT NULL DEFAULT 'VALID',
            degradation_reason   TEXT,
            captured_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_evidence_snapshots_tenant_captured
            ON {_TABLE} (tenant_id, captured_at DESC)
        """
    )

    # Fail-closed tenant isolation (v095 pattern): uuid = uuid predicate,
    # FORCE so even the table owner cannot bypass.
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

    # Client-role lockdown + app-role grants (v092/v098 pattern). Role
    # creation is guarded for environments provisioned without them.
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
            EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} '
                 || 'TO regengine, regengine_sysadmin';
        END $$;
        """
    )


def downgrade() -> None:
    # This migration is the table's only owner and the feature is new —
    # a real drop is the correct downgrade (no pre-existing data to keep).
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
