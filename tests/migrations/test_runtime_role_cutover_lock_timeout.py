"""The per-deploy runtime-role cutover gives up on a held table lock, and changes nothing.

``scripts/apply_runtime_role_cutover.py`` runs after every migration run while
the previous deployment still serves traffic. Its ``ALTER TABLE ... ROW LEVEL
SECURITY`` and policy statements take ACCESS EXCLUSIVE on ``public.api_keys``
among others. Unbounded, one open reader of that table made the cutover wait
for it indefinitely, and every API-key lookup queued behind the pending lock.

CI runs this in live-db-suite with the migration owner and provider
credentials. It changes grants and restores them before it returns.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply_runtime_role_cutover.py"
OWNER_URL = os.getenv("MIGRATIONS_DATABASE_URL")
ROLE_ADMIN_URL = os.getenv("ROLE_ADMIN_DATABASE_URL")
# A runtime grant outside the v111 inventory: the cutover must revoke it.
DRIFT_TABLE = "public.tool_leads"

pytestmark = pytest.mark.skipif(
    not (OWNER_URL and ROLE_ADMIN_URL),
    reason="migration-owner and provider role-admin PostgreSQL URLs are required",
)


def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        .replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        .replace("postgresql://", "postgresql+psycopg://", 1)
    )


def _run_cutover(lock_timeout: str) -> tuple[subprocess.CompletedProcess, float]:
    env = dict(os.environ, REGENGINE_CUTOVER_LOCK_TIMEOUT=lock_timeout)
    started = time.monotonic()
    # An unbounded wait shows up as TimeoutExpired: the blocker below is held
    # until the test releases it.
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
    return result, time.monotonic() - started


def _runtime_can_read_drift_table(engine) -> bool:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT has_table_privilege('regengine', :table, 'SELECT')"), {"table": DRIFT_TABLE}
        ).scalar_one()


def test_held_lock_refuses_fast_rolls_back_and_later_run_repairs():
    owner = create_engine(_sync_url(OWNER_URL), pool_pre_ping=True)
    provider = create_engine(_sync_url(ROLE_ADMIN_URL), pool_pre_ping=True)
    blocker = provider.connect()
    try:
        assert not _runtime_can_read_drift_table(owner)
        with owner.begin() as connection:
            connection.execute(text(f"GRANT SELECT ON {DRIFT_TABLE} TO regengine"))
        assert _runtime_can_read_drift_table(owner)

        # An open reader of api_keys, as a long request in the old deployment.
        blocker_transaction = blocker.begin()
        blocker.execute(text("LOCK TABLE public.api_keys IN ACCESS SHARE MODE"))

        refused, elapsed = _run_cutover("500ms")
        assert refused.returncode == 75, refused.stderr
        assert "did not get its table lock within 500ms" in refused.stderr
        assert "Nothing was changed" in refused.stderr
        assert "runtime role cutover applied" not in refused.stdout
        assert elapsed < 60, elapsed
        # One transaction: the stray grant survives the refused run.
        assert _runtime_can_read_drift_table(owner)

        blocker_transaction.rollback()
        applied, _ = _run_cutover("10s")
        assert applied.returncode == 0, applied.stderr
        assert "runtime role cutover applied" in applied.stdout
        assert not _runtime_can_read_drift_table(owner)
    finally:
        blocker.close()
        with owner.begin() as connection:
            connection.execute(text(f"REVOKE SELECT ON {DRIFT_TABLE} FROM regengine"))
        owner.dispose()
        provider.dispose()
