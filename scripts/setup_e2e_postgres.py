#!/usr/bin/env python3
"""Migrate the isolated local Playwright database before starting its servers."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    url = os.environ.get("DATABASE_URL", "")
    target = make_url(url)
    if (
        os.getenv("REGENGINE_E2E_MODE") != "true"
        or os.getenv("REGENGINE_ENV") != "test"
        or target.host not in {"localhost", "127.0.0.1"}
        or target.database != "playwright_shared"
        or target.get_backend_name() != "postgresql"
    ):
        raise SystemExit("Refusing to prepare anything except the local playwright_shared E2E database")
    from tests.migrations.test_seeded_mid_chain_upgrade import _provision_cluster

    engine = create_engine(target.set(drivername="postgresql+psycopg"))  # psycopg (v3); psycopg2 is not installed
    try:
        _provision_cluster(engine, engine)
    finally:
        engine.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=os.environ | {"MIGRATIONS_DATABASE_URL": url},
        check=True,
    )


if __name__ == "__main__":
    main()
