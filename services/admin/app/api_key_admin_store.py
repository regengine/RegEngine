"""Dedicated API-key store for high-assurance human administration.

Tenant credential validation deliberately remains on ``DATABASE_URL``. Human
global key management instead uses an independent async pool constructed from
``ADMIN_DATABASE_URL`` and arms only the ``regengine_sysadmin`` RLS branch.
"""

from __future__ import annotations

import os
import threading
from typing import Union

from shared.api_key_store import DatabaseAPIKeyStore
from shared.auth import APIKeyStore, get_key_store
from shared.env import requires_strict_auth_runtime

AdminAPIKeyStore = Union[APIKeyStore, DatabaseAPIKeyStore]

_admin_api_key_store: DatabaseAPIKeyStore | None = None
_admin_api_key_store_lock = threading.Lock()


def _database_admin_store_required() -> bool:
    return (
        requires_strict_auth_runtime()
        or os.getenv("ENABLE_DB_API_KEYS", "false").strip().lower() == "true"
    )


def get_admin_api_key_store() -> AdminAPIKeyStore:
    """Return the isolated admin store, or the explicit local/test fallback."""
    if not _database_admin_store_required():
        return get_key_store()

    admin_database_url = os.getenv("ADMIN_DATABASE_URL", "").strip()
    if not admin_database_url:
        raise RuntimeError(
            "ADMIN_DATABASE_URL is required for database-backed admin API-key management"
        )

    global _admin_api_key_store
    with _admin_api_key_store_lock:
        if _admin_api_key_store is None:
            _admin_api_key_store = DatabaseAPIKeyStore(
                database_url=admin_database_url,
                arm_sysadmin_rls=True,
            )
        return _admin_api_key_store


async def close_admin_api_key_store() -> None:
    """Dispose the dedicated admin pool during application shutdown."""
    global _admin_api_key_store
    with _admin_api_key_store_lock:
        store = _admin_api_key_store
        _admin_api_key_store = None
    if store is not None:
        await store.close()
