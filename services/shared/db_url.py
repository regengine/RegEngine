"""One synchronous Postgres driver for every SQLAlchemy engine: psycopg 3.

A bare ``postgresql://`` URL makes SQLAlchemy pick psycopg2, so engines built
from ``DATABASE_URL`` ran psycopg2 while the admin engine ran psycopg 3.
``sync_postgres_url`` pins the driver so the whole process uses psycopg 3 and
psycopg2 is not a dependency.

``sync_postgres_connect_args`` adds ``prepare_threshold=None`` to the libpq
liveness args. psycopg2 never creates server-side prepared statements;
psycopg 3 does after five executions by default, which breaks behind a
transaction-mode pooler (Supabase/PgBouncer) that hands each transaction a
different backend. The admin engine has run with this setting since it moved
to psycopg 3.
"""

from __future__ import annotations

from shared.db_liveness import postgres_liveness_connect_args

_PSYCOPG_PREFIX = "postgresql+psycopg://"

# Schemes rewritten to psycopg 3. ``postgres://`` is the Heroku/Railway alias
# that SQLAlchemy 2 rejects; asyncpg URLs are rewritten for sync callers that
# share an async-configured variable.
_REWRITE_PREFIXES = (
    "postgresql+psycopg2://",
    "postgresql+asyncpg://",
    "postgresql://",
    "postgres://",
)


def sync_postgres_url(url: str) -> str:
    """Return ``url`` with the psycopg 3 driver for any Postgres scheme.

    Non-Postgres URLs (SQLite in tests) are returned unchanged.
    """
    url = str(url)
    for prefix in _REWRITE_PREFIXES:
        if url.startswith(prefix):
            return _PSYCOPG_PREFIX + url[len(prefix) :]
    return url


def sync_postgres_connect_args(url: str) -> dict:
    """Return ``connect_args`` for a psycopg 3 engine, else ``{}``.

    Liveness args bound each connect and detect a dead peer; see
    ``shared.db_liveness``. ``prepare_threshold=None`` keeps statements
    unprepared, matching psycopg2 behaviour; see the module docstring.
    """
    url = str(url)
    if not url.startswith(_PSYCOPG_PREFIX):
        return postgres_liveness_connect_args(url)
    return {"prepare_threshold": None, **postgres_liveness_connect_args(url)}
