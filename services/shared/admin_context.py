"""Transaction-local helpers for explicitly classified admin authority.

This module deliberately has no engine or environment initialization. Shared
workers receive an already-selected admin session/connection and can arm that
one transaction without importing the admin service's module-level engine.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


def _is_sqlite(db_session: Any) -> bool:
    bind = getattr(db_session, "bind", None) or getattr(db_session, "engine", None)
    return bind is not None and getattr(bind.dialect, "name", None) == "sqlite"


def arm_global_admin_context(db_session: Any) -> None:
    """Explicitly arm one classified global control-plane transaction."""

    if _is_sqlite(db_session):
        db_session.info["is_admin"] = True
        return
    db_session.execute(text("SELECT set_config('regengine.is_sysadmin', 'true', true)"))


def disarm_global_admin_context(db_session: Any) -> None:
    """Force the current transaction back to tenant-scoped posture."""

    if _is_sqlite(db_session):
        db_session.info["is_admin"] = False
        return
    db_session.execute(text("SELECT set_config('regengine.is_sysadmin', 'false', true)"))


def bind_authenticated_user_context(db_session: Any, user_id: Any) -> None:
    """Bind self-service RLS policies to one verified user for this transaction."""

    if _is_sqlite(db_session):
        db_session.info["authenticated_user_id"] = str(user_id)
        return
    db_session.execute(
        text("SELECT set_config('regengine.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
