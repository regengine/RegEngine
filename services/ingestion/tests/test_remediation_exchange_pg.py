"""Remediation exchange is single-use even under a race: live Postgres.

``exchange_for_session`` used to check ``exchange_count`` in Python and then
run an UPDATE with no count guard, so two requests that both pre-read
``exchange_count = 0`` could each mint a session. The UPDATE now carries
``exchange_count < :max_exchanges`` and the zero-rowcount path denies, so the
loser of the race fails with the uniform 400.

The unit tests in
``remediation/test_remediation_exchange_race.py`` run against a fake session
that never parses the SQL, so they pass as long as the fake mimics the guard.
This module runs the real statement against a real cluster in a throwaway
database carrying a minimal ``fsma.remediation_tokens`` table (same column
names and types the UPDATE touches as migration v095).

Skips cleanly when no Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from shared.db_url import sync_postgres_url
from sqlalchemy import text

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.remediation.tokens as tokens

ADMIN_DSN = os.environ.get(
    "REMEDIATION_EXCHANGE_PG_ADMIN_DSN",
    "postgresql://sellers@localhost:5432/postgres",
)
DB_NAME = "fleet_remediation_race"


def _engine(dsn: str):
    from sqlalchemy import create_engine

    return create_engine(sync_postgres_url(dsn), isolation_level="AUTOCOMMIT")


def _reachable() -> bool:
    try:
        engine = _engine(ADMIN_DSN)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_DB_READY = _reachable()

if not _DB_READY and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(
        f"REGENGINE_REQUIRE_DB=1 but no Postgres is reachable at {ADMIN_DSN!r}: refusing to skip."
    )

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DB_READY, reason="local Postgres not available"),
]


@pytest.fixture(scope="module")
def pg_engine():
    """Throwaway database with a minimal remediation_tokens table, dropped after."""
    from sqlalchemy import create_engine

    admin = _engine(ADMIN_DSN)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    admin.dispose()

    dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{DB_NAME}"
    engine = create_engine(sync_postgres_url(dsn))
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS fsma"))
        conn.execute(
            text(
                """
                CREATE TABLE fsma.remediation_tokens (
                    id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    session_token_hash TEXT UNIQUE,
                    session_expires_at TIMESTAMPTZ,
                    exchange_count INTEGER NOT NULL DEFAULT 0,
                    revoked_at TIMESTAMPTZ
                )
                """
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        admin = _engine(ADMIN_DSN)
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{DB_NAME}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
        admin.dispose()


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
