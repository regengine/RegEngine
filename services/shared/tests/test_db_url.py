"""Every sync Postgres engine uses psycopg 3; psycopg2 is not a dependency.

A bare ``postgresql://`` URL makes SQLAlchemy load psycopg2, so the helper
must rewrite every Postgres scheme, and the psycopg 3 connect args must keep
statements unprepared (psycopg2 never prepared them; a transaction-mode
pooler breaks on prepared statements).
"""

from __future__ import annotations

import pytest
from shared.db_url import sync_postgres_connect_args, sync_postgres_url

REST = "u:p@h:5432/db?sslmode=require"


@pytest.mark.parametrize(
    "scheme",
    ["postgres", "postgresql", "postgresql+psycopg2", "postgresql+asyncpg", "postgresql+psycopg"],
)
def test_every_postgres_scheme_becomes_psycopg(scheme):
    assert sync_postgres_url(f"{scheme}://{REST}") == f"postgresql+psycopg://{REST}"


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "sqlite://", "mysql://u@h/db"])
def test_non_postgres_urls_unchanged(url):
    assert sync_postgres_url(url) == url


def test_psycopg_connect_args_disable_prepared_statements_and_bound_liveness():
    args = sync_postgres_connect_args("postgresql+psycopg://u@h/db")

    assert "prepare_threshold" in args and args["prepare_threshold"] is None
    assert args["connect_timeout"] == 10
    assert args["tcp_user_timeout"] == 60_000


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "postgresql+asyncpg://u@h/db"])
def test_non_psycopg_urls_get_no_psycopg_args(url):
    assert sync_postgres_connect_args(url) == {}


def test_bare_postgres_url_engine_loads_psycopg_not_psycopg2():
    from sqlalchemy import create_engine

    url = sync_postgres_url("postgresql://probe@127.0.0.1:9/probe")
    engine = create_engine(url, connect_args=sync_postgres_connect_args(url))
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_shared_engine_driver():
    from shared import database

    if database.engine.dialect.name != "postgresql":
        pytest.skip("DATABASE_URL is not Postgres in this run")
    assert database.engine.dialect.driver == "psycopg"
