"""v127 — make the v122 inbound-address lookup work under a NOBYPASSRLS owner.

``fsma.get_tenant_by_inbound_address(text, text)`` (v122) is SECURITY DEFINER
with ``SET row_security = off``, and ``fsma.tenant_inbound_addresses`` is
FORCE ROW LEVEL SECURITY. ``row_security = off`` does not bypass RLS: for a
role without BYPASSRLS it makes any policy-affected query RAISE ("query would
be affected by row-level security policy"). The definer is the migration
owner, which the #2461 posture deliberately keeps NOBYPASSRLS, so on every
database migrated by ``scripts/run-migrations.sh`` the email_ingest webhook
failed on its first tenant lookup. It only ever worked where migrations ran
as a superuser.

Fix: the shape ``fsma.get_active_portal_link_by_token`` (v075) already runs in
production with. The fail-hard tenant policy is scoped ``TO regengine,
regengine_sysadmin`` -- the definer is neither, so inside the function only
v121's GUC-keyed ``inbound_address_lookup`` arm applies, matching the one
address the function set -- and ``row_security`` returns to the default.

Nothing widens for the runtime roles: neither holds any privilege on this
table (v111 closed-grant model), and for both of them the tenant predicate is
unchanged. No ``app.tenant_id`` pinning is introduced (#1091/#2935).

Revision ID: d2e7a7319b33
Revises: c51d4898e0a2
Create Date: 2026-09-28
"""

from alembic import op

revision = "d2e7a7319b33"  # pragma: allowlist secret
down_revision = "c51d4898e0a2"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "fsma.tenant_inbound_addresses"
_POLICY = "tenant_isolation_tenant_inbound_addresses"
_FN = "fsma.get_tenant_by_inbound_address(text, text)"


def _tenant_policy(roles: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
            FOR ALL
            TO {roles}
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )


def upgrade() -> None:
    _tenant_policy("regengine, regengine_sysadmin")
    op.execute(f"ALTER FUNCTION {_FN} RESET row_security")


def downgrade() -> None:
    op.execute(f"ALTER FUNCTION {_FN} SET row_security = off")
    _tenant_policy("PUBLIC")
