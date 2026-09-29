"""The DB-backed API-key store bounds connects and commands on asyncpg.

2026-09-28: a Railway Postgres restart black-holed the old container's
address, and any connection opened in that window hung until the kernel gave
up. The store rewrites every Postgres URL to asyncpg, which ignores the libpq
liveness keywords, so it needs asyncpg's own ``timeout`` (connect) and
``command_timeout`` (every operation, including the pool pre-ping).

Production always uses this store for API-key auth (``shared.auth.get_key_store``
under ``requires_strict_auth_runtime()``), and the admin key-management store is
a second instance built with ``arm_sysadmin_rls=True``.

The ``do_connect`` hook fires before any network I/O, so no database is needed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_LIVENESS = {"timeout": 10, "command_timeout": 30}
# #1874: Supabase pgbouncer transaction mode needs asyncpg's statement cache off.
EXPECTED_PGBOUNCER = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}

PROD_URL_FORMS = [
    "postgresql://probe@127.0.0.1:9/probe",
    "postgresql+psycopg2://probe@127.0.0.1:9/probe",
    "postgresql+asyncpg://probe@127.0.0.1:9/probe",
]


class _ConnectCaptured(Exception):
    def __init__(self, params: dict):
        super().__init__("connect params captured")
        self.params = params


async def _connect_params(async_engine) -> dict:
    @event.listens_for(async_engine.sync_engine, "do_connect")
    def _capture(dialect, conn_rec, cargs, cparams):
        raise _ConnectCaptured(dict(cparams))

    try:
        with pytest.raises(_ConnectCaptured) as captured:
            async with async_engine.connect():
                pass
    finally:
        await async_engine.dispose()
    return captured.value.params


def _subset(params: dict, expected: dict) -> dict:
    return {key: params.get(key) for key in expected}


def test_asyncpg_liveness_args_values():
    from shared.db_liveness import asyncpg_liveness_connect_args

    assert asyncpg_liveness_connect_args() == EXPECTED_LIVENESS


@pytest.mark.parametrize("arm_sysadmin_rls", [False, True], ids=["tenant_store", "admin_store"])
@pytest.mark.parametrize("url", PROD_URL_FORMS)
async def test_store_engine_passes_liveness_and_pgbouncer_args(url, arm_sysadmin_rls):
    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore(database_url=url, arm_sysadmin_rls=arm_sysadmin_rls)
    assert store._engine.dialect.driver == "asyncpg"

    params = await _connect_params(store._engine)

    assert _subset(params, EXPECTED_LIVENESS) == EXPECTED_LIVENESS
    assert _subset(params, EXPECTED_PGBOUNCER) == EXPECTED_PGBOUNCER
    # Pool sizing is unchanged.
    assert store._engine.pool.size() == 5
    assert store._engine.pool._max_overflow == 10


async def test_sslmode_url_keeps_ssl_alongside_liveness_args():
    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore(database_url="postgresql://probe@127.0.0.1:9/probe?sslmode=require")

    params = await _connect_params(store._engine)

    assert params.get("ssl") == "require"
    assert _subset(params, EXPECTED_LIVENESS) == EXPECTED_LIVENESS
    assert _subset(params, EXPECTED_PGBOUNCER) == EXPECTED_PGBOUNCER


async def test_liveness_args_reach_asyncpg_connect(monkeypatch):
    # SQLAlchemy's asyncpg adapter pops some keywords before calling
    # asyncpg.connect(); prove these two survive to the driver.
    import asyncpg
    from shared.api_key_store import DatabaseAPIKeyStore

    async def _capturing_connect(*args, **kwargs):
        raise _ConnectCaptured(kwargs)

    monkeypatch.setattr(asyncpg, "connect", _capturing_connect)
    store = DatabaseAPIKeyStore(database_url=PROD_URL_FORMS[0])

    try:
        with pytest.raises(_ConnectCaptured) as captured:
            async with store._engine.connect():
                pass
    finally:
        await store._engine.dispose()

    assert _subset(captured.value.params, EXPECTED_LIVENESS) == EXPECTED_LIVENESS
    assert captured.value.params.get("statement_cache_size") == 0


async def test_bare_asyncpg_engine_has_no_liveness_args():
    # Negative control: the capture sees nothing the store did not add.
    params = await _connect_params(create_async_engine(PROD_URL_FORMS[-1]))

    assert not set(EXPECTED_LIVENESS) & set(params)
    assert not set(EXPECTED_PGBOUNCER) & set(params)


async def test_sqlite_store_gets_no_asyncpg_args():
    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore(database_url="sqlite+aiosqlite:///:memory:")

    params = await _connect_params(store._engine)

    assert not set(EXPECTED_LIVENESS) & set(params)
    assert not set(EXPECTED_PGBOUNCER) & set(params)
