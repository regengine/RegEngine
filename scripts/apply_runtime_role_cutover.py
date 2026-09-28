#!/usr/bin/env python3
"""Idempotently reapply the v111 runtime-role cutover as schema owner.

Normal deploys receive the same statements through ``alembic upgrade head``,
and ``scripts/run-migrations.sh`` reruns this command after every migration
run, so v111's closed inventory is the whole runtime grant surface: a grant
applied only by a later migration is revoked here. It also serves an audited
repair after privilege drift or a migration schema-owner change; it never
prints a connection URL or credential.

It runs while the previous deployment still serves traffic, and several of
its statements take ACCESS EXCLUSIVE locks (``ALTER TABLE ... ROW LEVEL
SECURITY`` and ``DROP``/``CREATE POLICY``, on ``public.api_keys`` among
others). Unbounded, one long transaction on such a table made the cutover
wait for it to end, and every request touching that table queued behind the
pending lock meanwhile. So each lock wait is capped (``lock_timeout``, 10s
like the migrations' own); on timeout the whole cutover rolls back and the
command exits 75, which fails the deploy and leaves the old deployment
serving.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

LOCK_TIMEOUT_ENV = "REGENGINE_CUTOVER_LOCK_TIMEOUT"
DEFAULT_LOCK_TIMEOUT = "10s"
LOCK_NOT_AVAILABLE = "55P03"  # SQLSTATE raised when lock_timeout expires
EX_TEMPFAIL = 75  # run-migrations.sh's advisory-lock timeout uses it too


def _migration_url() -> str:
    url = os.getenv("MIGRATIONS_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "MIGRATIONS_DATABASE_URL is required; refusing to use a runtime credential"
        )
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _first_sql_line(statement: str) -> str:
    """The statement's first non-comment line: SQL text, never a credential."""
    for line in statement.splitlines():
        line = line.strip()
        if line and not line.startswith("--"):
            return line[:120]
    return ""


def main() -> int:
    # The repair helper is an owner-only operation in every environment. Set
    # this before loading v111 because the revision builds its SQL guard at
    # import time from the exact MIGRATIONS_DATABASE_URL login identity.
    os.environ["REGENGINE_ENFORCE_MIGRATION_ROLE"] = "1"
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260803_b71d9e4c2a60_v111_runtime_role_grants.py"
    )
    spec = importlib.util.spec_from_file_location("regengine_v111_cutover", migration_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load v111 cutover from {migration_path}")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    lock_timeout = os.getenv(LOCK_TIMEOUT_ENV, "").strip() or DEFAULT_LOCK_TIMEOUT
    statements = migration.CUTOVER_STATEMENTS
    current = 0
    engine = create_engine(_migration_url(), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            # Transaction-local: it ends with the cutover's single transaction.
            connection.execute(
                text("SELECT set_config('lock_timeout', :value, true)"),
                {"value": lock_timeout},
            )
            identity = connection.execute(
                text("SELECT current_user, current_database()")
            ).one()
            for current, statement in enumerate(statements, start=1):
                connection.execute(text(statement))
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        where = (
            f"statement {current} of {len(statements)} ({_first_sql_line(statements[current - 1])!r})"
            if current
            else "the cutover"
        )
        print(
            f"runtime role cutover refused: {where} did not get its table lock "
            f"within {lock_timeout} ({LOCK_TIMEOUT_ENV}). Nothing was changed: the "
            "cutover is one transaction and it rolled back. A long-running transaction "
            "holds a table the cutover alters; find it in pg_stat_activity (oldest "
            "xact_start) and redeploy once it has ended.",
            file=sys.stderr,
        )
        return EX_TEMPFAIL
    finally:
        engine.dispose()
    print(
        "runtime role cutover applied "
        f"as role={identity.current_user} database={identity.current_database}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
