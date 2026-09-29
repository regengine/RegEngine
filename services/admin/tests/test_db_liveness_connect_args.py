"""The admin engine bounds connects and detects dead peers.

2026-09-28: a Railway Postgres restart black-holed the old container's
address. The admin engine (``ADMIN_DATABASE_URL``, role
``regengine_sysadmin``) passed libpq no ``connect_timeout`` and no TCP
keepalives, so any connection opened in that window waited on the kernel
default (keepalive idle 7200 s) and hung the request that opened it.

Each test captures the kwargs SQLAlchemy hands the DBAPI ``connect()``
(the ``do_connect`` hook fires before any network I/O, so no database is
needed) and asserts the libpq liveness settings are among them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event

from services.admin.app import database as admin_database

PG_URL = "postgresql://probe@127.0.0.1:9/probe"

EXPECTED_LIVENESS = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 60_000,
}


class _ConnectCaptured(Exception):
    def __init__(self, cparams: dict):
        super().__init__("connect params captured")
        self.cparams = cparams


def _connect_params(engine) -> dict:
    @event.listens_for(engine, "do_connect")
    def _capture(dialect, conn_rec, cargs, cparams):
        raise _ConnectCaptured(dict(cparams))

    try:
        with pytest.raises(_ConnectCaptured) as captured:
            engine.connect()
    finally:
        engine.dispose()
    return captured.value.cparams


def _liveness_subset(cparams: dict) -> dict:
    return {key: cparams.get(key) for key in EXPECTED_LIVENESS}


def test_capture_harness_detects_missing_liveness_args():
    # Negative control: an engine built without the liveness args must show
    # none of them, or the assertions below could pass vacuously.
    cparams = _connect_params(create_engine(PG_URL))

    assert _liveness_subset(cparams) == dict.fromkeys(EXPECTED_LIVENESS)


@pytest.mark.parametrize(
    "admin_url",
    [
        PG_URL,
        "postgresql+psycopg2://probe@127.0.0.1:9/probe",
        "postgresql+psycopg://probe@127.0.0.1:9/probe",
        # Rewritten to psycopg before the engine is built; the liveness args
        # must follow the rewritten URL, not the asyncpg original.
        "postgresql+asyncpg://probe@127.0.0.1:9/probe",
    ],
)
def test_admin_engine_passes_liveness_args(monkeypatch, admin_url):
    monkeypatch.setenv("ADMIN_DATABASE_URL", admin_url)

    engine = admin_database._create_engine()
    assert engine.dialect.driver == "psycopg"
    cparams = _connect_params(engine)

    assert _liveness_subset(cparams) == EXPECTED_LIVENESS
    # Supabase transaction-pooler setting survives the merge.
    assert "prepare_threshold" in cparams
    assert cparams["prepare_threshold"] is None


def test_admin_sqlite_engine_gets_no_libpq_args(monkeypatch):
    # sqlite3.connect() rejects libpq keywords; the SQLite path must stay as is.
    monkeypatch.setenv("ADMIN_DATABASE_URL", "sqlite://")

    cparams = _connect_params(admin_database._create_engine())

    assert _liveness_subset(cparams) == dict.fromkeys(EXPECTED_LIVENESS)
    assert cparams["check_same_thread"] is False
