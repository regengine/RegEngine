"""Cross-tenant RLS isolation on the admin surface, proven against a REAL Postgres (#2876).

What this file used to be
-------------------------
A "pilot" that skipped unconditionally (its fixture required six
``V*.sql`` files that ``services/admin/migrations/`` has never
contained) and, underneath the skip, ended in ``assert True`` after
printing the *same* ``results`` variable twice. It could not fail even
if it ran, so the single most important property in a multi-tenant
compliance product — a tenant cannot see another tenant's rows — was
certified by a tautology.

What it is now
--------------
A behavioural test against a live PostgreSQL. It asserts the isolation
contract the admin surface depends on, using **production artefacts**
rather than re-implementations:

* ``get_tenant_context()`` is installed by executing the real SQL from
  the v097 migration module (``_PIN_FAIL_HARD``) — not a copy pasted
  into this file. Same technique as
  ``tests/migrations/test_v097_pin_get_tenant_context.py``.
* ``app.tenant_id`` is set through the real production primitive
  ``shared.tenant_context.set_tenant_guc``. If that helper starts
  writing the wrong GUC name, the wrong scope, or nothing, these tests
  go red.
* The policy predicate is the canonical repo shape
  ``USING (tenant_id = get_tenant_context())`` with ``ENABLE`` +
  ``FORCE ROW LEVEL SECURITY``, applied ``TO`` a **non-superuser,
  NOBYPASSRLS** role — because RLS is a no-op for superusers, and
  running the old "pilot" as the container superuser is exactly why it
  could never have observed isolation even with the migrations present.

Everything is built inside a throwaway schema and a throwaway role,
both dropped on teardown, so the suite is safe to point at a shared CI
database.

Infrastructure gate
-------------------
Postgres acquisition goes through ``tests.migrations.rls_db`` — the
repo's existing policy helper: CI's service-container ``DATABASE_URL``,
else an explicitly designated ``REGENGINE_MIGRATION_TEST_DB``, else
testcontainers, else skip. Under ``REGENGINE_REQUIRE_DB=1`` (set by the
``repo-root-suite`` job) an unavailable database is a **hard failure**,
so this gate can never report green by not running.
"""

from __future__ import annotations

import importlib.util
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.migrations.rls_db import rls_postgres_or_skip

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
V097_PATH = REPO_ROOT / "alembic" / "versions" / "20260721_e4d7b2a9c561_v097_pin_get_tenant_context_fail_hard.py"

TABLE = "admin_rls_probe"


def _load_v097():
    """Import the v097 migration module by path for its canonical SQL.

    Loading the module (rather than copying the DDL) is what keeps this
    test honest: if the pinned ``get_tenant_context()`` body ever goes
    back to fail-soft, the assertions below break here rather than in
    production.
    """
    spec = importlib.util.spec_from_file_location("v097_pin_get_tenant_context", V097_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {V097_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rls_fixture() -> Iterator[tuple[Engine, str, str]]:
    """Yield ``(engine, schema, app_role)`` for a live, RLS-protected table.

    Skips (or FAILS under ``REGENGINE_REQUIRE_DB=1``) when no real
    Postgres is reachable — see the module docstring.
    """
    with rls_postgres_or_skip() as (_plain_url, engine):
        suffix = uuid.uuid4().hex[:12]
        schema = f"admin_rls_{suffix}"
        app_role = f"admin_rls_app_{suffix}"
        try:
            _bootstrap(engine, schema, app_role)
            yield engine, schema, app_role
        finally:
            _teardown(engine, schema, app_role)


def _bootstrap(engine: Engine, schema: str, app_role: str) -> None:
    v097 = _load_v097()
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        # search_path first: v097's DO block installs the function into the
        # first schema of current_schemas(true) that already holds one, so
        # seeding a placeholder here keeps the canonical function inside our
        # throwaway schema instead of touching public.
        conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        conn.execute(
            text(
                # The deliberately WRONG pre-v097 fail-soft shape. v097's job
                # is to replace exactly this; installing it first means the
                # migration's real CREATE OR REPLACE branch is what produces
                # the function these tests then rely on.
                f"""
                CREATE FUNCTION "{schema}".get_tenant_context() RETURNS UUID AS $fn$
                BEGIN
                    RETURN NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID;
                EXCEPTION WHEN OTHERS THEN
                    RETURN NULL;
                END;
                $fn$ LANGUAGE plpgsql;
                """
            )
        )
        conn.execute(text(v097._PIN_FAIL_HARD))

        conn.execute(text(f'CREATE ROLE "{app_role}" NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT'))
        conn.execute(
            text(
                f"""
                CREATE TABLE "{schema}"."{TABLE}" (
                    id        UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    name      TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(text(f'ALTER TABLE "{schema}"."{TABLE}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{schema}"."{TABLE}" FORCE ROW LEVEL SECURITY'))
        conn.execute(
            text(
                f"""
                CREATE POLICY tenant_isolation_{TABLE} ON "{schema}"."{TABLE}"
                    FOR ALL TO "{app_role}"
                    USING (tenant_id = "{schema}".get_tenant_context())
                """
            )
        )
        conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{app_role}"'))
        conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{schema}"."{TABLE}" TO "{app_role}"'))
        conn.execute(text(f'GRANT EXECUTE ON FUNCTION "{schema}".get_tenant_context() TO "{app_role}"'))


def _teardown(engine: Engine, schema: str, app_role: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.execute(text(f'DROP OWNED BY "{app_role}" CASCADE'))
        conn.execute(text(f'DROP ROLE IF EXISTS "{app_role}"'))


@pytest.fixture(scope="module")
def seeded(rls_fixture) -> Iterator[dict]:
    """Insert one row per tenant as the (RLS-bypassing) owner."""
    engine, schema, app_role = rls_fixture
    rows = {
        "tenant_a": uuid.uuid4(),
        "tenant_b": uuid.uuid4(),
        "row_a": uuid.uuid4(),
        "row_b": uuid.uuid4(),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO "{schema}"."{TABLE}" (id, tenant_id, name) VALUES
                    (:row_a, :tenant_a, 'Project A'),
                    (:row_b, :tenant_b, 'Project B')
                """
            ),
            {str(k): v for k, v in rows.items()},
        )
    yield rows


@contextmanager
def _tenant_session(engine: Engine, schema: str, app_role: str, tenant_id) -> Iterator[Session]:
    """A transaction running as the app role with ``app.tenant_id`` set.

    ``tenant_id=None`` means "no tenant context at all" — the
    untenanted-access case that must fail closed.
    """
    session = Session(bind=engine)
    try:
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        session.execute(text(f'SET LOCAL ROLE "{app_role}"'))
        if tenant_id is not None:
            # Production primitive, not a hand-rolled SET LOCAL.
            set_tenant_guc(session, str(tenant_id))
        yield session
    finally:
        session.rollback()
        session.close()


def _visible_names(session: Session, schema: str) -> set[str]:
    return {row[0] for row in session.execute(text(f'SELECT name FROM "{schema}"."{TABLE}"')).all()}


# ---------------------------------------------------------------------------
# The isolation contract
# ---------------------------------------------------------------------------


def test_app_role_is_actually_subject_to_rls(rls_fixture):
    """Guard against the failure that made the old pilot meaningless.

    If the session runs as a superuser or a BYPASSRLS role, every
    isolation assertion below becomes vacuous. Assert the precondition.
    """
    engine, schema, app_role = rls_fixture
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
            {"r": app_role},
        ).one()
    assert row.rolsuper is False, f"{app_role} is a superuser — RLS would be bypassed and these tests vacuous"
    assert row.rolbypassrls is False, f"{app_role} has BYPASSRLS — RLS would be bypassed and these tests vacuous"


def test_tenant_a_sees_only_its_own_rows(rls_fixture, seeded):
    engine, schema, app_role = rls_fixture
    with _tenant_session(engine, schema, app_role, seeded["tenant_a"]) as session:
        assert _visible_names(session, schema) == {"Project A"}


def test_tenant_b_sees_only_its_own_rows(rls_fixture, seeded):
    engine, schema, app_role = rls_fixture
    with _tenant_session(engine, schema, app_role, seeded["tenant_b"]) as session:
        assert _visible_names(session, schema) == {"Project B"}


def test_cross_tenant_row_is_invisible_even_by_primary_key(rls_fixture, seeded):
    """A direct PK lookup must not be a way around the policy."""
    engine, schema, app_role = rls_fixture
    with _tenant_session(engine, schema, app_role, seeded["tenant_a"]) as session:
        leaked = session.execute(
            text(f'SELECT name FROM "{schema}"."{TABLE}" WHERE id = :id'),
            {"id": seeded["row_b"]},
        ).all()
    assert leaked == [], f"tenant A read tenant B's row by primary key: {leaked!r}"


def test_tenant_cannot_write_a_row_owned_by_another_tenant(rls_fixture, seeded):
    """``FOR ALL ... USING`` supplies the WITH CHECK, so forged writes fail."""
    engine, schema, app_role = rls_fixture
    with _tenant_session(engine, schema, app_role, seeded["tenant_a"]) as session:
        with pytest.raises(DatabaseError) as excinfo:
            session.execute(
                text(f'INSERT INTO "{schema}"."{TABLE}" (id, tenant_id, name) VALUES (:id, :tid, :name)'),
                {"id": uuid.uuid4(), "tid": seeded["tenant_b"], "name": "Forged for B"},
            )
    assert "row-level security" in str(excinfo.value).lower()


def test_untenanted_session_fails_closed_rather_than_leaking(rls_fixture, seeded):
    """No ``app.tenant_id`` must RAISE, not quietly return rows.

    This is the #2461 contract: a fail-soft ``get_tenant_context()``
    returns NULL, ``tenant_id = NULL`` is NULL, and the query succeeds
    empty — silent, not loud. Either an empty success *or* a leak fails
    this test.
    """
    engine, schema, app_role = rls_fixture
    with _tenant_session(engine, schema, app_role, None) as session:
        with pytest.raises(DatabaseError) as excinfo:
            session.execute(text(f'SELECT name FROM "{schema}"."{TABLE}"')).all()
    assert "app.tenant_id not set" in str(excinfo.value)


def test_tenant_context_round_trips_through_the_production_helper(rls_fixture, seeded):
    """``set_tenant_guc`` must be what ``get_tenant_context()`` reads."""
    engine, schema, app_role = rls_fixture
    tenant_a = seeded["tenant_a"]
    with _tenant_session(engine, schema, app_role, tenant_a) as session:
        observed = session.execute(text(f'SELECT "{schema}".get_tenant_context()')).scalar()
    assert observed == tenant_a
