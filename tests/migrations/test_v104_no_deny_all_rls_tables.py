"""v104 (7c1f2c8ffe05) — no RLS table may be deny-all for the app roles.

The incident this guards against: v051 and v056 enable and FORCE row level
security on ``public.obligation_cte_rules`` unconditionally, but create its
only policy inside a block guarded on ``pg_roles.rolname = 'authenticated'``
and ``public.memberships`` — both Supabase constructs. On the Railway
least-privilege database that role does not exist, so the guard was false,
the policy was never created, and the table became invisible to the app.

RLS filters rows instead of raising, so nothing failed loudly. The table held
82 rows while every application query returned zero, which silently disabled
the tenant's configured CTE-type subset in compliance scoring
(``services/ingestion/app/compliance_score.py``) and dropped
obligation-driven KDE enforcement entirely in webhook validation
(``services/ingestion/app/webhook_router_v2/validation.py`` — ``if not rows:
return []``). It only became reachable when the #2461 cutover moved the app
off a superuser connection that had been bypassing RLS.

The first test is the generalizable guard: ANY table with RLS enabled and no
policy applicable to ``regengine``/``regengine_sysadmin`` is deny-all for the
application and is almost certainly a bug, not a deliberate lockout. It would
have caught this the moment v051 ran against a non-Supabase database.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.migrations.rls_db import guarded_live_database_url

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = guarded_live_database_url()

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260730_7c1f2c8ffe05_v104_obligation_cte_rules_app_role_policy.py"
)

APP_ROLES = ("regengine", "regengine_sysadmin")

# polroles = '{0}' means the policy applies to PUBLIC (every role).
_DENY_ALL_TABLES = """
SELECT n.nspname || '.' || c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND c.relrowsecurity
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_policy p
      WHERE p.polrelid = c.oid
        AND (
            p.polroles = '{0}'
            OR EXISTS (
                SELECT 1 FROM pg_roles r
                WHERE r.oid = ANY (p.polroles)
                  AND r.rolname = ANY (%(app_roles)s)
            )
        )
  )
ORDER BY 1
"""


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)
def test_no_rls_table_is_deny_all_for_app_roles():
    """RLS + no applicable policy = the app silently sees zero rows."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(_DENY_ALL_TABLES, {"app_roles": list(APP_ROLES)}).fetchall()

    offenders = [r[0] for r in rows]
    assert not offenders, (
        "RLS is enabled on these tables but no policy applies to "
        f"{'/'.join(APP_ROLES)}, so the application reads zero rows from them "
        f"with no error raised: {offenders}. Either add a policy (see v104 for "
        "the parent-scoped pattern) or, if the lockout is deliberate, grant no "
        "table privileges instead so failures are loud."
    )


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)
def test_obligation_cte_rules_is_readable_under_tenant_context():
    """The specific regression: rules are visible to the app for their owning
    tenant, and not visible for a different tenant."""
    with psycopg.connect(DATABASE_URL) as conn:
        owning_tenant = conn.execute(
            """
            SELECT o.tenant_id
            FROM obligation_cte_rules r
            JOIN obligations o ON o.id = r.obligation_id
            GROUP BY o.tenant_id
            ORDER BY count(*) DESC
            LIMIT 1
            """
        ).fetchone()
        if owning_tenant is None:
            pytest.skip("no obligation_cte_rules rows seeded in this database")

        total = conn.execute("SELECT count(*) FROM obligation_cte_rules").fetchone()[0]

        # Act as the application role, with the tenant GUC the app would set.
        conn.execute("SET LOCAL ROLE regengine")
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(owning_tenant[0]),))
        visible = conn.execute("SELECT count(*) FROM obligation_cte_rules").fetchone()[0]

        assert visible > 0, (
            "obligation_cte_rules is still invisible to the regengine role under "
            f"its own tenant context ({total} rows exist) — the v104 policy is "
            "missing or its predicate does not match."
        )

        conn.rollback()


def test_v104_creates_the_policy_unconditionally():
    """The bug was a CONDITIONAL CREATE POLICY that silently never fired, so
    v104 must not reintroduce that shape: the roles are created first and the
    policy statement itself must not sit behind an IF."""
    source = MIGRATION.read_text(encoding="utf-8")

    # The statement is built with an f-string, so match the pieces.
    assert '_POLICY = "obligation_cte_rules_tenant_isolation"' in source
    assert "CREATE POLICY {_POLICY}" in source
    assert "TO regengine, regengine_sysadmin" in source
    # Roles are ensured rather than tested for.
    assert "CREATE ROLE regengine NOLOGIN" in source
    assert "CREATE ROLE regengine_sysadmin NOLOGIN" in source

    create_at = source.index("CREATE POLICY {_POLICY}")
    guard_markers = ("IF EXISTS (SELECT 1 FROM pg_roles", "rolname = 'authenticated'")
    for marker in guard_markers:
        idx = source.find(marker, create_at)
        assert idx == -1, (
            f"v104 guards its CREATE POLICY with {marker!r} — that is exactly the "
            "v051/v056 failure mode this migration exists to fix."
        )
