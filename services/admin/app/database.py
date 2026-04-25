"""Database utilities for the admin service.

Security note (#1381 -- pooled connection tenant bleed):

``TenantContext.set_tenant_context`` uses ``set_config(name, val,
false)`` where the third arg is "is_local" -- ``false`` means the GUC
persists for the LIFETIME OF THE CONNECTION, not the transaction. When
the FastAPI session closes and the connection returns to the
``SessionLocal`` pool, the previous tenant's ``app.tenant_id`` is still
set. The next unrelated request that picks up that connection inherits
the stale tenant context before any new set_tenant_context runs. A
route that does NOT set context (``/health``, pre-auth paths, or a
broken auth dep that raises after an early DB call) then reads under
the previous tenant's RLS.

Mitigation (this module): a ``connect`` + ``checkout`` event listener
on the engine's connection pool runs
``SELECT set_config('app.tenant_id', '', false)`` and
``SELECT set_config('regengine.is_sysadmin', 'false', false)``
BEFORE the session sees the connection. This guarantees every route
starts from a clean slate; authenticated routes re-set tenant context
as the first step, and unauthenticated paths are genuinely scoped to
"no tenant" rather than inheriting the neighbor's.

Complementary: ``get_tenant_session`` (and the ``_session_scope``
inside ``HallucinationTracker``) use ``SET LOCAL`` which is
transaction-local and auto-cleared on COMMIT/ROLLBACK -- preferred for
new code.
"""

from __future__ import annotations

import os
from typing import Iterator, AsyncIterator

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger("admin-db")


def _sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _create_engine():
    """Create the Admin database engine for core tables (users, tenants, roles)."""
    database_url = os.getenv("ADMIN_DATABASE_URL")
    if database_url:
        sqlalchemy_url = _sqlalchemy_url(database_url)
        logger.info("admin_database_configured", url=database_url.split("@")[-1])
        # prepare_threshold=0 disables prepared statements — required for
        # Supabase PgBouncer (transaction mode) which doesn't support them.
        return create_engine(
            sqlalchemy_url,
            pool_pre_ping=True,
            future=True,
            pool_size=int(os.getenv("ADMIN_DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("ADMIN_DB_MAX_OVERFLOW", "20")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
            connect_args={"prepare_threshold": 0},
        )

    fallback_url = os.getenv("ADMIN_FALLBACK_SQLITE", "sqlite:///./admin.db")
    logger.warning(
        "database_url_missing_using_fallback",
        fallback=fallback_url,
    )
    connect_args = {"check_same_thread": False} if fallback_url.startswith("sqlite") else {}
    return create_engine(fallback_url, connect_args=connect_args, future=True)



# Admin DB engine for core tables (users, tenants, memberships, roles)
_engine = _create_engine()
SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def _reset_tenant_guc_on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Clear ``app.tenant_id`` and related RLS GUCs when a pooled
    connection is handed out.

    Fixes #1381: pooled connections retain session-level GUCs across
    requests because ``set_tenant_context`` uses ``set_config(..., false)``
    (session-level). Without this listener the next unrelated request
    that picks up the connection inherits the previous tenant's
    ``app.tenant_id``.

    We run this on ``checkout`` (when the pool gives the connection to
    a session) rather than ``checkin`` (when the session returns it) so
    that even a connection that was orphaned mid-request -- e.g. by a
    crash or a ``KeyboardInterrupt`` -- is still clean on its next use.

    SQLite does not honor ``set_config`` and does not use RLS; skip
    silently.
    """
    if _engine.dialect.name == "sqlite":
        return
    try:
        cursor = dbapi_connection.cursor()
        try:
            # Clear tenant GUC. Third arg 'false' == session-level set,
            # which matches set_tenant_context's scope.
            cursor.execute("SELECT set_config('app.tenant_id', '', false)")
            # Defense-in-depth: also clear the sysadmin-context flag so
            # a stale sysadmin session does not linger in the pool.
            cursor.execute(
                "SELECT set_config('regengine.is_sysadmin', 'false', false)"
            )
        finally:
            cursor.close()
    except Exception as exc:  # noqa: BLE001 -- log and keep going
        # Do not fail the whole request if the RESET fails; log loudly
        # so the pool-bleed mitigation is visible if it ever regresses.
        logger.warning(
            "pool_checkout_tenant_reset_failed",
            error=str(exc),
        )


if _engine.dialect.name != "sqlite":
    event.listen(_engine, "checkout", _reset_tenant_guc_on_checkout)

def init_db() -> None:
    """Create RLS helper functions on startup. Schema is managed by Alembic.

    NOTE: Base.metadata.create_all() was removed intentionally for PostgreSQL
    — Alembic owns all DDL. For SQLite (local dev fallback), we create tables
    directly since Alembic migrations are PostgreSQL-specific.
    """
    dialect = _engine.dialect.name

    if dialect == "sqlite":
        # SQLite dev fallback: create only core auth tables (no Alembic, no RLS).
        # SQLite dev fallback doesn't support PostgreSQL ARRAY types.
        from .sqlalchemy_models import (
            Base, TenantModel, UserModel, RoleModel, MembershipModel,
            AuditLogModel, InviteModel, SessionModel, ReviewItemModel,
        )
        _core_tables = [
            Base.metadata.tables[m.__tablename__]
            for m in (TenantModel, UserModel, RoleModel, MembershipModel,
                      AuditLogModel, InviteModel, SessionModel, ReviewItemModel)
            if m.__tablename__ in Base.metadata.tables
        ]
        Base.metadata.create_all(bind=_engine, tables=_core_tables)
        logger.info("database_tables_initialized", dialect="sqlite", tables=len(_core_tables))
        return

    # Create RLS helper functions in Admin DB (use CREATE OR REPLACE to
    # avoid DROP errors when columns have DEFAULT dependencies on these fns)
    with _engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id text) RETURNS void AS $$
            BEGIN
              PERFORM set_config('app.tenant_id', tenant_id, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID AS $$
            DECLARE
              tid TEXT;
            BEGIN
              tid := NULLIF(current_setting('app.tenant_id', true), '');
              IF tid IS NULL THEN
                RAISE EXCEPTION 'app.tenant_id not set — tenant context required for RLS';
              END IF;
              RETURN tid::UUID;
            END;
            $$ LANGUAGE plpgsql;
        """))
        # SECURITY: set_admin_context sets the regengine.is_sysadmin session
        # variable. This alone is NOT sufficient for RLS bypass — the RLS
        # policies also require current_user = 'regengine_sysadmin'.
        # See: migrations/V048__rls_sysadmin_defense_in_depth.sql
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $$
            BEGIN
              IF p_is_sysadmin AND current_user != 'regengine_sysadmin' THEN
                RAISE WARNING 'set_admin_context(true) called by non-sysadmin role';
              END IF;
              PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
    logger.info("database_tables_initialized", dialect="postgresql")


def get_session() -> Iterator[Session]:
    """Provide a SQLAlchemy session for FastAPI dependencies.

    This returns a session connected to the Admin DB for core tables.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        # rollback() is a no-op if no transaction is active; when a prior
        # query aborted the transaction it clears the InFailedSqlTransaction
        # state so the next request checking out this pooled connection
        # does not inherit it.
        session.rollback()
        session.close()


def get_tenant_session(
    tenant_id: str,
) -> Iterator[Session]:
    """Provide a tenant-aware SQLAlchemy session (Admin DB).
    """
    session = SessionLocal()
    try:
        if tenant_id and _engine.dialect.name != "sqlite":
            from shared.tenant_context import set_tenant_guc  # noqa: PLC0415
            set_tenant_guc(session, tenant_id)
        yield session
    finally:
        session.rollback()
        session.close()


# Async session support (wraps sync session for FastAPI async routes)
async def get_async_session() -> AsyncIterator[Session]:
    """Provide an async-compatible SQLAlchemy session (Admin DB).

    Note: This wraps the synchronous session. For true async,
    use asyncpg with SQLAlchemy 2.0 async engine.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


