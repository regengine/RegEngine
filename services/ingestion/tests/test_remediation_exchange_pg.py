"""Remediation exchange is single-use even under a race: live Postgres.

``exchange_for_session`` used to check ``exchange_count`` in Python and then
run an UPDATE with no count guard, so two requests that both pre-read
``exchange_count = 0`` could each mint a session. The UPDATE now carries
``exchange_count < :max_exchanges`` and the zero-rowcount path denies.

This module runs the real statement against a real cluster in a throwaway
database with a minimal ``fsma.remediation_tokens`` table (migration v095
columns). Live tests are opt-in via ``REMEDIATION_EXCHANGE_PG_ADMIN_DSN``;
without it they skip, except under ``REGENGINE_REQUIRE_DB=1`` where missing
or unreachable DB fails (#2530). Import/collection never connects. Throwaway
DB: unique name, no pre-DROP, DROP owned-only, cleanup fails closed, and
setup/cleanup errors name the env var instead of the DSN.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import subprocess
import sys
import textwrap
import traceback
import uuid
from pathlib import Path
from unittest import mock

import pytest
from fastapi import HTTPException
from shared.db_url import sync_postgres_url
from sqlalchemy import text

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.remediation.tokens as tokens

ADMIN_ENV_VAR = "REMEDIATION_EXCHANGE_PG_ADMIN_DSN"
REQUIRE_ENV_VAR = "REGENGINE_REQUIRE_DB"

_DB_NAME_PREFIX = "fleet_remediation_race_"


def _unique_db_name() -> str:
    return f"{_DB_NAME_PREFIX}{secrets.token_hex(8)}"


def _derived_db_dsn(admin_dsn: str, db_name: str) -> str:
    from sqlalchemy.engine import make_url

    url = make_url(admin_dsn).set(database=db_name)
    return sync_postgres_url(url.render_as_string(hide_password=False))


def _admin_engine(admin_dsn: str):
    from sqlalchemy import create_engine

    return create_engine(
        sync_postgres_url(admin_dsn),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000 -c lock_timeout=5000"},
    )


def _db_engine(derived_dsn: str):
    from sqlalchemy import create_engine

    return create_engine(
        sync_postgres_url(derived_dsn),
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000 -c lock_timeout=5000"},
    )


def _is_admin_reachable(admin_dsn: str) -> bool:
    try:
        engine = _admin_engine(admin_dsn)
    except Exception:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            engine.dispose()


@contextlib.contextmanager
def _throwaway_pg_engine(admin_dsn):
    """Yield an engine on a fresh throwaway DB; drop the owned DB afterwards."""
    db_name = _unique_db_name()
    admin = None
    engine = None
    owned = False
    try:
        try:
            admin = _admin_engine(admin_dsn)
            with admin.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            owned = True
            engine = _db_engine(_derived_db_dsn(admin_dsn, db_name))
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS fsma"))
                conn.execute(
                    text(
                        "CREATE TABLE fsma.remediation_tokens (id UUID PRIMARY KEY, tenant_id UUID NOT NULL, "
                        "session_token_hash TEXT UNIQUE, session_expires_at TIMESTAMPTZ, "
                        "exchange_count INTEGER NOT NULL DEFAULT 0, revoked_at TIMESTAMPTZ)"
                    )
                )
        except Exception:
            raise RuntimeError(f"throwaway PG setup failed for {db_name!r} (see {ADMIN_ENV_VAR})") from None
        yield engine
    finally:
        if engine is not None:
            with contextlib.suppress(Exception):
                engine.dispose()
        if owned and admin is not None:
            try:
                with admin.connect() as conn:
                    conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            except Exception:
                with contextlib.suppress(Exception):
                    admin.dispose()
                raise RuntimeError(f"throwaway PG cleanup failed for {db_name!r} (see {ADMIN_ENV_VAR})") from None
        if admin is not None:
            with contextlib.suppress(Exception):
                admin.dispose()


@pytest.fixture(scope="module")
def pg_engine():
    """Throwaway database with a minimal remediation_tokens table, dropped after."""
    admin_dsn = os.environ.get(ADMIN_ENV_VAR)
    require_db = os.environ.get(REQUIRE_ENV_VAR) == "1"
    if not admin_dsn:
        msg = f"{ADMIN_ENV_VAR} is not set: live PG race tests are opt-in only."
        if require_db:
            pytest.fail(f"{REQUIRE_ENV_VAR}=1 but {msg} Refusing to skip.")
        pytest.skip(msg)
    assert admin_dsn is not None
    if not _is_admin_reachable(admin_dsn):
        if require_db:
            pytest.fail(f"{REQUIRE_ENV_VAR}=1 but admin PG is unreachable (see {ADMIN_ENV_VAR}): refusing to skip.")
        pytest.skip(f"admin PG unreachable (see {ADMIN_ENV_VAR})")
    with _throwaway_pg_engine(admin_dsn) as engine:
        yield engine


@pytest.fixture()
def db_session(pg_engine, monkeypatch):
    from sqlalchemy.orm import Session

    monkeypatch.setattr(tokens, "audit_event", lambda *a, **k: None)
    monkeypatch.setattr(tokens, "set_tenant_guc", lambda *a, **k: None)
    session = Session(bind=pg_engine)
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture()
def token_row(db_session):
    tenant_id, token_id, case_id = (str(uuid.uuid4()) for _ in range(3))
    db_session.execute(
        text(
            "INSERT INTO fsma.remediation_tokens (id, tenant_id, exchange_count) "
            "VALUES (CAST(:id AS uuid), CAST(:tenant AS uuid), 0)"
        ),
        {"id": token_id, "tenant": tenant_id},
    )
    db_session.commit()
    return {"id": token_id, "tenant_id": tenant_id, "case_id": case_id, "exchange_count": 0}


@pytest.mark.integration
def test_second_exchange_with_stale_read_fails_pg(db_session, token_row):
    """Both requests pre-read exchange_count = 0; the loser gets the uniform 400."""
    first = tokens.exchange_for_session(db_session, dict(token_row))
    db_session.commit()
    assert first["session_token"]

    with pytest.raises(HTTPException) as exc_info:
        tokens.exchange_for_session(db_session, dict(token_row))
    db_session.rollback()
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Remediation link is not usable"

    count = db_session.execute(
        text("SELECT exchange_count FROM fsma.remediation_tokens WHERE id = CAST(:id AS uuid)"),
        {"id": token_row["id"]},
    ).scalar()
    assert count == 1


@pytest.mark.integration
def test_first_session_survives_lost_race_pg(db_session, token_row):
    """The winner's session hash is stored exactly once; no second session exists."""
    tokens.exchange_for_session(db_session, dict(token_row))
    db_session.commit()
    with pytest.raises(HTTPException):
        tokens.exchange_for_session(db_session, dict(token_row))
    db_session.rollback()

    rows = db_session.execute(
        text(
            "SELECT exchange_count, session_token_hash IS NOT NULL "
            "FROM fsma.remediation_tokens WHERE id = CAST(:id AS uuid)"
        ),
        {"id": token_row["id"]},
    ).one()
    assert rows[0] == 1
    assert rows[1] is True


@pytest.mark.integration
def test_concurrent_exchanges_single_winner_pg(pg_engine, token_row, db_session):
    """Separate transactions race the same stale token; exactly one succeeds."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    barrier = Barrier(2)

    def exchange():
        with Session(bind=pg_engine) as session:
            barrier.wait(timeout=10)
            try:
                result = tokens.exchange_for_session(session, dict(token_row))
                session.commit()
                return ("accepted", result["session_token"])
            except HTTPException as exc:
                session.rollback()
                return ("denied", exc.status_code, exc.detail)

    # The engine bounds connection, statement and lock waits to five seconds.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(exchange) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert sum(result[0] == "accepted" for result in results) == 1
    assert ("denied", 400, "Remediation link is not usable") in results
    count = db_session.execute(
        text("SELECT exchange_count FROM fsma.remediation_tokens WHERE id = CAST(:id AS uuid)"),
        {"id": token_row["id"]},
    ).scalar()
    assert count == 1


class _FakeEngine:
    def __init__(self, record, fail=None):
        self._record = record
        self._fail = fail or {}
        self.disposed = False

    def connect(self):
        return contextlib.nullcontext(self)

    def begin(self):
        return contextlib.nullcontext(self)

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self._record.append(sql)
        for needle, exc in self._fail.items():
            if needle in sql:
                raise exc
        return None

    def dispose(self):
        self.disposed = True


def _assert_sanitized(exc, secret, dsn):
    assert secret not in str(exc)
    assert dsn not in str(exc)
    assert ADMIN_ENV_VAR in str(exc)
    assert exc.__cause__ is None
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert secret not in rendered
    assert dsn not in rendered


@pytest.mark.parametrize(
    "phase,expect_drop",
    [
        ("admin_factory", 0),
        ("create", 0),
        ("derived", 1),
        ("db_factory", 1),
        ("schema", 1),
        ("drop", 1),
        ("success", 1),
        ("body", 1),
    ],
)
def test_throwaway_lifecycle(monkeypatch, phase, expect_drop):
    secret = "synth-secret-001"  # pragma: allowlist secret - synthetic redaction sentinel
    admin_dsn = f"postgresql://alice:{secret}@127.0.0.1:1/postgres"
    admin_rec: list = []
    db_rec: list = []
    engines: list = []
    monkeypatch.setattr(f"{__name__}._unique_db_name", lambda: "fleet_remediation_race_owned")
    boom = RuntimeError(f"boom {secret} at {admin_dsn}")
    admin_fail = {"create": {"CREATE DATABASE": boom}, "drop": {"DROP DATABASE": boom}}.get(phase, {})
    db_fail = {"schema": {"CREATE TABLE": boom}}.get(phase, {})

    def factory(role, dsn):
        if phase == f"{role}_factory":
            raise boom
        if role == "admin":
            assert dsn == admin_dsn
            engine = _FakeEngine(admin_rec, admin_fail)
        else:
            assert "fleet_remediation_race_owned" in dsn
            engine = _FakeEngine(db_rec, db_fail)
        engines.append(engine)
        return engine

    monkeypatch.setattr(f"{__name__}._admin_engine", lambda dsn: factory("admin", dsn))
    monkeypatch.setattr(f"{__name__}._db_engine", lambda dsn: factory("db", dsn))
    if phase == "derived":
        monkeypatch.setattr(f"{__name__}._derived_db_dsn", mock.Mock(side_effect=boom))
    expected = (
        contextlib.nullcontext()
        if phase == "success"
        else pytest.raises(
            AssertionError if phase == "body" else RuntimeError,
            match="body-boom" if phase == "body" else "cleanup failed" if phase == "drop" else "setup failed",
        )
    )
    with expected as error:
        with _throwaway_pg_engine(admin_dsn):
            assert any("CREATE DATABASE" in statement for statement in admin_rec)
            assert not any("DROP DATABASE" in statement for statement in admin_rec)
            if phase == "body":
                raise AssertionError("body-boom")
            assert phase in {"success", "drop"}, "setup failure must not yield"
    if phase not in {"success", "body"}:
        _assert_sanitized(error.value, secret, admin_dsn)

    creates = [s for s in admin_rec if "CREATE DATABASE" in s]
    drops = [s for s in admin_rec if "DROP DATABASE" in s]
    assert len(drops) == expect_drop
    assert not any("pg_terminate_backend" in s for s in admin_rec + db_rec)
    assert all(e.disposed for e in engines)
    if expect_drop:
        assert len(creates) == 1
        assert "fleet_remediation_race_owned" in creates[0]
        assert "fleet_remediation_race_owned" in drops[0]
    else:
        assert len(creates) <= 1


def test_db_names_unique_and_prefixed():
    names = {_unique_db_name() for _ in range(20)}
    assert len(names) == 20
    assert all(n.startswith(_DB_NAME_PREFIX) for n in names)


def test_derived_dsn_preserves_query():
    from sqlalchemy.engine import make_url

    admin = "postgresql://alice:pw@db.example.com:5433/postgres?sslmode=require&connect_timeout=5"  # pragma: allowlist secret - URL parsing only
    parsed = make_url(_derived_db_dsn(admin, "owned_db_1"))
    assert parsed.database == "owned_db_1"
    assert parsed.username == "alice"
    assert parsed.host == "db.example.com"
    assert parsed.port == 5433
    assert parsed.query["sslmode"] == "require"
    assert parsed.query["connect_timeout"] == "5"


def test_missing_dsn_skips_or_fails(monkeypatch):
    monkeypatch.delenv(ADMIN_ENV_VAR, raising=False)
    monkeypatch.delenv(REQUIRE_ENV_VAR, raising=False)
    with pytest.raises(pytest.skip.Exception, match="opt-in only"):
        list(pg_engine.__wrapped__())
    monkeypatch.setenv(REQUIRE_ENV_VAR, "1")
    with pytest.raises(pytest.fail.Exception, match="opt-in only"):
        list(pg_engine.__wrapped__())


def test_unreachable_admin_skips_or_fails_sanitized(monkeypatch):
    secret = "pw-unreachable-456"  # pragma: allowlist secret - synthetic redaction sentinel
    dsn = f"postgresql://bob:{secret}@127.0.0.1:1/postgres?sslmode=require"
    monkeypatch.setenv(ADMIN_ENV_VAR, dsn)
    with mock.patch(f"{__name__}._is_admin_reachable", return_value=False):
        monkeypatch.delenv(REQUIRE_ENV_VAR, raising=False)
        with pytest.raises(pytest.skip.Exception) as s:
            list(pg_engine.__wrapped__())
        assert secret not in str(s.value) and dsn not in str(s.value)
        assert ADMIN_ENV_VAR in str(s.value)
        monkeypatch.setenv(REQUIRE_ENV_VAR, "1")
        with pytest.raises(pytest.fail.Exception) as f:
            list(pg_engine.__wrapped__())
        assert secret not in str(f.value) and dsn not in str(f.value)
        assert s.value.__cause__ is None and f.value.__cause__ is None


def test_import_and_collection_never_connect():
    target = Path(__file__).resolve()
    script = textwrap.dedent(
        """
        import runpy
        import socket
        import sys
        from pathlib import Path
        import pytest

        attempts = []
        def blocked(*args, **kwargs):
            attempts.append(True)
            raise AssertionError("database connection during collection")
        socket.socket.connect = blocked
        import sqlalchemy
        sqlalchemy.create_engine = blocked
        target = Path(sys.argv[1])
        sys.path[:0] = [str(target.parents[3] / "services"), str(target.parent.parent)]
        runpy.run_path(str(target), run_name="fixture_import_probe")
        assert pytest.main([str(target), "--collect-only", "-q"]) == 0
        assert pytest.main([str(target), "-k", "definitely_no_such_test_xyz", "-q"]) == 5
        assert not attempts, "even a caught connection attempt is forbidden"
        """
    )
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_ADDOPTS="-p no:cacheprovider")
    env.update({ADMIN_ENV_VAR: "postgresql://test@127.0.0.1:1/postgres", REQUIRE_ENV_VAR: "1"})
    result = subprocess.run(
        [sys.executable, "-c", script, str(target)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=target.parents[3],
        env=env,
    )
    assert result.returncode == 0, result.stderr[-4000:] + result.stdout[-4000:]
