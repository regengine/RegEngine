"""v109 — tenant-bound SECURITY DEFINER team roster reader.

The Team page merge added in this branch reads ``public.users`` from the
ingestion session, but v078's ``user_self_isolation`` policy (FORCE RLS)
only exposes a user row when the ``regengine.user_id`` GUC matches — a GUC
set exclusively on the admin service's request path. Under the enforced
production posture (NOBYPASSRLS app role) the JOIN therefore returned zero
rows with no error: the merge was a silent no-op and the founder's own
account kept rendering as "0 active". (Local dev connects as a superuser,
which is why it appeared to work.)

Standard fix: a SECURITY DEFINER function owned by the migration role.
Definer rights bypass the per-user RLS on ``public.users`` for exactly
this read, while the function itself stays tenant-fail-closed — it serves
only the tenant bound to the session's ``app.tenant_id`` context
(``get_tenant_context()`` raises when unset, v097 fail-hard), so it cannot
be used for cross-tenant reads regardless of caller privileges.

Revision ID: 51701aedee57
Revises: a43b0fb1edd0
Create Date: 2026-08-02
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "51701aedee57"  # pragma: allowlist secret
down_revision = "a43b0fb1edd0"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_team_roster(p_tenant_id uuid)
        RETURNS TABLE (
            user_id       text,
            email         text,
            role_name     text,
            member_status text,
            last_active   text,
            joined_at     text
        )
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = public, fsma
        AS $fn$
        BEGIN
            -- Fail closed: only the session's own tenant may be read.
            -- get_tenant_context() raises when app.tenant_id is unset.
            IF p_tenant_id IS DISTINCT FROM get_tenant_context() THEN
                RAISE EXCEPTION 'tenant context mismatch for team roster';
            END IF;

            RETURN QUERY
            SELECT u.id::text,
                   u.email,
                   COALESCE(r.name, 'Member'),
                   CASE WHEN m.is_active THEN 'active' ELSE 'deactivated' END,
                   u.last_login_at::text,
                   m.created_at::text
            FROM public.memberships m
            JOIN public.users u ON u.id = m.user_id
            LEFT JOIN public.roles r ON r.id = m.role_id
            WHERE m.tenant_id = p_tenant_id;
        END;
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_team_roster(uuid) FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                GRANT EXECUTE ON FUNCTION fsma.get_team_roster(uuid) TO regengine;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_team_roster(uuid)")
