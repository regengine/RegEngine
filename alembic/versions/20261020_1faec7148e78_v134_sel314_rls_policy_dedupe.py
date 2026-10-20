"""SEL-314: remove duplicate permissive RLS policies.

The Supabase performance advisor reported 46 ``multiple_permissive_policies``
warnings across twelve tables. Eleven ``public.*`` tables carried, next to the
Alembic-managed tenant policy (``TO PUBLIC``, ``public.get_tenant_context()``,
fail-closed), an out-of-band ``authenticated``-only policy that fell back to the
placeholder tenant ``00000000-0000-0000-0000-000000000001`` when
``app.tenant_id`` was unset. That tenant does not exist, no row carries it, and
no client code queries these tables through the Supabase client, so the policy
only widened the permissive set. ``fsma.tenant_portal_links`` carried a
tenant-isolation ``ALL`` policy and a portal-token ``SELECT`` policy that both
reach ``regengine``; they are replaced by one ``SELECT`` policy carrying both
conditions and per-command write policies with the tenant condition. The
tenant policy is dropped under both its v074 name
(``tenant_isolation_portal_links``, still live in production) and its v090
name (``tenant_isolation_tenant_portal_links``, Alembic-built databases).
Predicates use the v096 ``CASE`` form so the token and sysadmin arms are
tested before ``get_tenant_context()``, which raises without ``app.tenant_id``.

Effective access does not change. The upgrade is idempotent so the plain SQL in
``sql/prod-apply/apply_sel314_rls_dedupe.sql`` can run ahead of it.

Revision ID: 1faec7148e78
Revises: c4d8f1a2b6e7
Create Date: 2026-10-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "1faec7148e78"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c4d8f1a2b6e7"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_DUPLICATE_AUTHENTICATED_POLICIES: tuple[tuple[str, str], ...] = (
    ("api_keys", "tenant_isolation_policy"),
    ("compliance_alerts", "compliance_alerts_tenant_isolation"),
    ("compliance_status_log", "compliance_status_log_tenant_isolation"),
    ("invites", "invites_tenant_isolation"),
    ("memberships", "memberships_tenant_isolation"),
    ("review_items", "tenant_isolation_policy"),
    ("roles", "roles_tenant_isolation"),
    ("sessions", "sessions_user_owns"),
    ("tenant_compliance_status", "tenant_compliance_status_isolation"),
    ("tenant_product_profile", "tenant_product_profile_isolation"),
    ("users", "users_own_data"),
)

# CASE form, not OR: public.get_tenant_context() raises when app.tenant_id is
# unset and Postgres does not order OR operands, so the non-raising arms must
# be tested first (v096 docstring). The token arm serves the supplier portal,
# which runs without a tenant GUC; the sysadmin arm serves armed admin sessions.
_SYSADMIN_ARM = """
    (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
    AND current_user = 'regengine_sysadmin'
"""

_TOKEN_ARM = """
    link_token = NULLIF((SELECT current_setting('app.portal_link_token', true)), '')
    AND status = 'active'
    AND expires_at > now()
"""

_TENANT_OR_SYSADMIN = f"""
    CASE
        WHEN {_SYSADMIN_ARM} THEN true
        ELSE tenant_id = (SELECT public.get_tenant_context())
    END
"""

# A portal-token session (app.portal_link_token set, app.tenant_id unset, as
# inside fsma.get_active_portal_link_by_token) sees only the matching row:
# the third arm hides every other row instead of reaching the raising tenant
# arm. Tenant sessions carry an empty token (begin-hook baseline), so they
# skip that arm and stay fail-hard.
_SELECT_PREDICATE = f"""
    CASE
        WHEN {_TOKEN_ARM} THEN true
        WHEN {_SYSADMIN_ARM} THEN true
        WHEN NULLIF((SELECT current_setting('app.portal_link_token', true)), '') IS NOT NULL
            THEN false
        ELSE tenant_id = (SELECT public.get_tenant_context())
    END
"""


def _drop_portal_policies() -> str:
    # v074 named the tenant policy tenant_isolation_portal_links; v090
    # renamed it tenant_isolation_tenant_portal_links on Alembic-built
    # databases. Production still carries the v074 name. Drop both.
    names = (
        "portal_links_token_lookup",
        "tenant_isolation_portal_links",
        "tenant_isolation_tenant_portal_links",
        "portal_links_select",
        "portal_links_insert",
        "portal_links_update",
        "portal_links_delete",
    )
    return "\n".join(f"DROP POLICY IF EXISTS {n} ON fsma.tenant_portal_links;" for n in names)


def upgrade() -> None:
    for table, policy in _DUPLICATE_AUTHENTICATED_POLICIES:
        op.execute(
            f"""
            DO $sel314$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    SET LOCAL lock_timeout = '10s';
                    DROP POLICY IF EXISTS {policy} ON public.{table};
                END IF;
            END
            $sel314$;
            """
        )

    op.execute(
        f"""
        DO $sel314_portal$
        BEGIN
            IF to_regclass('fsma.tenant_portal_links') IS NULL
               OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                RETURN;
            END IF;
            SET LOCAL lock_timeout = '10s';
            {_drop_portal_policies()}
            CREATE POLICY portal_links_select ON fsma.tenant_portal_links
                FOR SELECT
                USING ({_SELECT_PREDICATE});
            CREATE POLICY portal_links_insert ON fsma.tenant_portal_links
                FOR INSERT TO regengine, regengine_sysadmin
                WITH CHECK ({_TENANT_OR_SYSADMIN});
            CREATE POLICY portal_links_update ON fsma.tenant_portal_links
                FOR UPDATE TO regengine, regengine_sysadmin
                USING ({_TENANT_OR_SYSADMIN})
                WITH CHECK ({_TENANT_OR_SYSADMIN});
            CREATE POLICY portal_links_delete ON fsma.tenant_portal_links
                FOR DELETE TO regengine, regengine_sysadmin
                USING ({_TENANT_OR_SYSADMIN});
        END
        $sel314_portal$;
        """
    )


def downgrade() -> None:
    # The eleven dropped ``authenticated`` policies were never created by this
    # chain, so the downgrade does not recreate them; use
    # sql/prod-apply/rollback_sel314_rls_dedupe.sql for an exact restore.
    op.execute(
        f"""
        DO $sel314_portal_down$
        BEGIN
            IF to_regclass('fsma.tenant_portal_links') IS NULL
               OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                RETURN;
            END IF;
            SET LOCAL lock_timeout = '10s';
            {_drop_portal_policies()}
            CREATE POLICY portal_links_token_lookup ON fsma.tenant_portal_links
                FOR SELECT
                USING ({_TOKEN_ARM});
            -- v090's canonical name; the prod-apply rollback restores v074's.
            CREATE POLICY tenant_isolation_tenant_portal_links ON fsma.tenant_portal_links
                FOR ALL TO regengine, regengine_sysadmin
                USING ({_TENANT_OR_SYSADMIN})
                WITH CHECK ({_TENANT_OR_SYSADMIN});
        END
        $sel314_portal_down$;
        """
    )
