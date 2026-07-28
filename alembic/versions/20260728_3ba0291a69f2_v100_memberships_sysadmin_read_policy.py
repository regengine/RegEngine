"""v100 — sysadmin SELECT arm on public.memberships for pre-tenant auth lookup.

The #2461 least-privilege cutover broke every authenticated dashboard route:
``GET /auth/me`` (services/admin/app/auth_routes.py) and ``get_current_user``
(services/admin/app/dependencies.py) both derive the session's tenant by
selecting the user's active rows from ``public.memberships`` BEFORE any
tenant context exists — that query is what determines the tenant. The table
is ENABLE + FORCE RLS with a single permissive policy
``tenant_isolation_memberships`` (``tenant_id = get_tenant_context()``), and
v097's fail-hard ``get_tenant_context()`` raises when ``app.tenant_id`` is
unset. Under the old BYPASSRLS role the policy never evaluated; under the
cutover both ``regengine`` and ``regengine_sysadmin`` are NOBYPASSRLS, so the
auth bootstrap raised ``app.tenant_id not set`` and every route behind it
returned 500 (prod incident 2026-07-27, dashboard unusable).

Fix: a SELECT-only permissive policy TO ``regengine_sysadmin`` — the admin
service's engine, which is the only code path that performs the pre-tenant
identity lookup. Permissive policies OR together and the planner folds
``... OR true``, so the fail-hard tenant arm is not evaluated for sysadmin
SELECTs (validated live against prod PG 18 with a forced-RLS probe table).
Tenant isolation for the app role (``regengine``) is unchanged, as are
INSERT/UPDATE/DELETE for every role.

Role-guarded like v095's grants: local/CI databases without the
``regengine_sysadmin`` role converge to a no-op.

Revision ID: 3ba0291a69f2
Revises: 8b2f4e6a9c31
Create Date: 2026-07-28
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3ba0291a69f2"
down_revision = "8b2f4e6a9c31"
branch_labels = None
depends_on = None

POLICY = "memberships_sysadmin_read"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                DROP POLICY IF EXISTS {POLICY} ON public.memberships;
                CREATE POLICY {POLICY} ON public.memberships
                    FOR SELECT TO regengine_sysadmin USING (true);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON public.memberships;")
