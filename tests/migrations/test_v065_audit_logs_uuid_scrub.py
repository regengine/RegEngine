"""v065 audit_logs UUID column conversion — integration test.

Regression test for the prod failure on 2026-04-25: deploy ``b9613323``
crashed inside ``alembic upgrade head`` on this exact SQL --

    ALTER TABLE public.audit_logs
    ALTER COLUMN tenant_id TYPE uuid USING tenant_id::uuid

-- because at least one row contained a value that was not castable to
``uuid`` (empty string, ``"system"`` sentinel, etc.). The cast aborted the
ALTER, the migration exited non-zero, the container failed to start,
the Railway healthcheck timed out, and every subsequent deploy on top
of the same DB state hit the same wall.

This test reproduces that environment by:

1. Spinning up a disposable PostgreSQL container.
2. Creating ``audit_logs`` in its legacy shape (``tenant_id``,
   ``actor_id``, ``request_id`` all ``text``).
3. Seeding the table with a mix of:
   - valid UUID strings (must survive),
   - NULL in nullable columns (must survive as NULL),
   - non-castable garbage in the NOT NULL column (must be deleted),
   - non-castable garbage in nullable columns (must become NULL).
4. Running the v065 ``upgrade()`` SQL.
5. Asserting:
   - the three columns are now ``uuid`` data type,
   - valid rows still have their original UUID values,
   - non-castable ``actor_id`` / ``request_id`` are NULL,
   - rows with non-castable ``tenant_id`` were removed,
   - re-running ``upgrade()`` is a no-op (idempotent).

Requires Docker for testcontainers. If Docker is unavailable the test
module skips cleanly.

Run via:
    pytest tests/migrations/test_v065_audit_logs_uuid_scrub.py -v
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

testcontainers = pytest.importorskip("testcontainers")  # noqa: F841
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "20260423_c7d8e9f0a1b2_v065_audit_logs_fix_uuid_columns.py"
)


def _load_v065_module():
    """Import the v065 migration module without going through Alembic."""
    spec = importlib.util.spec_from_file_location(
        "v065_audit_logs_fix_uuid_columns", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_v065(conn, v065) -> None:
    """Apply v065's full upgrade sequence on an open SQLAlchemy connection.

    Mirrors the ordering in ``v065.upgrade()``:
      1. create scrub helper
      2. drop the v056 policy (so the ALTERs aren't blocked by it)
      3. scrub + ALTER each column
      4. re-issue the policy without the ``::uuid`` cast
    """
    conn.execute(text(v065._CREATE_IS_VALID_UUID_FN))
    conn.execute(text(v065._DROP_POLICY_SQL))
    for column, is_nullable in v065._COLUMNS_TO_FIX:
        conn.execute(text(v065._scrub_and_alter_text_to_uuid(column, is_nullable)))
    conn.execute(text(v065._CREATE_POLICY_NO_CAST_SQL))


# Static UUIDs let the assertions reference exact values rather than
# fishing them back out of the DB.
GOOD_TENANT = "11111111-1111-1111-1111-111111111111"
GOOD_TENANT_2 = "22222222-2222-2222-2222-222222222222"
GOOD_ACTOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GOOD_REQUEST = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture(scope="module")
def pg_engine():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url(), future=True)
        with engine.begin() as conn:
            # Minimal stand-in for ``get_tenant_context()`` so the v056-style
            # RLS policy that v065 re-issues parses on this disposable DB.
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION get_tenant_context()
                    RETURNS uuid
                    LANGUAGE sql STABLE AS $$
                        SELECT NULL::uuid
                    $$;
                    """
                )
            )
        yield engine
        engine.dispose()


@pytest.fixture
def seed_audit_rows(pg_engine):
    """Insert a representative mix of good and bad rows, return their ids.

    Uses a separate fixture per test so each test runs against a fresh
    table state. Each test seeds via DROP + CREATE + INSERT, so there's no
    cross-test leakage even though the engine is module-scoped.
    """
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))
        conn.execute(
            text(
                """
                CREATE TABLE public.audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id text NOT NULL,
                    actor_id text NULL,
                    request_id text NULL,
                    integrity_hash text NOT NULL
                )
                """
            )
        )
        rows = [
            # 1. Fully valid row — must survive untouched.
            (GOOD_TENANT, GOOD_ACTOR, GOOD_REQUEST, "good-1"),
            # 2. Valid tenant, NULL actor/request — must survive.
            (GOOD_TENANT_2, None, None, "good-2"),
            # 3. Valid tenant, garbage actor and request — actor/request
            #    must become NULL, row stays.
            (GOOD_TENANT, "system", "", "scrub-actor-and-request"),
            # 4. Garbage tenant — entire row must be deleted.
            ("not-a-uuid", GOOD_ACTOR, GOOD_REQUEST, "bad-tenant-delete"),
            # 5. Empty-string tenant (the most common real-world failure
            #    mode for ``text -> uuid`` ALTERs). Row must be deleted.
            ("", None, None, "empty-tenant-delete"),
        ]
        ids = []
        for tenant, actor, request, hash_label in rows:
            row_id = conn.execute(
                text(
                    """
                    INSERT INTO audit_logs
                        (tenant_id, actor_id, request_id, integrity_hash)
                    VALUES (:t, :a, :r, :h)
                    RETURNING id
                    """
                ),
                {"t": tenant, "a": actor, "r": request, "h": hash_label},
            ).scalar_one()
            ids.append(row_id)
    yield ids
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.audit_logs"))


def _column_data_types(conn) -> dict[str, str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'audit_logs'
              AND column_name IN ('tenant_id', 'actor_id', 'request_id')
            """
        )
    ).all()
    return {r[0]: r[1] for r in rows}


def test_v065_converts_columns_to_uuid(pg_engine, seed_audit_rows):
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        types = _column_data_types(conn)

    assert types == {
        "tenant_id": "uuid",
        "actor_id": "uuid",
        "request_id": "uuid",
    }


def test_v065_preserves_valid_rows(pg_engine, seed_audit_rows):
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        rows = conn.execute(
            text(
                """
                SELECT tenant_id::text, actor_id::text, request_id::text,
                       integrity_hash
                FROM audit_logs
                WHERE integrity_hash IN ('good-1', 'good-2')
                ORDER BY integrity_hash
                """
            )
        ).all()

    assert rows == [
        (GOOD_TENANT, GOOD_ACTOR, GOOD_REQUEST, "good-1"),
        (GOOD_TENANT_2, None, None, "good-2"),
    ]


def test_v065_nulls_garbage_in_nullable_columns(pg_engine, seed_audit_rows):
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        row = conn.execute(
            text(
                """
                SELECT tenant_id::text, actor_id, request_id
                FROM audit_logs
                WHERE integrity_hash = 'scrub-actor-and-request'
                """
            )
        ).one()

    tenant_id_text, actor_id, request_id = row
    assert tenant_id_text == GOOD_TENANT
    assert actor_id is None, "non-UUID actor_id should be NULL after v065"
    assert request_id is None, "non-UUID request_id should be NULL after v065"


def test_v065_deletes_rows_with_non_castable_tenant_id(pg_engine, seed_audit_rows):
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        labels = {
            r[0]
            for r in conn.execute(text("SELECT integrity_hash FROM audit_logs")).all()
        }

    assert "bad-tenant-delete" not in labels
    assert "empty-tenant-delete" not in labels
    assert {"good-1", "good-2", "scrub-actor-and-request"} <= labels


def test_v065_is_idempotent(pg_engine, seed_audit_rows):
    """Re-running the upgrade on already-uuid columns must be a clean no-op."""
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        before = {
            r[0]
            for r in conn.execute(text("SELECT integrity_hash FROM audit_logs")).all()
        }

    # Second apply (different transaction so pg_temp helper is recreated).
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        after = {
            r[0]
            for r in conn.execute(text("SELECT integrity_hash FROM audit_logs")).all()
        }
        types = _column_data_types(conn)

    assert before == after
    assert types == {
        "tenant_id": "uuid",
        "actor_id": "uuid",
        "request_id": "uuid",
    }


def test_v065_does_not_resurrect_rls_uuid_cast(pg_engine, seed_audit_rows):
    """The re-issued RLS policy must reference plain ``tenant_id``, not ``tenant_id::uuid``.

    The whole point of v065 is to remove the type drift that forced the
    v056 workaround cast. If the cast comes back, the drift came back.
    """
    v065 = _load_v065_module()
    with pg_engine.begin() as conn:
        _apply_v065(conn, v065)
        policy_def = conn.execute(
            text(
                """
                SELECT pg_get_expr(polqual, polrelid)
                FROM pg_policy
                WHERE polname = 'tenant_isolation_audit'
                  AND polrelid = 'public.audit_logs'::regclass
                """
            )
        ).scalar_one()

    assert "::uuid" not in policy_def, (
        f"v065 should drop the ::uuid workaround cast, got: {policy_def}"
    )
    assert "get_tenant_context()" in policy_def
