"""Fail-open policy embedded in an op.execute string, as real revisions write them."""

from alembic import op

revision = "fixture_bad_op_execute"
down_revision = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY tenant_isolation_demo_py ON fsma.demo_events
            FOR ALL
            USING (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', true), ''),
                    '00000000-0000-0000-0000-000000000001'
                )::uuid
            )
            WITH CHECK (
                tenant_id = COALESCE(
                    NULLIF(current_setting('app.tenant_id', true), ''),
                    '00000000-0000-0000-0000-000000000001'
                )::uuid
            )
        """
    )
