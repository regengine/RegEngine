"""Audited tenant-id discovery for cross-tenant maintenance orchestration.

The ordinary ``DATABASE_URL`` role never receives a global tenant-table RLS
branch.  A background job that must iterate tenants obtains only their UUIDs
through ``ADMIN_DATABASE_URL`` and then performs each data operation in a
fresh transaction scoped to that UUID.
"""

from __future__ import annotations

import os

from shared.db_url import sync_postgres_connect_args, sync_postgres_url
from sqlalchemy import create_engine, text


def list_maintenance_tenant_ids(admin_database_url: str | None = None, *, limit: int | None = None) -> list[str]:
    """Return tenant UUIDs through the exact non-bypass sysadmin credential.

    The posture check and transaction-local control-plane GUC are part of the
    same transaction as the read.  A runtime/owner/misconfigured URL fails
    closed; no fallback to ``DATABASE_URL`` exists.
    """
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("maintenance tenant limit must be a positive integer")
    url = admin_database_url or os.getenv("ADMIN_DATABASE_URL", "")
    if not url:
        raise RuntimeError("ADMIN_DATABASE_URL is required for tenant maintenance discovery")

    sync_url = sync_postgres_url(url)
    engine = create_engine(sync_url, pool_pre_ping=True, connect_args=sync_postgres_connect_args(sync_url))
    try:
        with engine.begin() as connection:
            posture = connection.execute(
                text(
                    """
                    SELECT current_user, rolsuper, rolbypassrls
                      FROM pg_roles
                     WHERE rolname = current_user
                    """
                )
            ).one()
            if posture != ("regengine_sysadmin", False, False):
                raise RuntimeError(
                    "tenant maintenance discovery requires the exact NOSUPERUSER/NOBYPASSRLS regengine_sysadmin role"
                )
            connection.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))
            return [
                str(value)
                for value in connection.execute(
                    text("SELECT id FROM public.tenants ORDER BY id LIMIT :limit"),
                    {"limit": limit},
                ).scalars()
            ]
    finally:
        engine.dispose()
