"""Disposable per-suite PostgreSQL databases.

``rls_db.rls_postgres_or_skip`` hands back whatever live Postgres is
available — in CI that is the shared service container the rest of the job
is also using, and outside CI it may be a scratch DB pointed at by
``REGENGINE_MIGRATION_TEST_DB``. A suite that needs to CREATE or DROP a
real table (rather than only read one) must not do that in a shared
database: dropping ``fsma.task_queue`` out from under a concurrently
running migration gate breaks it in ways that are painful to attribute.

This module creates a brand-new database on the same server, hands back an
engine bound to it, and drops it afterwards. Nothing the suite does can
reach the database it borrowed the connection details from.

Skips (or fails, under ``REGENGINE_REQUIRE_DB=1``) when the connecting
role may not create databases.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from tests.migrations.rls_db import _normalize_psycopg, rls_postgres_or_skip, skip_or_fail_db

# Database names are interpolated into DDL (they cannot be bound), so they
# are restricted to an obviously-safe identifier shape rather than quoted
# and hoped for.
_SAFE_NAME = re.compile(r"\A[a-z][a-z0-9_]{0,62}\Z")

# Connecting to the database being dropped is not allowed, so admin DDL is
# issued against a maintenance database that no suite targets.
_MAINTENANCE_DB = "postgres"


@contextmanager
def scratch_database_engine(db_name: str) -> Iterator[Engine]:
    """Yield an Engine bound to a freshly created, disposable database.

    The database is dropped on exit, including after a failure, so a
    crashed suite does not leave state behind for the next run.
    """
    if not _SAFE_NAME.match(db_name):
        raise ValueError(f"unsafe scratch database name: {db_name!r}")

    with rls_postgres_or_skip() as (plain_url, _engine):
        url = make_url(plain_url)
        if (url.database or "") == db_name:
            raise ValueError(f"scratch database {db_name!r} must differ from the borrowed database")

        admin_url = _normalize_psycopg(url.set(database=_MAINTENANCE_DB).render_as_string(hide_password=False))
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        created = False
        try:
            try:
                with admin.connect() as conn:
                    conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db_name}"')
                    conn.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
                created = True
            except Exception as exc:  # insufficient privilege, maintenance DB absent, ...
                skip_or_fail_db(f"cannot create a disposable database {db_name!r}: {exc}")
                return

            target = create_engine(
                _normalize_psycopg(url.set(database=db_name).render_as_string(hide_password=False)), future=True
            )
            try:
                yield target
            finally:
                target.dispose()
        finally:
            if created:
                try:
                    with admin.connect() as conn:
                        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
                except Exception:  # pragma: no cover - best effort cleanup
                    pass
            admin.dispose()
