"""RLS coverage regression gate — #1456 / EPIC-B.

After ``alembic upgrade head`` on a fresh PostgreSQL, this test asserts
that every tenant-scoped table in the ``fsma`` schema carries all three
layers of our isolation story:

  1. ``tenant_id`` column exists and is ``NOT NULL``
     (an INSERT that forgets tenant_id cannot slip through).

  2. ``FORCE ROW LEVEL SECURITY`` is enabled
     (the table owner cannot bypass RLS by connecting as owner).

  3. At least one policy references either ``get_tenant_context()`` or
     ``app.tenant_id`` (the policy is actually doing tenant isolation,
     not a placeholder like ``USING (true)``).

This is a lock against the whole class of regressions where a new
``fsma.*`` table ships with ``ENABLE ROW LEVEL SECURITY`` but not
``FORCE``, or with a nullable ``tenant_id`` column, or with RLS enabled
but no policies (the "empty-fortress" bug #1217 was fixed by v067).

TABLES_EXEMPT is the only escape hatch — add a table here only if it
genuinely is not tenant-scoped (e.g. lookup tables, system catalogs)
with a comment explaining why. Keep the list small.

#2828 — the same three checks now also run over the tenant-scoped tables
in the ``public`` schema. The fsma sweep above enumerates
``pg_tables WHERE schemaname = 'fsma'``, so no public-schema table was
ever examined, and ``public.controls`` / ``public.regulations`` sat on
``ENABLE`` without ``FORCE`` from v056 until v111 — meaning the table
owner (which in backend CI is the app role ``regengine`` itself, see
``.github/workflows/backend-ci.yml`` lines 525-526) read and wrote every
tenant's rows with RLS inert. The public half is a curated list rather
than a schema sweep: ``public`` also holds admin/auth, outbox and
migration-infra tables whose isolation stories are deliberately
different (v092 gives some of them a permissive ``USING (true)``
app-role policy, and leaves ``alembic_version`` ENABLE-without-FORCE on
purpose so the migration role cannot lock itself out). Only tables whose
required posture is "FORCE + a real tenant predicate" belong in
PUBLIC_TENANT_SCOPED_TABLES.

Needs a real Postgres. Reuses ``DATABASE_URL`` when set (CI service
container), else spins up a disposable testcontainers Postgres. With
``REGENGINE_REQUIRE_DB=1`` an unavailable Postgres (or a failed
``alembic upgrade head``) FAILS instead of skipping, so the gate can't pass
green by skipping in CI (#2530). Without it the module skips cleanly.

Run via:
    pytest tests/migrations/test_rls_coverage.py -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator, Set

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db

REPO_ROOT = Path(__file__).resolve().parents[2]

# Tables that are intentionally NOT tenant-scoped — regulatory lookup
# data that all tenants share, or system catalogs. Every entry needs a
# comment justifying the exemption and ideally a link to the design doc.
TABLES_EXEMPT: Set[str] = {
    # Tenant/org roots do not carry tenant_id; they define the isolation boundary.
    "organizations",
    # Global rules catalog and its change log are shared regulatory metadata.
    "rule_definitions",
    "rule_audit_log",
    # Migration-internal quarantine log from the v059 cte_kdes JSONB
    # conversion (forward-ported by v078). Written only while v078 runs;
    # no application read/write path, rows carry no tenant_id. v081
    # locks it down instead: FORCE RLS with no policy (deny-all) and
    # REVOKE ALL FROM PUBLIC.
    "cte_kdes_backfill_log_v059",
    # Release-disabled by v111. FORCE RLS has no policy and neither runtime
    # role has table privileges; application WHERE clauses are not treated as
    # an authorization boundary.
    "incidents",
    # Release-disabled by v111 for the same reason. A future exchange router
    # must ship a two-party RLS design before either role receives access.
    "exchange_packages",
    # v121 (DESIGN_email-ingestion.md): one row per inbound email, including
    # emails to an unmapped recipient address that has no tenant yet but must
    # still be auditable, so tenant_id is nullable -- there is no value to
    # compare against a `tenant_id = get_tenant_context()` policy for those
    # rows. Closed-grant model instead (matches the v095 remediation_tokens /
    # v111 incidents / v112 seed_obligations_for_tenant precedent): no direct
    # table privilege is granted to `regengine`, only EXECUTE on the two
    # SECURITY DEFINER functions (fsma.record_inbound_email_audit,
    # fsma.get_inbound_email_audit_by_message_id) that are the sole access
    # path to this table.
    "inbound_email_audit",
}

# #2828: public-schema tables whose required posture is identical to the
# fsma sweep above — NOT NULL tenant_id, FORCE ROW LEVEL SECURITY, and at
# least one policy carrying a real tenant predicate. Curated on purpose;
# see the module docstring for why the public schema is not swept wholesale.
PUBLIC_TENANT_SCOPED_TABLES: Set[str] = {
    # Regulatory control plane. v056 Part 4 gives all three the same
    # tenant_isolation_* policy TO regengine/regengine_sysadmin, but only
    # obligations was ever FORCEd (v051 line 461, v056 line 296); v111
    # closes controls/regulations. Created NOT NULL by the baseline
    # (alembic/sql/V036__fsma_204_regulatory_seed_data.sql).
    "obligations",
    "controls",
    "regulations",
    # Supplier portal slice — v077 lines 294-343 create each with
    # tenant_id UUID NOT NULL and arm ENABLE + FORCE + a
    # get_tenant_context() policy in one block.
    "supplier_facilities",
    "supplier_facility_ftl_categories",
    "supplier_traceability_lots",
    "supplier_cte_events",
    "supplier_funnel_events",
}

# Tenant-scoped public tables that reach their tenant through a parent row
# instead of carrying tenant_id themselves. FORCE and the policy predicate
# still apply; the NOT NULL tenant_id check does not.
PUBLIC_TABLES_SCOPED_VIA_PARENT: Set[str] = {
    # obligation_id -> obligations.tenant_id. FORCE from v051 line 483; the
    # policy that makes it readable is v104's (the incident that established
    # "a conditional CREATE POLICY is what caused this incident").
    "obligation_cte_rules",
}

PUBLIC_RLS_TABLES: Set[str] = PUBLIC_TENANT_SCOPED_TABLES | PUBLIC_TABLES_SCOPED_VIA_PARENT


def _provision_app_roles(database_url: str) -> None:
    """Create local roles/functions referenced by RLS policies."""
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'regengine'
                    ) THEN
                        CREATE ROLE regengine NOLOGIN;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin'
                    ) THEN
                        CREATE ROLE regengine_sysadmin NOLOGIN;
                    END IF;
                END$$;
            """)
            )
            conn.execute(
                text("""
                CREATE OR REPLACE FUNCTION get_tenant_context()
                RETURNS uuid
                LANGUAGE plpgsql
                STABLE
                AS $$
                DECLARE
                    tid text;
                BEGIN
                    tid := NULLIF(current_setting('app.tenant_id', true), '');
                    IF tid IS NULL THEN
                        RAISE EXCEPTION
                            'app.tenant_id not set - tenant context required for RLS'
                            USING ERRCODE = 'insufficient_privilege';
                    END IF;
                    RETURN tid::uuid;
                END;
                $$;
            """)
            )
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def upgraded_engine() -> Iterator[Engine]:
    """Acquire a real Postgres, run ``alembic upgrade head``, yield the engine.

    Reuses ``DATABASE_URL`` (CI service container) when reachable, else a
    disposable testcontainers Postgres; skips locally / FAILS under
    ``REGENGINE_REQUIRE_DB=1`` when no Postgres is available (#2530). A failed
    ``alembic upgrade head`` likewise FAILS under ``REGENGINE_REQUIRE_DB=1`` so a
    broken migration chain can't quietly green the gate.
    """
    with rls_postgres_or_skip() as (plain_url, engine):
        driver_url = engine.url.render_as_string(hide_password=False)
        env = {
            "MIGRATIONS_DATABASE_URL": plain_url,
            "DATABASE_URL": plain_url,
            "PATH": subprocess.os.environ["PATH"],
        }
        # alembic needs these env defaults — reuse what the fresh-DB
        # test sets up.
        for k in (
            "REGENGINE_ENV",
            "REGENGINE_ALLOW_BASELINE_DOWNGRADE",
        ):
            v = subprocess.os.environ.get(k)
            if v is not None:
                env[k] = v

        _provision_app_roles(driver_url)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            skip_or_fail_db(
                f"alembic upgrade head failed (returncode={result.returncode}):"
                f"\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

        yield engine


def _fsma_tables(engine: Engine) -> list[str]:
    """Return all base tables in the ``fsma`` schema, sorted."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'fsma'
                ORDER BY tablename
                """
            )
        ).fetchall()
    return [r[0] for r in rows]


def _table_exists(engine: Engine, table: str, schema: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT to_regclass(:q) IS NOT NULL"),
            {"q": f"{schema}.{table}"},
        ).fetchone()
    return bool(row and row[0])


def _table_has_tenant_id_not_null(engine: Engine, table: str, schema: str = "fsma") -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT is_nullable = 'NO' AS not_null
                FROM information_schema.columns
                WHERE table_schema = :s
                  AND table_name = :t
                  AND column_name = 'tenant_id'
                """
            ),
            {"t": table, "s": schema},
        ).fetchone()
    return bool(row and row[0])


def _table_has_force_rls(engine: Engine, table: str, schema: str = "fsma") -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT c.relrowsecurity AND c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = :s AND c.relname = :t
                """
            ),
            {"t": table, "s": schema},
        ).fetchone()
    return bool(row and row[0])


def _table_has_tenant_policy(engine: Engine, table: str, schema: str = "fsma") -> bool:
    """Return True if at least one policy on the table references
    ``get_tenant_context()`` or ``app.tenant_id`` in its expression —
    i.e., the policy is actually doing tenant isolation rather than
    a placeholder like ``USING (true)``."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT qual, with_check
                FROM pg_policies
                WHERE schemaname = :s AND tablename = :t
                """
            ),
            {"t": table, "s": schema},
        ).fetchall()
    if not rows:
        return False
    for qual, with_check in rows:
        blob = " ".join(x for x in (qual, with_check) if x)
        if "get_tenant_context" in blob or "app.tenant_id" in blob:
            return True
    return False


class TestRLSCoverage_EPIC_B:
    def test_release_disabled_incident_exchange_surfaces_are_deny_all(
        self,
        upgraded_engine: Engine,
    ):
        with upgraded_engine.connect() as conn:
            for table in ("incidents", "exchange_packages"):
                assert _table_has_force_rls(upgraded_engine, table)
                assert conn.execute(
                    text(
                        """
                        SELECT count(*)
                          FROM pg_policies
                         WHERE schemaname = 'fsma' AND tablename = :table
                        """
                    ),
                    {"table": table},
                ).scalar_one() == 0
                for role in ("regengine", "regengine_sysadmin"):
                    assert not conn.execute(
                        text(
                            "SELECT has_table_privilege(:role, :table, "
                            "'SELECT,INSERT,UPDATE,DELETE')"
                        ),
                        {"role": role, "table": f"fsma.{table}"},
                    ).scalar_one()

    def test_every_fsma_table_has_tenant_id_not_null(self, upgraded_engine: Engine):
        tables = _fsma_tables(upgraded_engine)
        assert tables, "no fsma.* tables found after alembic upgrade head"
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_tenant_id_not_null(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables missing NOT NULL tenant_id (add to TABLES_EXEMPT "
            f"with justification if this is intentional): {failures}"
        )

    def test_every_fsma_table_has_force_rls(self, upgraded_engine: Engine):
        tables = _fsma_tables(upgraded_engine)
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_force_rls(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables missing FORCE ROW LEVEL SECURITY. Without FORCE "
            "the table owner role bypasses RLS entirely: "
            f"{failures}"
        )

    def test_every_fsma_table_has_tenant_isolation_policy(self, upgraded_engine: Engine):
        tables = _fsma_tables(upgraded_engine)
        failures = []
        for t in tables:
            if t in TABLES_EXEMPT:
                continue
            if not _table_has_tenant_policy(upgraded_engine, t):
                failures.append(t)
        assert not failures, (
            "fsma.* tables with RLS enabled but no tenant-isolation policy "
            "referencing get_tenant_context() or app.tenant_id. This is "
            "the empty-fortress anti-pattern (#1217). Offenders: "
            f"{failures}"
        )


class TestPublicSchemaRLSCoverage_2828:
    """The same three layers, over the tenant-scoped ``public`` tables.

    ``TestRLSCoverage_EPIC_B`` enumerates ``pg_tables WHERE schemaname =
    'fsma'`` and therefore never looked at the public schema, which is how
    ``public.controls`` and ``public.regulations`` carried ENABLE-without-
    FORCE from v056 all the way to v111 (#2828).
    """

    def test_listed_tables_all_exist(self, upgraded_engine: Engine):
        """A renamed or dropped table must break this gate, not empty it.

        Without this, a typo in PUBLIC_RLS_TABLES would make every
        assertion below vacuously true.
        """
        missing = sorted(t for t in PUBLIC_RLS_TABLES if not _table_exists(upgraded_engine, t, "public"))
        assert not missing, (
            "PUBLIC_RLS_TABLES names public tables that do not exist after "
            f"alembic upgrade head: {missing}. Fix the name or remove the entry "
            "— a stale entry silently hollows out this gate."
        )

    def test_every_public_tenant_scoped_table_has_tenant_id_not_null(self, upgraded_engine: Engine):
        failures = [
            t
            for t in sorted(PUBLIC_TENANT_SCOPED_TABLES)
            if not _table_has_tenant_id_not_null(upgraded_engine, t, schema="public")
        ]
        assert not failures, (
            "public.* tenant-scoped tables missing NOT NULL tenant_id "
            f"(an INSERT that forgets tenant_id would slip through): {failures}"
        )

    def test_every_public_tenant_scoped_table_has_force_rls(self, upgraded_engine: Engine):
        """The #2828 regression lock.

        ENABLE alone leaves the table OWNER outside RLS. Backend CI makes the
        app role ``regengine`` the owner of the database it migrates
        (.github/workflows/backend-ci.yml lines 525-526), so on these tables
        the application role WAS the owner and the tenant predicate never
        applied to it.
        """
        failures = [
            t for t in sorted(PUBLIC_RLS_TABLES) if not _table_has_force_rls(upgraded_engine, t, schema="public")
        ]
        assert not failures, (
            "public.* tables with RLS enabled but not FORCED. Without FORCE the "
            "table owner role bypasses RLS entirely, and the owner is the app "
            f"role under the CI/production layout (#2828): {failures}"
        )

    def test_every_public_tenant_scoped_table_has_tenant_isolation_policy(self, upgraded_engine: Engine):
        failures = [
            t for t in sorted(PUBLIC_RLS_TABLES) if not _table_has_tenant_policy(upgraded_engine, t, schema="public")
        ]
        assert not failures, (
            "public.* tables with RLS enabled but no policy referencing "
            "get_tenant_context() or app.tenant_id — the empty-fortress "
            f"anti-pattern (#1217, and #2880 for the conditional-policy shape): {failures}"
        )
