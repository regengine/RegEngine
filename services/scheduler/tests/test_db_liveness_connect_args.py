"""Every Postgres engine a scheduler job touches bounds connects and detects dead peers.

2026-09-28: a Railway Postgres restart left the remediation notification
drain job (``max_instances=1``) blocked on a half-open socket, because the
shared engine passed libpq no ``connect_timeout`` and no TCP keepalives.
Every later tick was skipped until the service was redeployed.

Each test captures the kwargs SQLAlchemy hands the DBAPI ``connect()``
(the ``do_connect`` hook fires before any network I/O, so no database is
needed) and asserts the libpq liveness settings are among them.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event

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


def _capture_connect_params(engine) -> None:
    @event.listens_for(engine, "do_connect")
    def _capture(dialect, conn_rec, cargs, cparams):
        raise _ConnectCaptured(dict(cparams))


def _connect_params(engine) -> dict:
    _capture_connect_params(engine)
    try:
        with pytest.raises(_ConnectCaptured) as captured:
            engine.connect()
    finally:
        engine.dispose()
    return captured.value.cparams


def _liveness_subset(cparams: dict) -> dict:
    return {key: cparams.get(key) for key in EXPECTED_LIVENESS}


def test_liveness_args_only_for_libpq_urls():
    from shared.db_liveness import postgres_liveness_connect_args

    for url in (PG_URL, "postgresql+psycopg2://u@h/db", "postgresql+psycopg://u@h/db"):
        assert postgres_liveness_connect_args(url) == EXPECTED_LIVENESS
    # SQLite (tests) and asyncpg reject libpq keywords.
    assert postgres_liveness_connect_args("sqlite:///:memory:") == {}
    assert postgres_liveness_connect_args("postgresql+asyncpg://u@h/db") == {}


def test_shared_engine_passes_liveness_args_to_psycopg2():
    from shared import database

    kwargs = database._build_engine_kwargs(PG_URL)
    cparams = _connect_params(create_engine(PG_URL, **kwargs))

    assert _liveness_subset(cparams) == EXPECTED_LIVENESS
    # Pre-existing pool behavior is unchanged.
    assert kwargs["pool_pre_ping"] is True
    assert "connect_args" not in database._build_engine_kwargs("sqlite:///:memory:")


def test_maintenance_tenant_discovery_engine_passes_liveness_args(monkeypatch):
    from shared import maintenance_tenants

    real_create_engine = maintenance_tenants.create_engine

    def _capturing_create_engine(url, **kwargs):
        engine = real_create_engine(url, **kwargs)
        _capture_connect_params(engine)
        return engine

    monkeypatch.setattr(maintenance_tenants, "create_engine", _capturing_create_engine)

    with pytest.raises(_ConnectCaptured) as captured:
        maintenance_tenants.list_maintenance_tenant_ids(PG_URL)

    assert _liveness_subset(captured.value.cparams) == EXPECTED_LIVENESS


def test_scheduler_state_engine_passes_liveness_args():
    from app.state import StateManager

    manager = StateManager(database_url=PG_URL)
    manager.initialize()

    assert _liveness_subset(_connect_params(manager.engine)) == EXPECTED_LIVENESS


def test_compliance_integration_engine_passes_liveness_args(monkeypatch):
    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = PG_URL
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)

    integration = ci_module.ComplianceIntegration()

    assert _liveness_subset(_connect_params(integration.engine)) == EXPECTED_LIVENESS


def test_leader_election_engine_passes_liveness_args(monkeypatch):
    # The election loop and the lock heartbeat both connect through this
    # engine; on 2026-09-28 their reconnects hung too.
    from app import distributed

    fake_settings = MagicMock()
    fake_settings.database_url = PG_URL
    monkeypatch.setattr(distributed, "get_settings", lambda: fake_settings)

    context = distributed.DistributedContext()

    assert _liveness_subset(_connect_params(context.engine)) == EXPECTED_LIVENESS
