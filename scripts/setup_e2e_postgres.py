#!/usr/bin/env python3
"""Migrate the isolated local Playwright database before starting its servers."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# CI-only fake password for the NOSUPERUSER/NOBYPASSRLS regengine_sysadmin
# LOGIN used by ADMIN_DATABASE_URL in Passwordless Auth E2E. Never a real
# production secret — gitleaks allowlisted with reason.
_CI_E2E_SYSADMIN_PASSWORD = "ci-e2e-only-sysadmin-not-a-real-secret"  # pragma: allowlist secret — CI-only fake password for Playwright E2E regengine_sysadmin LOGIN; never used in production


def _enable_e2e_sysadmin_login(engine: Engine) -> None:
    """Flip the provisioned NOLOGIN sysadmin role to a CI-only LOGIN.

    ``_provision_cluster`` creates ``regengine_sysadmin`` as NOLOGIN so
    migrations can GRANT to it. The admin API-key store then requires an
    actual connection as that NOSUPERUSER/NOBYPASSRLS role — enable LOGIN
    with an obviously fake CI password and grant CONNECT on the E2E DB.
    """
    # Build the ALTER from the CI-only constant. Single-quote doubling is the
    # only escaping needed for a SQL string literal; parameterized ALTER ROLE
    # PASSWORD is not portable across drivers.
    pw_literal = _CI_E2E_SYSADMIN_PASSWORD.replace("'", "''")
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER ROLE regengine_sysadmin WITH LOGIN "
                f"PASSWORD '{pw_literal}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"
            )
        )
        conn.execute(
            text("GRANT CONNECT ON DATABASE playwright_shared TO regengine_sysadmin")
        )


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
    # After migrations GRANT to the role, enable the CI-only LOGIN that
    # ADMIN_DATABASE_URL points at in frontend-ci.yml / start-e2e-backend.sh.
    engine = create_engine(target.set(drivername="postgresql+psycopg"))
    try:
        _enable_e2e_sysadmin_login(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
