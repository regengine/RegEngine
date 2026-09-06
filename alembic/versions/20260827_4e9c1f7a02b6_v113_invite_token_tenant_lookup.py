"""v113 — token-keyed pre-tenant lookup for public.invites (#2899).

``POST /auth/accept-invite`` (services/admin/app/invite_routes.py:393) is a
public, unauthenticated route. Its first statement reads ``public.invites`` by
the SHA-256 of the token that was mailed to the invitee — necessarily before
any tenant context exists, because the invite row is what NAMES the tenant.

``public.invites`` is ENABLE + FORCE ROW LEVEL SECURITY with exactly one
policy, v078's ``tenant_isolation_invites``::

    FOR ALL USING (tenant_id = get_tenant_context())

v097 pinned ``get_tenant_context()`` to RAISE when ``app.tenant_id`` is unset,
and ``services/admin/app/database.py:_reset_tenant_guc_on_checkout`` clears
``app.tenant_id`` on every pool checkout. Unlike the ``fsma.*`` policies this
``public.*`` policy has no sysadmin break-glass arm, so under the #2461
least-privilege cutover BOTH ``regengine`` and ``regengine_sysadmin`` raised
``app.tenant_id not set`` on that first read: every invite acceptance, every
tenant, returned 500. Same mechanism as the 2026-07-27 production incident
that v100 fixed for ``public.memberships`` — v100 was scoped to one table, so
``invites`` kept the defect.

Why not v100's shape (``FOR SELECT TO regengine_sysadmin USING (true)``):
that would expose every invite row of every tenant — email addresses, tenant
ids and token hashes — to the whole admin service for the sake of one
pre-auth lookup. The route needs exactly one row, and the caller already
proves entitlement to it by holding the token.

Why not a bare SECURITY DEFINER reader (v109's shape): it would not work.
``public.invites`` is FORCE ROW LEVEL SECURITY, so the table OWNER — which is
the definer — is subject to ``tenant_isolation_invites`` too. v112's docstring
records this exact trap. Definer rights only help when the definer holds
BYPASSRLS, which the #2461 posture deliberately removed.

So the arm is the narrowest thing that can work: a SELECT-only policy that
matches a single row by its token hash, and only while that invite is still
unaccepted, unrevoked and unexpired. The predicate reads
``regengine.invite_token_hash``, a GUC that
``public.get_invite_tenant_by_token_hash()`` sets transaction-locally for the
duration of its own lookup and clears again on both the success and the error
path — so the arm is never live outside that one statement. The function is
SECURITY INVOKER on purpose: authorisation comes from the policy, evaluated
against the real calling role, not from an escalation.

The function returns nothing but ``tenant_id``. The route binds that tenant
context and every subsequent statement — the invite re-read, the membership
insert, the ``accepted_at`` write, the audit row — is authorised by the
ordinary tenant policies, unchanged.

One Postgres detail drives the function's shape. Permissive policies OR
together, but Postgres only avoids evaluating the other arm when it can
constant-fold — which is why v100's ``USING (true)`` works. A non-constant arm
like ours does not fold, so ``tenant_id = get_tenant_context()`` is still
evaluated and still raises. The function therefore also points
``app.tenant_id`` at a freshly generated uuid for the duration of its lookup,
turning that arm from "raises" into "false". The value belongs to no tenant
and is not chosen by the caller, so it cannot make any other row visible; it
is restored (with the token GUC) on both the success and the error path.

``tenant_isolation_invites`` itself is NOT touched. A caller with no tenant
context and no token hash still reads zero rows — it still raises, in fact —
and a caller under tenant B still cannot see tenant A's invites.
``tests/shared/test_invite_token_lookup_live.py`` asserts both of those
directly against a live database, so a future "fix" that widens the base
policy fails the suite.

Roles are created if absent rather than guarding the DDL on their existence:
v104 documents a conditional CREATE POLICY as the cause of a production
incident, and this revision must never silently skip the policy it exists to
add.

Revision ID: 4e9c1f7a02b6
Revises: d8b2056471a7
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e9c1f7a02b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d8b2056471a7"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY = "invites_token_lookup"
_GUC = "regengine.invite_token_hash"
_FN = "public.get_invite_tenant_by_token_hash(text)"


def upgrade() -> None:
    # Make the precondition true instead of skipping when it is false (v104).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;
        END $$;
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.get_invite_tenant_by_token_hash(p_token_hash text)
        RETURNS uuid
        LANGUAGE plpgsql
        VOLATILE
        SET search_path = public, pg_catalog
        AS $fn$
        DECLARE
            v_tenant  uuid;
            v_prev    text := current_setting('app.tenant_id', true);
            v_nowhere text := gen_random_uuid()::text;
        BEGIN
            IF p_token_hash IS NULL OR length(p_token_hash) = 0 THEN
                RETURN NULL;
            END IF;

            -- Two GUCs, both transaction-local, both restored below.
            --
            -- 1. app.tenant_id -> a freshly generated uuid. Permissive
            --    policies OR together, but Postgres only skips the other arm
            --    when it constant-folds (v100 relies on `... OR true`); a
            --    non-constant arm like ours does not fold, so the fail-hard
            --    `tenant_id = get_tenant_context()` arm is still EVALUATED
            --    and raises. Giving it a tenant id that matches nothing turns
            --    that arm from "raises" into "false" without weakening it:
            --    the value is unguessable and belongs to no tenant, so this
            --    cannot make any other row visible. (Verified: without this,
            --    the token arm alone still raises `app.tenant_id not set`.)
            -- 2. the token GUC -> arms invites_token_lookup for one row.
            PERFORM set_config('app.tenant_id', v_nowhere, true);
            PERFORM set_config('{_GUC}', p_token_hash, true);
            BEGIN
                SELECT i.tenant_id
                INTO v_tenant
                FROM public.invites i
                WHERE i.token_hash = p_token_hash
                  AND i.accepted_at IS NULL
                  AND i.revoked_at IS NULL
                  AND i.expires_at > now()
                LIMIT 1;
            EXCEPTION WHEN OTHERS THEN
                PERFORM set_config('{_GUC}', '', true);
                PERFORM set_config('app.tenant_id', COALESCE(v_prev, ''), true);
                RAISE;
            END;
            PERFORM set_config('{_GUC}', '', true);
            PERFORM set_config('app.tenant_id', COALESCE(v_prev, ''), true);

            RETURN v_tenant;
        END;
        $fn$;
        """
    )

    # The narrow arm. SELECT only; one row at a time; only an invite that is
    # still usable. NULLIF(...,'') keeps an unset or cleared GUC from matching
    # a row whose token_hash is somehow empty.
    op.execute(
        f"""
        DROP POLICY IF EXISTS {_POLICY} ON public.invites;
        CREATE POLICY {_POLICY} ON public.invites
            FOR SELECT
            TO regengine_sysadmin
            USING (
                token_hash = NULLIF(current_setting('{_GUC}', true), '')
                AND accepted_at IS NULL
                AND revoked_at IS NULL
                AND expires_at > now()
            );
        """
    )

    op.execute(f"REVOKE ALL ON FUNCTION {_FN} FROM PUBLIC")
    # Invite acceptance belongs to ADMIN_DATABASE_URL; the ordinary runtime
    # has no public.invites privilege in the v111 closed grant inventory.
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FN} TO regengine_sysadmin")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON public.invites")
