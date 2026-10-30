"""v141 — ``fsma.traceability_events`` mutation policy (S4).

Static checks run everywhere. Behavioural checks run against a real
PostgreSQL at alembic head (``REGENGINE_MIGRATION_TEST_DB`` or a
testcontainers Postgres, same contract as ``test_client_role_lockdown_v092``)
and verify the sanctioned mutation surface end to end:

1. Allowlisted column UPDATEs (verdict markers, amended_at) succeed.
2. ``status`` may move ``active -> superseded`` and nothing else.
3. A payload column UPDATE, a DELETE and a TRUNCATE raise ``check_violation``.
4. ``SET LOCAL fsma.allow_mutation = 'true'`` lets UPDATE and DELETE through.
5. Re-applying the upgrade SQL is idempotent; the downgrade removes both
   triggers and both functions; re-upgrading restores them.
"""

from __future__ import annotations

import ast
import importlib.util
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
MIGRATION = REPO_ROOT / "alembic" / "versions" / "20261028_08c7cf36ddbe_v141_traceability_events_append_only.py"

TENANT = "00000000-0000-4000-8000-0000000138aa"


def _load_migration():
    spec = importlib.util.spec_from_file_location("v141_traceability_events_append_only", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------


def test_revision_chain_and_shape() -> None:
    mod = _load_migration()
    assert mod.revision == "08c7cf36ddbe"  # pragma: allowlist secret
    assert mod.down_revision == "b8c1e4f2a901"  # pragma: allowlist secret
    tree = ast.parse(MIGRATION.read_text())
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"upgrade", "downgrade"} <= names


def test_trigger_sql_covers_update_delete_and_truncate() -> None:
    mod = _load_migration()
    assert "BEFORE UPDATE OR DELETE ON fsma.traceability_events" in mod._TRIGGERS_SQL
    assert "BEFORE TRUNCATE ON fsma.traceability_events" in mod._TRIGGERS_SQL
    assert "FOR EACH STATEMENT" in mod._TRIGGERS_SQL
    assert "to_regclass('fsma.traceability_events')" in mod._TRIGGERS_SQL
    assert "DROP TRIGGER IF EXISTS" in mod._TRIGGERS_SQL
    assert "ERRCODE = 'check_violation'" in mod._ROW_FUNCTION_SQL
    assert "current_setting('fsma.allow_mutation', true)" in mod._ROW_FUNCTION_SQL
    assert "current_setting('fsma.allow_mutation', true)" in mod._TRUNCATE_FUNCTION_SQL
    # Null-safe transition guard (the Supabase twin leaves status nullable).
    assert "(OLD.status = 'active' AND NEW.status = 'superseded') IS NOT TRUE" in mod._ROW_FUNCTION_SQL


def test_allowlist_matches_the_production_writers() -> None:
    """The three sanctioned writers only touch these columns."""
    mod = _load_migration()
    assert set(mod.ALLOWLIST) == {
        "status",
        "amended_at",
        "evaluation_verdict",
        "no_verdict_reason",
        "evaluation_error",
        "evaluated_at",
    }
    writer = (REPO_ROOT / "services/shared/canonical_persistence/writer.py").read_text()
    assert "SET status = 'superseded', amended_at = NOW()" in writer
    engine = (REPO_ROOT / "services/shared/rules/engine.py").read_text()
    assert "SET evaluation_verdict = :verdict" in engine
    assert "SET evaluation_error = :error_message" in engine


def test_downgrade_removes_everything_it_created() -> None:
    mod = _load_migration()
    for name in (mod.ROW_TRIGGER, mod.TRUNCATE_TRIGGER):
        assert f"DROP TRIGGER IF EXISTS {name}" in mod._DOWNGRADE_SQL
    for fn in (mod.ROW_FUNCTION, mod.TRUNCATE_FUNCTION):
        assert f"DROP FUNCTION IF EXISTS {fn}()" in mod._DOWNGRADE_SQL


# ---------------------------------------------------------------------------
# Behavioural (live PostgreSQL)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def upgraded_engine() -> Iterator[Engine]:
    """Real Postgres at alembic head (same contract as test_client_role_lockdown_v092)."""
    with rls_postgres_or_skip() as (plain_url, engine):
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
        with engine.connect() as conn:
            if conn.execute(text("SELECT to_regclass('fsma.traceability_events')")).scalar() is None:
                skip_or_fail_db("fsma.traceability_events missing at alembic head")
        yield engine


def _insert_event(conn, *, status: str = "active") -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO fsma.traceability_events
                (event_id, tenant_id, source_system, event_type, event_timestamp,
                 traceability_lot_code, quantity, unit_of_measure, status)
            VALUES
                (CAST(:eid AS uuid), CAST(:tid AS uuid), 'test', 'shipping', NOW(),
                 'TLC-V138', 10.0, 'case', :status)
            """
        ),
        {"eid": event_id, "tid": TENANT, "status": status},
    )
    return event_id


@pytest.fixture
def seeded(upgraded_engine: Engine) -> Iterator[tuple[Engine, str]]:
    with upgraded_engine.begin() as conn:
        event_id = _insert_event(conn)
    try:
        yield upgraded_engine, event_id
    finally:
        with upgraded_engine.begin() as conn:
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
            conn.execute(
                text("DELETE FROM fsma.traceability_events WHERE tenant_id = CAST(:tid AS uuid)"),
                {"tid": TENANT},
            )


def _expect_rejected(engine: Engine, sql: str, params: dict) -> None:
    with pytest.raises(DBAPIError) as exc:
        with engine.begin() as conn:
            conn.execute(text(sql), params)
    message = str(exc.value)
    assert "append-only" in message or "status may only move" in message, message
    # psycopg 3 (rls_db forces it) exposes the server SQLSTATE directly;
    # no fallback, so a driver that lacks it fails loudly.
    assert exc.value.orig.sqlstate == "23514", message  # check_violation


def test_triggers_installed_at_head(upgraded_engine: Engine) -> None:
    with upgraded_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'fsma.traceability_events'::regclass AND NOT tgisinternal
                """
            )
        ).scalars()
        names = set(rows)
    assert {"traceability_events_mutation_policy", "traceability_events_no_truncate"} <= names


def test_verdict_marker_update_is_allowed(seeded) -> None:
    engine, event_id = seeded
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE fsma.traceability_events"
                " SET evaluation_verdict = 'pass', no_verdict_reason = NULL, evaluated_at = NOW()"
                " WHERE tenant_id = CAST(:tid AS uuid) AND event_id = CAST(:eid AS uuid)"
            ),
            {"tid": TENANT, "eid": event_id},
        )
        conn.execute(
            text(
                "UPDATE fsma.traceability_events SET evaluation_error = 'boom', evaluated_at = NOW()"
                " WHERE tenant_id = CAST(:tid AS uuid) AND event_id = CAST(:eid AS uuid)"
            ),
            {"tid": TENANT, "eid": event_id},
        )
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT evaluation_verdict, evaluation_error FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        ).one()
    assert tuple(row) == ("pass", "boom")


def test_active_to_superseded_is_allowed(seeded) -> None:
    engine, event_id = seeded
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE fsma.traceability_events SET status = 'superseded', amended_at = NOW()"
                " WHERE event_id = CAST(:eid AS uuid) AND tenant_id = CAST(:tid AS uuid) AND status = 'active'"
                " RETURNING event_id"
            ),
            {"tid": TENANT, "eid": event_id},
        )
        assert result.fetchone() is not None


def test_superseded_cannot_go_back_to_active(seeded) -> None:
    engine, event_id = seeded
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE fsma.traceability_events SET status = 'superseded' WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        )
    _expect_rejected(
        engine,
        "UPDATE fsma.traceability_events SET status = 'active' WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


@pytest.mark.parametrize("target", ["rejected", "draft"])
def test_other_status_transitions_rejected(seeded, target) -> None:
    engine, event_id = seeded
    _expect_rejected(
        engine,
        f"UPDATE fsma.traceability_events SET status = '{target}' WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


def test_null_status_rejected_on_nullable_catalogs(seeded) -> None:
    """A NULL ``status`` must not slip past the transition guard.

    The alembic catalog declares ``status NOT NULL``, but the Supabase twin
    (``supabase/migrations/20260403234813_*.sql``) leaves it nullable, and
    ``NOT (OLD.status = 'active' AND NEW.status = 'superseded')`` is NULL,
    not TRUE, when either side is NULL. Both transactions below drop the
    NOT NULL constraint only inside a transaction that the rejection rolls
    back, so the catalog is unchanged afterwards.
    """
    engine, event_id = seeded
    drop_not_null = text("ALTER TABLE fsma.traceability_events ALTER COLUMN status DROP NOT NULL")
    set_status = text("UPDATE fsma.traceability_events SET status = :status WHERE event_id = CAST(:eid AS uuid)")

    # active -> NULL
    with pytest.raises(DBAPIError) as exc:
        with engine.begin() as conn:
            conn.execute(drop_not_null)
            conn.execute(set_status, {"status": None, "eid": event_id})
    assert "status may only move" in str(exc.value), str(exc.value)
    assert exc.value.orig.sqlstate == "23514"

    # NULL -> active (the row got its NULL through break-glass)
    with pytest.raises(DBAPIError) as exc:
        with engine.begin() as conn:
            conn.execute(drop_not_null)
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
            conn.execute(set_status, {"status": None, "eid": event_id})
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'false'"))
            conn.execute(set_status, {"status": "active", "eid": event_id})
    assert "status may only move" in str(exc.value), str(exc.value)
    assert exc.value.orig.sqlstate == "23514"

    with engine.connect() as conn:
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns"
                " WHERE table_schema = 'fsma' AND table_name = 'traceability_events' AND column_name = 'status'"
            )
        ).scalar()
    assert nullable == "NO"


@pytest.mark.parametrize(
    "assignment",
    [
        "quantity = quantity + 0.25",
        "event_timestamp = event_timestamp + interval '1 minute'",
        "traceability_lot_code = 'TLC-MUTATED'",
        "kdes = '{\"x\": 1}'::jsonb",
        "sha256_hash = repeat('a', 64)",
        "tenant_id = '00000000-0000-4000-8000-0000000138bb'",
    ],
)
def test_payload_column_update_rejected(seeded, assignment) -> None:
    engine, event_id = seeded
    _expect_rejected(
        engine,
        f"UPDATE fsma.traceability_events SET {assignment} WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


def test_allowlisted_and_payload_change_in_one_statement_rejected(seeded) -> None:
    """Hiding a payload change behind a sanctioned marker update does not work."""
    engine, event_id = seeded
    _expect_rejected(
        engine,
        "UPDATE fsma.traceability_events SET evaluated_at = NOW(), quantity = 1.0 WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


def test_delete_rejected(seeded) -> None:
    engine, event_id = seeded
    _expect_rejected(
        engine,
        "DELETE FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


def test_truncate_rejected(upgraded_engine: Engine) -> None:
    # CASCADE so PostgreSQL gets past its own FK check (evidence_attachments
    # references this table) and reaches the BEFORE TRUNCATE trigger, which
    # raises before any table loses a row. The transaction rolls back.
    with pytest.raises(DBAPIError) as exc:
        with upgraded_engine.begin() as conn:
            conn.execute(text("TRUNCATE fsma.traceability_events CASCADE"))
    assert "TRUNCATE rejected" in str(exc.value)


def test_break_glass_allows_update_and_delete(seeded) -> None:
    engine, event_id = seeded
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
        conn.execute(
            text("UPDATE fsma.traceability_events SET quantity = 99.0 WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT quantity FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        ).scalar() == 99.0
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
        conn.execute(
            text("DELETE FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM fsma.traceability_events WHERE event_id = CAST(:eid AS uuid)"),
            {"eid": event_id},
        ).scalar() == 0


def test_break_glass_is_transaction_local(seeded) -> None:
    """SET LOCAL does not leak: the next transaction is protected again."""
    engine, event_id = seeded
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
        conn.execute(text("SELECT 1"))
    _expect_rejected(
        engine,
        "UPDATE fsma.traceability_events SET quantity = 1.0 WHERE event_id = CAST(:eid AS uuid)",
        {"eid": event_id},
    )


def test_upgrade_is_idempotent_and_downgrade_removes_triggers(upgraded_engine: Engine) -> None:
    mod = _load_migration()
    with upgraded_engine.begin() as conn:
        for stmt in (mod._ROW_FUNCTION_SQL, mod._TRUNCATE_FUNCTION_SQL, mod._TRIGGERS_SQL):
            conn.execute(text(stmt))
    query = text(
        """
        SELECT tgname FROM pg_trigger
        WHERE tgrelid = 'fsma.traceability_events'::regclass AND NOT tgisinternal
          AND tgname IN ('traceability_events_mutation_policy', 'traceability_events_no_truncate')
        """
    )
    with upgraded_engine.connect() as conn:
        assert len(set(conn.execute(query).scalars())) == 2
    try:
        with upgraded_engine.begin() as conn:
            conn.exec_driver_sql(mod._DOWNGRADE_SQL)
        with upgraded_engine.connect() as conn:
            assert set(conn.execute(query).scalars()) == set()
            functions = set(
                conn.execute(
                    text(
                        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                        " WHERE n.nspname = 'fsma' AND p.proname LIKE 'prevent_traceability_event_%'"
                    )
                ).scalars()
            )
            assert functions == set()
    finally:
        with upgraded_engine.begin() as conn:
            for stmt in (mod._ROW_FUNCTION_SQL, mod._TRUNCATE_FUNCTION_SQL, mod._TRIGGERS_SQL):
                conn.execute(text(stmt))
    with upgraded_engine.connect() as conn:
        assert len(set(conn.execute(query).scalars())) == 2
