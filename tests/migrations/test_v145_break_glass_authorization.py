"""v145 (17fc5f9d1e69): the fsma.allow_mutation break-glass is authorized by role.

Static checks read the migration, v111 and the scheduler source. Behavioural
checks need a real PostgreSQL at alembic head (``REGENGINE_MIGRATION_TEST_DB``
or the CI ``DATABASE_URL``) and run the guarded statements twice: as the
connecting superuser (the GUC-only contract every earlier suite relies on)
and as the runtime role through ``SET LOCAL ROLE regengine``, which is what
a session holding the application credential looks like to the trigger.

1. Superuser + GUC still bypasses every guard (unchanged contract).
2. Runtime role + GUC is refused on fsma.traceability_events and
   fsma.cte_events; the sanctioned allowlisted UPDATE still works for it
   (which also proves the EXECUTE grants on the helper functions).
3. ``fsma.arm_retention_purge`` permits the runtime role to DELETE only that
   tenant's fsma.cte_events rows older than the armed minimum age, inside the
   arming transaction, and nothing else; the floor and the tenant-context
   check raise.
4. Downgrade restores the GUC-only bodies and drops the helpers; upgrade
   re-applies.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = REPO_ROOT / "alembic" / "versions"
MIGRATION = VERSIONS / "20261126_17fc5f9d1e69_v145_break_glass_authorization.py"
V111 = VERSIONS / "20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
SCHEDULER = REPO_ROOT / "services" / "scheduler" / "service.py"
TENANT = "00000000-0000-4000-8000-0000000142aa"
OTHER_TENANT = "00000000-0000-4000-8000-0000000142bb"


def _load_migration():
    spec = importlib.util.spec_from_file_location("v145_break_glass_authorization", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_revision_chain_and_shape() -> None:
    mod = _load_migration()
    assert mod.revision == "17fc5f9d1e69"  # pragma: allowlist secret
    assert mod.down_revision == "d8f3a1c6b902"  # pragma: allowlist secret
    names = {n.name for n in ast.parse(MIGRATION.read_text()).body if isinstance(n, ast.FunctionDef)}
    assert {"upgrade", "downgrade"} <= names


def test_every_guarded_trigger_calls_the_authorization_helper() -> None:
    mod = _load_migration()
    v141 = mod._load_v141()
    for sql in (
        mod._CTE_MUTATION_FN_V145,
        mod._PATCH_MUTATION_FN_V145,
        mod._PATCH_TRUNCATE_FN_V145,
        mod._with_authorization(v141._ROW_FUNCTION_SQL),
        mod._with_authorization(v141._TRUNCATE_FUNCTION_SQL),
    ):
        assert mod.AUTH_CHECK in sql
        assert mod.GUC_CHECK not in sql
    # The v141 allowlist logic is carried over untouched.
    assert "to_jsonb(NEW) - allowlist" in mod._with_authorization(v141._ROW_FUNCTION_SQL)
    assert "IS NOT TRUE" in mod._with_authorization(v141._ROW_FUNCTION_SQL)
    # The retention path is limited to cte_events by name before OLD is read:
    # the permits call sits in its own IF nested under the table-name test,
    # so OLD.ingested_at is never evaluated for a fsma.hash_chain row (which
    # has created_at, not ingested_at).
    assert re.search(
        r"TG_TABLE_NAME = 'cte_events' THEN\s+IF " + re.escape(mod.PERMITS_FN) + r"\(TG_RELID, OLD\.tenant_id, OLD\.ingested_at\) THEN",
        mod._CTE_MUTATION_FN_V145,
    )
    with pytest.raises(RuntimeError):
        mod._with_authorization("BEGIN RETURN NEW; END")


def test_helpers_are_scoped_and_granted_narrowly() -> None:
    mod = _load_migration()
    assert "SECURITY INVOKER" in mod._AUTHORIZED_FN_SQL
    assert "rolsuper" in mod._AUTHORIZED_FN_SQL and "pg_has_role" in mod._AUTHORIZED_FN_SQL
    assert "SECURITY DEFINER" in mod._PERMITS_FN_SQL and "SECURITY DEFINER" in mod._ARM_FN_SQL
    assert "txid_current()" in mod._PERMITS_FN_SQL and "purpose = 'retention_purge'" in mod._PERMITS_FN_SQL
    assert mod.RETENTION_FLOOR in mod._ARM_FN_SQL
    assert "'fsma.cte_events'::regclass" in mod._ARM_FN_SQL
    assert "FORCE ROW LEVEL SECURITY" in mod._ARM_TABLE_SQL
    assert f"DROP CONSTRAINT IF EXISTS {mod.ARM_FLOOR_CHECK}" in mod._ARM_TABLE_SQL
    whole_days = mod.WHOLE_DAYS_CHECK.format(x="min_age")
    assert f"CHECK (min_age >= {mod.RETENTION_FLOOR} AND {whole_days})" in mod._ARM_TABLE_SQL
    # Month components are refused by the arm and the floor is applied to the
    # cutoff itself, so interval ordering and calendar arithmetic cannot disagree.
    assert mod.WHOLE_DAYS_CHECK.format(x="p_min_age") in mod._ARM_FN_SQL
    assert f"LEAST(now() - arm.min_age, now() - {mod.RETENTION_FLOOR})" in mod._PERMITS_FN_SQL
    assert "tenant_id = get_tenant_context()" in mod._ARM_TABLE_SQL
    for fn in (mod.AUTHORIZED_FN, mod.PERMITS_FN, mod.ARM_FN):
        assert f"REVOKE ALL ON FUNCTION {fn}" in mod._AUTHORIZED_FN_SQL + mod._PERMITS_FN_SQL + mod._ARM_FN_SQL
    assert f"DROP TABLE IF EXISTS {mod.ARM_TABLE}" in mod._DROP_SQL


def test_v111_inventory_carries_the_grants_behind_existence_guards() -> None:
    src = V111.read_text()
    block = src[src.index("v145 (17fc5f9d1e69) break-glass authorization") :]
    block = block[: block.index("END LOOP;")]
    for signature in (
        "fsma.break_glass_authorized(oid)",
        "fsma.retention_purge_permits(oid, uuid, timestamptz)",
        "fsma.arm_retention_purge(uuid, interval)",
    ):
        assert f"'{signature}'" in block
    assert "to_regprocedure(function_signature) IS NOT NULL" in block
    assert "TO regengine, regengine_sysadmin" in block


def test_scheduler_arms_the_purge_instead_of_setting_the_guc() -> None:
    src = SCHEDULER.read_text()
    assert "fsma.arm_retention_purge(CAST(:tid AS uuid), CAST(:min_age AS interval))" in src
    assert "set_config('fsma.allow_mutation', 'true', true)" not in src
    assert re.search(r"_CTE_RETENTION_MIN_AGE\s*=\s*\"1095 days\"", src)


# ---------------------------------------------------------------------------
# Behavioural (live PostgreSQL)
# ---------------------------------------------------------------------------


def _alembic(plain_url: str, *args: str) -> None:
    env = {
        "MIGRATIONS_DATABASE_URL": plain_url,
        "DATABASE_URL": plain_url,
        "PATH": subprocess.os.environ["PATH"],
    }
    for k in ("REGENGINE_ENV", "REGENGINE_ALLOW_BASELINE_DOWNGRADE"):
        v = subprocess.os.environ.get(k)
        if v is not None:
            env[k] = v
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        skip_or_fail_db(f"alembic {' '.join(args)} failed (returncode={result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}")


@pytest.fixture(scope="module")
def live() -> Iterator[tuple[str, Engine]]:
    """Real Postgres at alembic head (same contract as test_v141_traceability_events_append_only)."""
    with rls_postgres_or_skip() as (plain_url, engine):
        _alembic(plain_url, "upgrade", "head")
        _reapply(engine)
        with engine.connect() as conn:
            if conn.execute(text("SELECT to_regprocedure('fsma.arm_retention_purge(uuid, interval)')")).scalar() is None:
                skip_or_fail_db("fsma.arm_retention_purge missing at alembic head")
            if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'regengine'")).scalar() is None:
                skip_or_fail_db("runtime role regengine missing; v092/v112/v145 create it")
        yield plain_url, engine


def _reapply(engine: Engine) -> None:
    """Re-run v145's idempotent statements.

    ``alembic upgrade head`` is a no-op on a database already stamped at
    head, and the v141 idempotency test rewrites v141's trigger bodies
    directly, so on a shared database the bodies at head may predate v145.
    """
    mod = _load_migration()
    with engine.begin() as conn:
        for statement in mod.upgrade_statements():
            # text(): the bodies carry RAISE format '%' which the driver
            # would otherwise read as a placeholder.
            conn.execute(text(statement))


def _seed(conn, tenant: str) -> tuple[str, str, str]:
    """One traceability event, one expired and one fresh CTE event for ``tenant``."""
    conn.execute(
        text("INSERT INTO tenants (id, name, slug) VALUES (CAST(:id AS uuid), :name, :slug) ON CONFLICT (id) DO NOTHING"),
        {"id": tenant, "name": "v145 break-glass test", "slug": f"v145-{tenant[-4:]}"},
    )
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO fsma.traceability_events
                (event_id, tenant_id, source_system, event_type, event_timestamp,
                 traceability_lot_code, quantity, unit_of_measure, status)
            VALUES
                (CAST(:eid AS uuid), CAST(:tid AS uuid), 'test', 'shipping', NOW(),
                 'TLC-V145', 10.0, 'case', 'active')
            """
        ),
        {"eid": event_id, "tid": tenant},
    )
    old_id, fresh_id = str(uuid.uuid4()), str(uuid.uuid4())
    for row_id, age in ((old_id, "1100 days"), (fresh_id, "10 days")):
        conn.execute(
            text(
                """
                INSERT INTO fsma.cte_events
                    (id, tenant_id, event_type, traceability_lot_code, product_description,
                     quantity, unit_of_measure, event_timestamp, sha256_hash, chain_hash, ingested_at)
                VALUES
                    (CAST(:id AS uuid), CAST(:tid AS uuid), 'shipping', :lot, 'v145 test', 1.0, 'case',
                     NOW() - CAST(:age AS interval), :sha, :chain, NOW() - CAST(:age AS interval))
                """
            ),
            {"id": row_id, "tid": tenant, "lot": f"LOT-{row_id[:8]}", "age": age, "sha": f"sha-{row_id[:8]}", "chain": f"chain-{row_id[:8]}"},
        )
    return event_id, old_id, fresh_id


def _cleanup(engine: Engine, *tenants: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
        for tenant in tenants:
            conn.execute(text("DELETE FROM fsma.hash_chain WHERE tenant_id = CAST(:tid AS uuid)"), {"tid": tenant})
            conn.execute(text("DELETE FROM fsma.cte_events WHERE tenant_id = CAST(:tid AS uuid)"), {"tid": tenant})
            conn.execute(text("DELETE FROM fsma.traceability_events WHERE tenant_id = CAST(:tid AS uuid)"), {"tid": tenant})
            conn.execute(text("DELETE FROM fsma.break_glass_arms WHERE tenant_id = CAST(:tid AS uuid)"), {"tid": tenant})
            conn.execute(text("DELETE FROM tenants WHERE id = CAST(:tid AS uuid)"), {"tid": tenant})


@pytest.fixture
def seeded(live: tuple[str, Engine]) -> Iterator[tuple[Engine, str, str, str]]:
    _, engine = live
    _cleanup(engine, TENANT, OTHER_TENANT)
    with engine.begin() as conn:
        event_id, old_id, fresh_id = _seed(conn, TENANT)
    try:
        yield engine, event_id, old_id, fresh_id
    finally:
        _cleanup(engine, TENANT, OTHER_TENANT)


def _as_runtime_role(conn, tenant: str = TENANT) -> None:
    conn.execute(text("SET LOCAL ROLE regengine"))
    conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant})


def _rejected(engine: Engine, prepare, sql: str, params: dict, *, message: str) -> DBAPIError:
    with pytest.raises(DBAPIError) as exc:
        with engine.begin() as conn:
            prepare(conn)
            conn.execute(text(sql), params)
    assert message in str(exc.value), str(exc.value)
    return exc.value


def test_superuser_keeps_the_guc_only_contract(seeded) -> None:
    engine, event_id, old_id, _ = seeded
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
        conn.execute(
            text("UPDATE fsma.traceability_events SET quantity = 99 WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        )
        deleted = conn.execute(
            text("DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid) RETURNING id"), {"id": old_id}
        ).fetchall()
        assert len(deleted) == 1
        conn.rollback()


def test_runtime_role_cannot_authorize_itself_with_the_guc(seeded) -> None:
    engine, event_id, old_id, _ = seeded

    def armed_by_guc(conn):
        _as_runtime_role(conn)
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))

    exc = _rejected(
        engine,
        armed_by_guc,
        "UPDATE fsma.traceability_events SET quantity = 99 WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
        message="append-only",
    )
    assert exc.orig.sqlstate == "23514"
    _rejected(
        engine,
        armed_by_guc,
        "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)",
        {"id": old_id},
        message="CTE records are append-only",
    )
    # v111 grants the runtime role no DELETE on the canonical table, so the
    # grant layer refuses before the trigger does; the GUC changes nothing.
    exc = _rejected(
        engine,
        armed_by_guc,
        "DELETE FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
        message="permission denied",
    )
    assert exc.orig.sqlstate == "42501"


def test_runtime_role_sanctioned_update_still_allowed(seeded) -> None:
    """The trigger calls the helper as the invoking role: the EXECUTE grant must hold."""
    engine, event_id, _, _ = seeded
    with engine.begin() as conn:
        _as_runtime_role(conn)
        conn.execute(
            text(
                "UPDATE fsma.traceability_events"
                " SET evaluation_verdict = 'pass', no_verdict_reason = NULL, evaluated_at = NOW()"
                " WHERE event_id = CAST(:eid AS uuid)"
            ),
            {"eid": event_id},
        )
    with engine.connect() as conn:
        verdict = conn.execute(
            text("SELECT evaluation_verdict FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        ).scalar()
    assert verdict == "pass"


def test_arm_retention_purge_permits_only_expired_rows_of_the_tenant(seeded) -> None:
    engine, event_id, old_id, fresh_id = seeded

    def armed(conn):
        _as_runtime_role(conn)
        conn.execute(text("SELECT fsma.arm_retention_purge(CAST(:tid AS uuid), interval '1095 days')"), {"tid": TENANT})

    # A fresh row stays.
    _rejected(engine, armed, "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)", {"id": fresh_id}, message="CTE records are append-only")
    # The arm does not widen into an UPDATE on the canonical table.
    _rejected(
        engine,
        armed,
        "UPDATE fsma.traceability_events SET quantity = 99 WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
        message="append-only",
    )
    # An expired row goes, inside the arming transaction.
    with engine.begin() as conn:
        armed(conn)
        deleted = conn.execute(
            text("DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid) RETURNING id"), {"id": old_id}
        ).fetchall()
        assert [str(r[0]) for r in deleted] == [old_id]
    with engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM fsma.cte_events WHERE tenant_id = CAST(:tid AS uuid)"), {"tid": TENANT}
        ).scalar()
    assert remaining == 1


def test_arm_is_transaction_local(seeded) -> None:
    engine, _, old_id, _ = seeded
    # Arm in one transaction and commit; the arm row persists but names that txid only.
    with engine.begin() as conn:
        _as_runtime_role(conn)
        conn.execute(text("SELECT fsma.arm_retention_purge(CAST(:tid AS uuid))"), {"tid": TENANT})
    _rejected(
        engine,
        _as_runtime_role,
        "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)",
        {"id": old_id},
        message="CTE records are append-only",
    )


def test_arm_floor_and_tenant_context_are_enforced(seeded) -> None:
    engine, _, _, _ = seeded
    exc = _rejected(
        engine,
        _as_runtime_role,
        "SELECT fsma.arm_retention_purge(CAST(:tid AS uuid), interval '100 days')",
        {"tid": TENANT},
        message="24-month retention floor",
    )
    assert exc.orig.sqlstate == "22023"
    exc = _rejected(
        engine,
        _as_runtime_role,
        "SELECT fsma.arm_retention_purge(CAST(:tid AS uuid))",
        {"tid": OTHER_TENANT},
        message="not the current tenant context",
    )
    assert exc.orig.sqlstate == "42501"


def _armed_superuser(conn, tenant: str = TENANT) -> None:
    """A BYPASSRLS session (superuser, no GUC) holding one tenant's retention arm."""
    conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant})
    conn.execute(text("SELECT fsma.arm_retention_purge(CAST(:tid AS uuid), interval '1095 days')"), {"tid": tenant})


def test_arm_does_not_cover_another_tenants_expired_rows(seeded) -> None:
    """RLS does not hide other tenants from a BYPASSRLS session; the trigger must."""
    engine, _, own_old_id, _ = seeded
    with engine.begin() as conn:
        _, other_old_id, _ = _seed(conn, OTHER_TENANT)
    _rejected(
        engine,
        _armed_superuser,
        "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)",
        {"id": other_old_id},
        message="CTE records are append-only",
    )
    # One statement touching both tenants fails as a whole: nothing goes.
    _rejected(
        engine,
        _armed_superuser,
        "DELETE FROM fsma.cte_events WHERE id IN (CAST(:own AS uuid), CAST(:other AS uuid))",
        {"own": own_old_id, "other": other_old_id},
        message="CTE records are append-only",
    )
    with engine.connect() as conn:
        survivors = conn.execute(
            text("SELECT count(*) FROM fsma.cte_events WHERE id IN (CAST(:own AS uuid), CAST(:other AS uuid))"),
            {"own": own_old_id, "other": other_old_id},
        ).scalar()
    assert survivors == 2


def _seed_hash_chain(conn, tenant: str, cte_event_id: str) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO fsma.hash_chain
                (tenant_id, cte_event_id, sequence_num, event_hash, previous_chain_hash, chain_hash, created_at)
            VALUES
                (CAST(:tid AS uuid), CAST(:eid AS uuid), 1, 'v145-event-hash', NULL, 'v145-chain-hash',
                 NOW() - interval '1100 days')
            RETURNING id
            """
        ),
        {"tid": tenant, "eid": cte_event_id},
    ).scalar_one()


def test_retention_arm_does_not_open_hash_chain(seeded) -> None:
    """prevent_cte_mutation also guards fsma.hash_chain, which has no ingested_at.

    The retention branch is nested under the table-name test, so the trigger
    refuses with its append-only error instead of failing on OLD.ingested_at.
    """
    engine, _, old_id, _ = seeded
    with engine.begin() as conn:
        chain_id = _seed_hash_chain(conn, TENANT, old_id)
    exc = _rejected(
        engine,
        _armed_superuser,
        "DELETE FROM fsma.hash_chain WHERE id = :id",
        {"id": chain_id},
        message="append-only",
    )
    assert "ingested_at" not in str(exc)


PROBE_ROLE = "regengine_v145_probe"


@pytest.fixture
def probe_role(seeded) -> Iterator[tuple[Engine, str, str]]:
    """A runtime-like role that holds DML grants on the guarded tables but is
    neither a superuser nor a member of their owner. The application's own
    runtime role has no UPDATE/DELETE/TRUNCATE on these tables, so the grant
    layer would refuse before the trigger runs; this role reaches the trigger.
    """
    engine, _, old_id, _ = seeded

    def drop(conn) -> None:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": PROBE_ROLE}).scalar():
            conn.execute(text(f"DROP OWNED BY {PROBE_ROLE}"))
            conn.execute(text(f"DROP ROLE {PROBE_ROLE}"))

    with engine.begin() as conn:
        drop(conn)
        conn.execute(text(f"CREATE ROLE {PROBE_ROLE} NOLOGIN IN ROLE regengine"))
        conn.execute(
            text(f"GRANT UPDATE, DELETE ON fsma.hash_chain, fsma.correction_patches TO {PROBE_ROLE}")
        )
        conn.execute(text(f"GRANT TRUNCATE ON fsma.correction_patches TO {PROBE_ROLE}"))
        owner_is_member = conn.execute(
            text(
                "SELECT pg_has_role(:r, c.relowner, 'MEMBER') FROM pg_class c"
                " WHERE c.oid = 'fsma.hash_chain'::regclass"
            ),
            {"r": PROBE_ROLE},
        ).scalar()
        if owner_is_member:
            skip_or_fail_db("the runtime role is a member of the fsma table owner; probe cannot isolate the trigger")
        chain_id = _seed_hash_chain(conn, TENANT, old_id)
    try:
        yield engine, str(chain_id), old_id
    finally:
        with engine.begin() as conn:
            drop(conn)


def test_guc_does_not_authorize_a_role_with_dml_grants(probe_role) -> None:
    engine, chain_id, _ = probe_role

    def guc_only(conn):
        conn.execute(text(f"SET LOCAL ROLE {PROBE_ROLE}"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": TENANT})
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))

    _rejected(engine, guc_only, "DELETE FROM fsma.hash_chain WHERE id = :id", {"id": int(chain_id)}, message="append-only")
    _rejected(
        engine,
        guc_only,
        "UPDATE fsma.hash_chain SET chain_hash = 'tampered' WHERE id = :id",
        {"id": int(chain_id)},
        message="append-only",
    )
    # TRUNCATE fires the statement trigger without needing a seeded patch row.
    _rejected(engine, guc_only, "TRUNCATE fsma.correction_patches", {}, message="append-only")


_DIRECT_ARM_INSERT = (
    "INSERT INTO fsma.break_glass_arms (txid, relid, tenant_id, purpose, min_age, armed_by)"
    " VALUES (txid_current(), 'fsma.cte_events'::regclass, CAST(:tid AS uuid), 'retention_purge',"
    " CAST(:min_age AS interval), current_user)"
)

# Each compares as >= 730 days (interval ordering counts a month as 30 days)
# but ``now() - value`` applies calendar months: the first moves the cutoff
# about 12 years into the future, the second makes ~725-day-old rows eligible.
MONTH_BASED_AGES = ("-12000 months 360730 days", "-12 months 1090 days", "25 months")


def test_arm_table_floor_check_holds_for_direct_inserts(seeded) -> None:
    """The arm function refuses a short or month-based min_age; the CHECK covers any other path."""
    engine, _, _, _ = seeded
    for min_age in ("1 day", *MONTH_BASED_AGES):
        exc = _rejected(
            engine,
            lambda conn: None,
            _DIRECT_ARM_INSERT,
            {"tid": TENANT, "min_age": min_age},
            message="break_glass_arms_min_age_floor",
        )
        assert exc.orig.sqlstate == "23514", min_age


@pytest.mark.parametrize("min_age", MONTH_BASED_AGES)
def test_arm_refuses_month_based_intervals(seeded, min_age: str) -> None:
    engine, _, _, _ = seeded
    exc = _rejected(
        engine,
        _as_runtime_role,
        "SELECT fsma.arm_retention_purge(CAST(:tid AS uuid), CAST(:min_age AS interval))",
        {"tid": TENANT, "min_age": min_age},
        message="without a month or year component",
    )
    assert exc.orig.sqlstate == "22023"


def test_trigger_applies_the_floor_to_the_cutoff(seeded) -> None:
    """Defence in depth: even a stored month-based min_age cannot open a fresh row.

    The CHECK is dropped inside the transaction (rolled back with it) to plant
    the arm row the function and the CHECK refuse.
    """
    engine, _, old_id, fresh_id = seeded

    def planted(conn):
        conn.execute(text("ALTER TABLE fsma.break_glass_arms DROP CONSTRAINT break_glass_arms_min_age_floor"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": TENANT})
        conn.execute(text(_DIRECT_ARM_INSERT), {"tid": TENANT, "min_age": MONTH_BASED_AGES[0]})

    _rejected(
        engine,
        planted,
        "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)",
        {"id": fresh_id},
        message="CTE records are append-only",
    )
    # Positive control: the planted arm is live and still lets an expired row go.
    with engine.begin() as conn:
        planted(conn)
        deleted = conn.execute(
            text("DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid) RETURNING id"), {"id": old_id}
        ).fetchall()
        assert [str(r[0]) for r in deleted] == [old_id]
        conn.rollback()
    with engine.connect() as conn:
        restored = conn.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = 'break_glass_arms_min_age_floor'")
        ).scalar()
    assert restored == 1


def test_arm_table_is_owner_only(seeded) -> None:
    engine, _, _, _ = seeded
    exc = _rejected(engine, _as_runtime_role, "SELECT count(*) FROM fsma.break_glass_arms", {}, message="permission denied")
    assert exc.orig.sqlstate == "42501"


def test_downgrade_restores_guc_only_contract_and_upgrade_reapplies(live) -> None:
    plain_url, engine = live
    _cleanup(engine, TENANT)
    with engine.begin() as conn:
        _, old_id, _ = _seed(conn, TENANT)
    try:
        _alembic(plain_url, "downgrade", "d8f3a1c6b902")  # pragma: allowlist secret
        with engine.connect() as conn:
            assert conn.execute(text("SELECT to_regprocedure('fsma.break_glass_authorized(oid)')")).scalar() is None
            assert conn.execute(text("SELECT to_regclass('fsma.break_glass_arms')")).scalar() is None
        # Pre-v145 contract: the runtime role could bypass with the GUC alone.
        with engine.begin() as conn:
            _as_runtime_role(conn)
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
            deleted = conn.execute(
                text("DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid) RETURNING id"), {"id": old_id}
            ).fetchall()
            assert len(deleted) == 1
            conn.rollback()
        _alembic(plain_url, "upgrade", "head")
        _rejected(
            engine,
            lambda conn: (_as_runtime_role(conn), conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))),
            "DELETE FROM fsma.cte_events WHERE id = CAST(:id AS uuid)",
            {"id": old_id},
            message="CTE records are append-only",
        )
    finally:
        _alembic(plain_url, "upgrade", "head")
        _cleanup(engine, TENANT)
