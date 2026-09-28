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

The first test is the generalizable guard: an app role that holds a DML
privilege on an RLS table to which no policy applies for that role is
deny-all for the application, and the denial is silent. It would have caught
this the moment v051 ran against a non-Supabase database.

A role with NO privilege on such a table is not flagged: Postgres raises
``permission denied`` before RLS is consulted, so the lockout is loud. That
is the deliberate closed-grant posture v111 (b71d9e4c2a60) gives the
release-disabled ``fsma.incidents``, ``fsma.exchange_packages`` and
``fsma.organizations`` — also asserted by test_v111_runtime_role_grants.py
(``test_disabled_fsma_surfaces_are_unreachable_by_both_roles``) and required
by the runtime canary in services/shared/database.py. This guard predated
v111 and, never running in CI, flagged those tables until it was taught the
difference; ``test_guard_flags_silent_lockout_but_not_closed_grant`` proves it
still bites on the v051/v056 shape.
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

# One row per (table, app role) where the role can reach the table's rows —
# any table/column DML privilege, directly, via PUBLIC or via membership —
# yet no policy applies to it, so RLS filters every row without an error.
# A policy role oid of 0 means PUBLIC (every role).
_DENY_ALL_TABLES = """
SELECT n.nspname || '.' || c.relname, r.rolname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN pg_roles r
WHERE c.relkind IN ('r', 'p')
  AND c.relrowsecurity
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND r.rolname = ANY (%(app_roles)s)
  AND (
      has_any_column_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE')
      OR has_table_privilege(r.oid, c.oid, 'DELETE')
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_policy p, unnest(p.polroles) AS policy_role
      WHERE p.polrelid = c.oid
        AND (policy_role = 0 OR pg_has_role(r.oid, policy_role, 'MEMBER'))
  )
ORDER BY 1, 2
"""


def _silent_deny_all(conn) -> list[str]:
    rows = conn.execute(_DENY_ALL_TABLES, {"app_roles": list(APP_ROLES)}).fetchall()
    return [f"{table} ({role})" for table, role in rows]


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)
def test_no_rls_table_is_deny_all_for_app_roles():
    """RLS + a grant + no applicable policy = the app silently sees zero rows."""
    with psycopg.connect(DATABASE_URL) as conn:
        offenders = _silent_deny_all(conn)

    assert not offenders, (
        "RLS is enabled on these tables and the listed app role holds privileges "
        "on them, but no policy applies to that role, so the application reads "
        f"zero rows from them with no error raised: {offenders}. Either add a "
        "policy (see v104 for the parent-scoped pattern) or, if the lockout is "
        "deliberate, grant no table privileges instead so failures are loud."
    )


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — live DB required",
)
def test_guard_flags_silent_lockout_but_not_closed_grant():
    """The guard must still bite on the v051/v056 shape (RLS + a grant + no
    policy) while exempting the deliberate closed-grant shape (RLS + no grant
    + no policy). Uses a temp table in a rolled-back transaction."""
    probe = "v104_guard_probe"
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(f"CREATE TEMP TABLE {probe} (id int)")
        conn.execute(f"ALTER TABLE {probe} ENABLE ROW LEVEL SECURITY")

        conn.execute(f"GRANT SELECT ON {probe} TO regengine")
        silent = [o for o in _silent_deny_all(conn) if probe in o]
        assert len(silent) == 1 and silent[0].endswith(f".{probe} (regengine)"), (
            f"RLS + SELECT grant + no policy was not flagged: {silent}"
        )

        conn.execute(f"REVOKE ALL ON {probe} FROM regengine")
        assert not [o for o in _silent_deny_all(conn) if probe in o], (
            "RLS + no grant + no policy is a loud lockout and must not be flagged"
        )

        conn.execute(f"GRANT SELECT ON {probe} TO regengine")
        conn.execute(f"CREATE POLICY {probe}_p ON {probe} FOR SELECT TO regengine USING (true)")
        assert not [o for o in _silent_deny_all(conn) if probe in o], (
            "a policy applying to the granted role must clear the finding"
        )

        conn.rollback()


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
