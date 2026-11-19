"""Live-Postgres: scripts/create_test_api_key.py seeds its tenant as regengine_sysadmin.

Since v111 a ``tenants`` row is admitted only from ``regengine_sysadmin`` with
``regengine.is_sysadmin`` armed for the transaction. The script used to seed
as the runtime role and failed with "permission denied for table tenants" on
every migrated database, and no DB-free test can see a grant or a policy.

Each case runs the script's own helpers under ``SET LOCAL ROLE`` and rolls
back. Requires a designated live test DB (same guards as the other
tests/shared/*_live.py suites).
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from shared.db_url import sync_postgres_url
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.migrations.rls_db import guarded_live_database_url, skip_or_fail_without_db

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) "
        "— skipping create_test_api_key live test"
    ),
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_test_api_key.py"
TENANT_NAME = "create_test_api_key live"


def _script():
    name = "create_test_api_key_live"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # The script defines a dataclass, which needs its module registered.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture()
def conn():
    """A connection in a transaction that is always rolled back."""
    engine = create_engine(sync_postgres_url(DATABASE_URL))
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                for role in ("regengine", "regengine_sysadmin"):
                    present = connection.execute(
                        text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
                    ).scalar()
                    if not present:
                        skip_or_fail_without_db(f"{role} role not present in this database")
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_sysadmin_seeds_the_tenant_once_the_branch_is_armed(conn) -> None:
    script = _script()
    tenant_id = str(uuid.uuid4())

    conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))
    script._arm_sysadmin(conn)

    assert script._seed_tenant(conn, tenant_id, TENANT_NAME) is True
    assert script._seed_tenant(conn, tenant_id, TENANT_NAME) is False, "a second run must be a no-op"
    status = conn.execute(text("SELECT status FROM tenants WHERE id = :id"), {"id": tenant_id}).scalar()
    assert status == "active"


def test_sysadmin_role_alone_cannot_seed_the_tenant(conn) -> None:
    """Dropping the arm from the script must fail here, not in a developer's shell."""
    script = _script()

    conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))

    with pytest.raises(DBAPIError, match="row-level security"):
        script._seed_tenant(conn, str(uuid.uuid4()), TENANT_NAME)


def test_runtime_role_is_refused_before_any_write(conn) -> None:
    script = _script()

    conn.execute(text("SET LOCAL ROLE regengine"))

    with pytest.raises(SystemExit, match="logs in as 'regengine'"):
        script._arm_sysadmin(conn)
