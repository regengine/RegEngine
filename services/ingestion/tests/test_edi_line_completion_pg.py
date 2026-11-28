"""Real PostgreSQL tests for completing a stored EDI line (v146, ADR-007).

Run with REGENGINE_MIGRATION_TEST_DB pointing to a disposable Postgres server.
CI runs this via the existing live test_*_pg.py gate. ``fsma.cte_events`` is a
stand-in, as in test_edi_line_identity_pg.py, so the registry update, the
supersession marker, row security and the grants are the real ones.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.edi_line_identity import EDILine, EDILineRegistry, StoredLine
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.migrations.scratch_db import scratch_database_engine

ROOT = Path(__file__).resolve().parents[3]
V145 = ROOT / "alembic/versions/20261121_62355c37e367_v145_edi_line_identities.py"
V146 = ROOT / "alembic/versions/20261128_20ef2227dc73_v146_cte_event_supersessions.py"
SUPABASE_TWIN = ROOT / "supabase/migrations/20261128000000_v146_cte_event_supersessions.sql"
MARKERS = "fsma.cte_event_supersessions"
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
REGISTRY = EDILineRegistry()
INCOMPLETE = EDILine("identity-a", "digest-incomplete")
COMPLETE = EDILine("identity-a", "digest-complete")
# The filter the regulator-facing readers add, run against the stand-in.
LIVE_EVENTS = """
    SELECT e.id FROM fsma.cte_events e
    WHERE e.tenant_id = :tid
      AND NOT EXISTS (
          SELECT 1 FROM fsma.cte_event_supersessions s
          WHERE s.tenant_id = :tid AND s.superseded_event_id = e.id
      )
"""


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def database():
    if not os.getenv("REGENGINE_MIGRATION_TEST_DB") and not (
        os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
    ):
        pytest.skip("set REGENGINE_MIGRATION_TEST_DB to run live EDI line completion tests")
    with scratch_database_engine("edi_completion_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            conn.execute(
                text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'regengine') THEN
                        CREATE ROLE regengine NOLOGIN NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END $$;
                CREATE SCHEMA fsma;
                GRANT USAGE ON SCHEMA fsma TO regengine;
                CREATE FUNCTION public.get_tenant_context() RETURNS uuid LANGUAGE sql STABLE
                    AS $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;
                CREATE TABLE fsma.cte_events (
                    id uuid PRIMARY KEY,
                    tenant_id uuid NOT NULL,
                    quantity double precision NOT NULL,
                    sha256_hash text NOT NULL,
                    chain_hash text NOT NULL
                );
                GRANT SELECT, INSERT ON fsma.cte_events TO regengine;
            """)
            )
            with Operations.context(MigrationContext.configure(conn)):
                _load(V145, "v145").upgrade()
                _load(V146, "v146").upgrade()
        yield engine


@pytest.fixture()
def db(database):
    with database.begin() as conn:
        conn.execute(text(f"TRUNCATE {MARKERS}, fsma.edi_line_identities, fsma.cte_events"))
    return database


def _session(db, tenant_id: str = TENANT) -> Session:
    session = Session(db)
    session.execute(text("SET LOCAL ROLE regengine"))
    set_tenant_guc(session, tenant_id)
    return session


def _store_event(session, tenant_id: str = TENANT) -> str:
    event_id = str(uuid4())
    session.execute(
        text("INSERT INTO fsma.cte_events VALUES (CAST(:id AS uuid), CAST(:tenant AS uuid), 1, 'sha', 'chain')"),
        {"id": event_id, "tenant": tenant_id},
    )
    return event_id


def _stored_incomplete(db) -> tuple[StoredLine, str]:
    """An incomplete line recorded with its canonical link; returns it and the canonical id."""
    canonical = str(uuid4())
    with _session(db) as session:
        REGISTRY.record(session, TENANT, INCOMPLETE, _store_event(session), canonical)
        session.commit()
    with _session(db) as session:
        return REGISTRY.lookup(session, TENANT, [INCOMPLETE])["identity-a"], canonical


def _live_events(db, tenant_id: str = TENANT) -> set[str]:
    with _session(db, tenant_id) as session:
        return {str(row[0]) for row in session.execute(text(LIVE_EVENTS), {"tid": tenant_id})}


def test_a_line_records_and_returns_its_canonical_link(db):
    stored, canonical = _stored_incomplete(db)
    assert stored.canonical_event_id == canonical


def test_completing_a_line_repoints_it_and_marks_the_replaced_event(db):
    stored, _ = _stored_incomplete(db)
    new_canonical = str(uuid4())
    with _session(db) as session:
        new_event = _store_event(session)
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, new_event, new_canonical)
        session.commit()

    with _session(db) as session:
        now = REGISTRY.lookup(session, TENANT, [COMPLETE])["identity-a"]
    assert (now.content_digest, now.event_id, now.canonical_event_id) == ("digest-complete", new_event, new_canonical)
    # Both events stay stored for the chain; only the completed one is live.
    assert _live_events(db) == {new_event}
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fsma.cte_events")).scalar_one() == 2
        row = conn.execute(text(f"SELECT superseded_event_id, superseding_event_id FROM {MARKERS}")).one()
    assert (str(row[0]), str(row[1])) == (stored.event_id, new_event)


def test_a_line_that_changed_meanwhile_is_not_completed(db):
    stored, _ = _stored_incomplete(db)
    moved = StoredLine(stored.content_digest, str(uuid4()), canonical_event_id=stored.canonical_event_id)
    with _session(db) as session:
        new_event = _store_event(session)
        with pytest.raises(RuntimeError, match="changed while being completed"):
            REGISTRY.supersede(session, TENANT, COMPLETE, moved, new_event, str(uuid4()))
    with db.connect() as conn:
        assert conn.execute(text(f"SELECT count(*) FROM {MARKERS}")).scalar_one() == 0
        assert conn.execute(text("SELECT content_digest FROM fsma.edi_line_identities")).scalar_one() == (
            "digest-incomplete"
        )


def test_an_event_is_superseded_once(db):
    stored, _ = _stored_incomplete(db)
    with _session(db) as session:
        first = _store_event(session)
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, first, str(uuid4()))
        session.commit()
    with _session(db) as session:
        with pytest.raises(DBAPIError):
            session.execute(
                text(
                    f"INSERT INTO {MARKERS} (tenant_id, superseded_event_id, superseding_event_id) VALUES "
                    "(CAST(:tid AS uuid), CAST(:old AS uuid), CAST(:new AS uuid))"
                ),
                {"tid": TENANT, "old": stored.event_id, "new": _store_event(session)},
            )


def test_markers_are_tenant_scoped(db):
    stored, _ = _stored_incomplete(db)
    with _session(db) as session:
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, _store_event(session), str(uuid4()))
        session.commit()
    with _session(db, OTHER_TENANT) as session:
        assert session.execute(text(f"SELECT count(*) FROM {MARKERS}")).scalar_one() == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            session.execute(
                text(
                    f"INSERT INTO {MARKERS} (tenant_id, superseded_event_id, superseding_event_id) VALUES "
                    "(CAST(:tid AS uuid), gen_random_uuid(), gen_random_uuid())"
                ),
                {"tid": TENANT},
            )


def test_markers_cannot_be_changed_or_removed(db):
    stored, _ = _stored_incomplete(db)
    with _session(db) as session:
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, _store_event(session), str(uuid4()))
        session.commit()
    for statement in (f"UPDATE {MARKERS} SET superseded_at = now()", f"DELETE FROM {MARKERS}"):
        with _session(db) as session:
            with pytest.raises(DBAPIError):
                session.execute(text(statement))


def test_migration_rerun_downgrade_reupgrade_and_cutover_grants(db):
    """Both migration forms, and the inventory the per-deploy cutover rebuilds grants from."""
    with db.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            _load(V146, "v146").upgrade()
            _load(V146, "v146").downgrade()
            assert conn.execute(text(f"SELECT to_regclass('{MARKERS}')")).scalar_one() is None
            _load(V146, "v146").upgrade()
        conn.execute(text(SUPABASE_TWIN.read_text()))
        # The cutover revokes all table and column grants before rebuilding them.
        conn.execute(text(f"REVOKE ALL ON {MARKERS} FROM regengine"))
        conn.execute(text("REVOKE ALL ON fsma.edi_line_identities FROM regengine"))
        conn.execute(
            text(
                "REVOKE UPDATE (content_digest, event_id, stored_at, canonical_event_id)"
                " ON fsma.edi_line_identities FROM regengine"
            )
        )
        inventory = _load(ROOT / "alembic/versions/20260803_b71d9e4c2a60_v111_runtime_role_grants.py", "v111_inv")
        assert "cte_event_supersessions" in inventory.APPLICATION_TABLES["fsma"]
        for table in (MARKERS, "fsma.edi_line_identities"):
            conn.execute(
                text(inventory._grant_sql("regengine", table, inventory.REGENGINE_TABLE_GRANTS[table], "TABLE"))
            )
            for privilege, columns in inventory.REGENGINE_COLUMN_GRANTS.get(table, {}).items():
                conn.execute(text(inventory._column_grant_sql("regengine", table, privilege, columns)))
        assert conn.execute(
            text(f"SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = '{MARKERS}'::regclass")
        ).scalar_one()
        for privilege in ("UPDATE", "DELETE"):
            assert not conn.execute(
                text(f"SELECT has_table_privilege('regengine', '{MARKERS}', '{privilege}')")
            ).scalar_one()
    # The rebuilt grants are enough to record, complete and read a line.
    stored, _ = _stored_incomplete(db)
    with _session(db) as session:
        new_event = _store_event(session)
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, new_event, str(uuid4()))
        session.commit()
    assert _live_events(db) == {new_event}


def _downgrade_as_owner(db) -> None:
    """Run the v146 downgrade as a non-superuser, non-bypass table owner, like a deploy."""
    with db.begin() as conn:
        conn.execute(
            text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'v146_owner') THEN
                    CREATE ROLE v146_owner NOLOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
            GRANT USAGE ON SCHEMA fsma TO v146_owner;
            GRANT SELECT ON information_schema.columns TO v146_owner;
            ALTER TABLE fsma.cte_event_supersessions OWNER TO v146_owner;
            ALTER TABLE fsma.edi_line_identities OWNER TO v146_owner;
            SET LOCAL ROLE v146_owner;
        """)
        )
        with Operations.context(MigrationContext.configure(conn)):
            _load(V146, "v146").downgrade()


def _restore_v146(db) -> None:
    with db.begin() as conn:
        for table in (MARKERS, "fsma.edi_line_identities"):
            if conn.execute(text(f"SELECT to_regclass('{table}')")).scalar_one() is not None:
                conn.execute(text(f"ALTER TABLE {table} OWNER TO CURRENT_USER"))
        with Operations.context(MigrationContext.configure(conn)):
            _load(V146, "v146").upgrade()


def test_downgrade_refuses_to_drop_supersession_history(db):
    """Forced RLS hides rows from the owner, so the guard must lift it to see them."""
    stored, _ = _stored_incomplete(db)
    with _session(db) as session:
        REGISTRY.supersede(session, TENANT, COMPLETE, stored, _store_event(session), str(uuid4()))
        session.commit()
    try:
        with pytest.raises(DBAPIError, match="v146 downgrade refused"):
            _downgrade_as_owner(db)
        with db.connect() as conn:
            assert conn.execute(text(f"SELECT count(*) FROM {MARKERS}")).scalar_one() == 1
            assert conn.execute(
                text(f"SELECT relforcerowsecurity FROM pg_class WHERE oid = '{MARKERS}'::regclass")
            ).scalar_one(), "a refused downgrade must leave row security forced"
    finally:
        _restore_v146(db)


def test_an_empty_downgrade_is_allowed(db):
    try:
        _downgrade_as_owner(db)
        with db.connect() as conn:
            assert conn.execute(text(f"SELECT to_regclass('{MARKERS}')")).scalar_one() is None
            assert conn.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE oid = 'fsma.edi_line_identities'::regclass")
            ).scalar_one()
    finally:
        _restore_v146(db)
