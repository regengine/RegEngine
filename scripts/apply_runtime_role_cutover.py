#!/usr/bin/env python3
"""Idempotently reapply the v111 runtime-role cutover as schema owner.

Normal deploys receive the same statements through ``alembic upgrade head``.
This command exists for an audited repair after privilege drift or a migration
schema-owner change; it never prints a connection URL or credential.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


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
    engine = create_engine(_migration_url(), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            identity = connection.execute(
                text("SELECT current_user, current_database()")
            ).one()
            for statement in migration.CUTOVER_STATEMENTS:
                connection.execute(text(statement))
        print(
            "runtime role cutover applied "
            f"as role={identity.current_user} database={identity.current_database}"
        )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
