"""Graph-service Postgres engines bound connects and detect dead peers.

2026-09-28: a Railway Postgres restart black-holed the old container's
address. The FSMA audit-trail engine and the recall-drill persistence engine
passed libpq no ``connect_timeout`` and no TCP keepalives, so any connection
opened in that window waited on the kernel default (keepalive idle 7200 s)
and hung the request that opened it.

Each test captures the kwargs SQLAlchemy hands the DBAPI ``connect()``
(the ``do_connect`` hook fires before any network I/O, so no database is
needed) and asserts the libpq liveness settings are among them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event

from services.graph.app import fsma_audit
from services.graph.app.fsma_recall import persistence

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


@pytest.fixture
def fresh_audit_engine(monkeypatch):
    """Drop the cached audit engine; monkeypatch restores it afterwards."""
    monkeypatch.setattr(fsma_audit, "_db_engine", None)


def test_capture_harness_detects_missing_liveness_args():
    # Negative control: an engine built without the liveness args must show
    # none of them, or the assertions below could pass vacuously.
    cparams = _connect_params(create_engine(PG_URL.replace("postgresql://", "postgresql+psycopg://", 1)))

    assert _liveness_subset(cparams) == dict.fromkeys(EXPECTED_LIVENESS)


def test_audit_engine_passes_liveness_args(monkeypatch, fresh_audit_engine):
    monkeypatch.setenv("DATABASE_URL", PG_URL)

    engine = fsma_audit._get_audit_db_engine()
    assert engine is not None
    assert engine.dialect.driver == "psycopg"

    cparams = _connect_params(engine)
    assert _liveness_subset(cparams) == EXPECTED_LIVENESS
    # psycopg 3 must not prepare statements (transaction-mode pooler).
    assert "prepare_threshold" in cparams and cparams["prepare_threshold"] is None


def test_audit_sqlite_engine_gets_no_libpq_args(monkeypatch, fresh_audit_engine):
    # sqlite3.connect() rejects libpq keywords; the SQLite test path must stay as is.
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    engine = fsma_audit._get_audit_db_engine()
    assert engine is not None

    assert _liveness_subset(_connect_params(engine)) == dict.fromkeys(EXPECTED_LIVENESS)


def test_recall_persistence_engine_passes_liveness_args(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)

    engine = persistence._get_db_engine()
    assert engine is not None
    assert engine.dialect.driver == "psycopg"

    cparams = _connect_params(engine)
    assert _liveness_subset(cparams) == EXPECTED_LIVENESS
    # psycopg 3 must not prepare statements (transaction-mode pooler).
    assert "prepare_threshold" in cparams and cparams["prepare_threshold"] is None
