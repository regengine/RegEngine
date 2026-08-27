"""v080 -- fsma.rule_rejections durable rejection audit.

Revision ID: 8a9b0c1d2e3f
Revises: 267d8053ced5
Create Date: 2026-05-12

Adds the ``fsma.rule_rejections`` table — the durable audit trail for
events that the rules engine rejected under
``RULES_ENGINE_ENFORCE in (cte_only, all)``. Written via a separate
short-lived session so the row survives the caller's outer transaction
rollback / HTTPException.

Compliance defensibility: without this row a rejected event left no
DB trace (pre-eval ran with ``persist=False``, then the savepoint was
rolled back or the request raised 422 before any eval row was
committed). Stdout logs alone do not satisfy "we rejected event X at
time Y for reason Z".

Additive only: no existing table is modified.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "8a9b0c1d2e3f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "267d8053ced5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.rule_rejections (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         uuid NOT NULL,
            event_id          uuid NULL,
            rule_id           text NULL,
            rule_version      integer NULL,
            result            text NOT NULL DEFAULT 'rejected'
                              CHECK (result IN ('rejected')),
            reasons           jsonb NOT NULL DEFAULT '[]'::jsonb,
            source            text NOT NULL DEFAULT 'preeval',
            enforcement_mode  text NULL,
            created_at        timestamptz NOT NULL DEFAULT NOW()
        )
        """
    )
    # Idempotency key for retries — (tenant, event, rule, created_at)
    # is unique enough that a webhook redelivery within the same second
    # cannot double-write, but two distinct rejections of two events
    # for the same rule at the same instant remain distinct rows.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_rejections_idem
            ON fsma.rule_rejections (
                tenant_id,
                COALESCE(event_id, '00000000-0000-0000-0000-000000000000'::uuid),
                COALESCE(rule_id, ''),
                created_at
            )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_rejections_tenant_time
            ON fsma.rule_rejections (tenant_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rule_rejections_event
            ON fsma.rule_rejections (event_id)
            WHERE event_id IS NOT NULL
        """
    )

    # Row-level security — match the pattern used by
    # fsma.rule_evaluations in V053 (tenant_isolation_rule_evals).
    op.execute("ALTER TABLE fsma.rule_rejections ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DROP POLICY IF EXISTS tenant_isolation_rule_rejections
            ON fsma.rule_rejections
        """
    )
    op.execute(
        """
        -- #2935: fail-CLOSED. This policy originally coalesced an unset
        -- app.tenant_id to the nil UUID, which makes the predicate match
        -- nil-tenant rows instead of refusing the query -- the exact
        -- fail-open shape #1091 exists to prevent. get_tenant_context()
        -- (available since V056) raises when app.tenant_id is unset.
        -- Existing databases were already repaired by V083; correcting it
        -- here removes the transient window during a fresh `upgrade head`
        -- and stops this file being copied as a template.
        CREATE POLICY tenant_isolation_rule_rejections
            ON fsma.rule_rejections
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY IF EXISTS tenant_isolation_rule_rejections
            ON fsma.rule_rejections
        """
    )
    op.execute("DROP INDEX IF EXISTS fsma.idx_rule_rejections_event")
    op.execute("DROP INDEX IF EXISTS fsma.idx_rule_rejections_tenant_time")
    op.execute("DROP INDEX IF EXISTS fsma.uq_rule_rejections_idem")
    op.execute("DROP TABLE IF EXISTS fsma.rule_rejections")
