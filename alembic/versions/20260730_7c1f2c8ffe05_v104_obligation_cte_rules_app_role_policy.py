"""v104 — restore readability of obligation_cte_rules for the app roles.

Revision ID: 7c1f2c8ffe05
Revises: fcf558aeb1e2
Create Date: 2026-07-30

``public.obligation_cte_rules`` holds 82 rows in production but the app
sees zero of them.

v051 and v056 both run ``ENABLE``/``FORCE ROW LEVEL SECURITY`` on the
table unconditionally, then create its only policy inside a guarded
block::

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
       AND to_regclass('public.memberships') IS NOT NULL THEN
        EXECUTE $exec$CREATE POLICY obligation_cte_rules_select_via_obligation
            ... FOR SELECT TO authenticated USING (... auth.uid() ...)$exec$;
    END IF;

``authenticated`` and ``auth.uid()`` are Supabase constructs. On the
Railway production database that role does not exist, so the guard was
false and the policy was never created — while ENABLE/FORCE applied
anyway. The table has been deny-all ever since, and because RLS filters
rows rather than raising, both consumers degrade silently:

* ``services/ingestion/app/compliance_score.py`` (:143, :251) — the
  tenant's configured subset of CTE types comes back empty, so scoring
  silently falls back to "assume all 7 CTE types" instead of the
  tenant's self-normalized set.
* ``services/ingestion/app/webhook_router_v2/validation.py`` (:98) —
  ``if not rows: return []``, so obligation-driven KDE requirements are
  not enforced on ingested events at all.

Both routers are mounted in the production monolith (server/main.py:581
and :524). The regression became live when the #2461 least-privilege
cutover moved the app off a superuser connection: before that the app
bypassed RLS and the rows were visible, which is why this never showed
up as a failure.

Fix: create the policy the Railway role model actually needs, scoped
through the parent obligation exactly like ``tenant_isolation_obligations``
on ``public.obligations``. Rows in this table have no ``tenant_id`` of
their own — ownership is ``obligation_id -> obligations.tenant_id``.

Deliberately NOT guarded on role existence. The precondition is made
true first (the roles are created if absent, matching the baseline's
own idempotent role bootstrap) so this migration can never silently
skip the policy the way v051/v056 did. A conditional CREATE POLICY is
what caused this incident.

Revision ID: 7c1f2c8ffe05 (random hex, not a credential)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "7c1f2c8ffe05"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "fcf558aeb1e2"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY = "obligation_cte_rules_tenant_isolation"
_LEGACY_POLICY = "obligation_cte_rules_select_via_obligation"

# Mirrors tenant_isolation_obligations on public.obligations: tenant match,
# or the sysadmin break-glass path (GUC + role, both required).
_PREDICATE = """
    EXISTS (
        SELECT 1
        FROM public.obligations o
        WHERE o.id = public.obligation_cte_rules.obligation_id
          AND o.tenant_id = get_tenant_context()
    )
    OR (
        current_setting('regengine.is_sysadmin', true) = 'true'
        AND CURRENT_USER = 'regengine_sysadmin'
    )
"""


def upgrade() -> None:
    # Make the precondition true instead of skipping when it is false.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin NOLOGIN;
            END IF;
        END $$
        """
    )

    # The Supabase-era policy is unreachable on this role model; drop it if a
    # database somewhere did manage to create it.
    op.execute(f"DROP POLICY IF EXISTS {_LEGACY_POLICY} ON public.obligation_cte_rules")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON public.obligation_cte_rules")

    op.execute(
        f"""
        CREATE POLICY {_POLICY}
            ON public.obligation_cte_rules
            FOR ALL
            TO regengine, regengine_sysadmin
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )

    # RLS only filters what the grant already allows; keep the read grant
    # explicit so a fresh database does not depend on inherited defaults.
    op.execute("GRANT SELECT ON public.obligation_cte_rules TO regengine, regengine_sysadmin")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON public.obligation_cte_rules")
