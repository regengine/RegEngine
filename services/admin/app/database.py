"""Database utilities for the admin service."""

from __future__ import annotations

import os
from typing import Iterator, AsyncIterator

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# PCOS models are registered with Base.metadata at import time.
# Keep this import so Alembic --autogenerate can see them.
from . import pcos_models  # noqa: F401

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
        return create_engine(
            sqlalchemy_url,
            pool_pre_ping=True,
            future=True,
            pool_size=int(os.getenv("ADMIN_DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("ADMIN_DB_MAX_OVERFLOW", "20")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
        )

    default_sqlite = f"sqlite:///{os.path.join(os.path.dirname(__file__), '..', 'admin.db')}"
    fallback_url = os.getenv("ADMIN_FALLBACK_SQLITE", default_sqlite)
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

# PCOS tables: Entertainment DB was planned but not yet provisioned.
# Fall back to admin DB engine until ENTERTAINMENT_DATABASE_URL is configured.
_entertainment_url = os.getenv("ENTERTAINMENT_DATABASE_URL")
if _entertainment_url:
    _entertainment_engine = create_engine(
        _sqlalchemy_url(_entertainment_url),
        pool_pre_ping=True,
        future=True,
        pool_size=int(os.getenv("ENTERTAINMENT_DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("ENTERTAINMENT_DB_MAX_OVERFLOW", "20")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
    )
    logger.info("entertainment_database_configured", url=_entertainment_url.split("@")[-1])
else:
    _entertainment_engine = _engine
    logger.warning("entertainment_database_not_configured_using_admin_db")

EntertainmentSessionLocal = sessionmaker(
    bind=_entertainment_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """Create RLS helper functions on startup. Schema is managed by Alembic.

    NOTE: Base.metadata.create_all() was removed intentionally for PostgreSQL
    — Alembic owns all DDL. For SQLite (local dev fallback), we create tables
    directly since Alembic migrations are PostgreSQL-specific.
    """
    dialect = _engine.dialect.name

    if dialect == "sqlite":
        # SQLite dev fallback: create only core auth tables (no Alembic, no RLS).
        # PCOS models use PostgreSQL ARRAY types incompatible with SQLite.
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
    For PCOS operations, use get_pcos_session() instead.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_pcos_session() -> Iterator[Session]:
    """Provide a SQLAlchemy session for PCOS operations (Entertainment DB).
    
    All PCOS models (38 tables prefixed with pcos_*) are in the Entertainment database
    as of the V002 migration on Jan 31, 2026. Use this session for all PCOS routes.
    """
    session = EntertainmentSessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_tenant_session(
    tenant_id: str,
) -> Iterator[Session]:
    """Provide a tenant-aware SQLAlchemy session (Admin DB).

    For PCOS operations with tenant isolation, use get_pcos_tenant_session() instead.
    """
    session = SessionLocal()
    try:
        if tenant_id and _engine.dialect.name != "sqlite":
            session.execute(
                text("SET LOCAL app.tenant_id = :tenant"),
                {"tenant": tenant_id},
            )
        yield session
    finally:
        session.close()


def get_pcos_tenant_session(
    tenant_id: str,
) -> Iterator[Session]:
    """Provide a tenant-aware SQLAlchemy session for PCOS operations (Entertainment DB).

    Use this for PCOS routes that need tenant isolation (most PCOS operations).
    """
    session = EntertainmentSessionLocal()
    try:
        if tenant_id and _entertainment_engine.dialect.name != "sqlite":
            session.execute(
                text("SET LOCAL app.tenant_id = :tenant"),
                {"tenant": tenant_id},
            )
        yield session
    finally:
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
        session.close()


async def get_async_pcos_session() -> AsyncIterator[Session]:
    """Provide an async-compatible SQLAlchemy session for PCOS operations (Entertainment DB).
    
    Note: This wraps the synchronous session. For true async,
    use asyncpg with SQLAlchemy 2.0 async engine.
    """
    session = EntertainmentSessionLocal()
    try:
        yield session
    finally:
        session.close()
