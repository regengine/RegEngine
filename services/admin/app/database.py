"""Database utilities for the admin service."""

from __future__ import annotations

import os
from typing import Iterator, AsyncIterator

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .sqlalchemy_models import Base
# Import PCOS models to register them with Base.metadata
from . import pcos_models  # noqa: F401

logger = structlog.get_logger("admin-db")


def _create_engine():
    """Create the Admin database engine for core tables (users, tenants, roles)."""
    database_url = os.getenv("ADMIN_DATABASE_URL")
    if database_url:
        logger.info("admin_database_configured", url=database_url.split("@")[-1])
        return create_engine(database_url, pool_pre_ping=True, future=True)

    fallback_url = os.getenv("ADMIN_FALLBACK_SQLITE", "sqlite:///./admin.db")
    logger.warning(
        "database_url_missing_using_fallback",
        fallback=fallback_url,
    )
    connect_args = {"check_same_thread": False} if fallback_url.startswith("sqlite") else {}
    return create_engine(fallback_url, connect_args=connect_args, future=True)


def _create_entertainment_engine():
    """Create the Entertainment database engine for PCOS tables.
    
    Following RegEngine's vertical isolation pattern, PCOS tables are now in
    the dedicated Entertainment database (as of V002 migration, Jan 31 2026).
    """
    database_url = os.getenv("ENTERTAINMENT_DATABASE_URL")
    if database_url:
        logger.info("entertainment_database_configured", url=database_url.split("@")[-1])
        return create_engine(database_url, pool_pre_ping=True, future=True)
    
    # Fallback: construct from ADMIN_DATABASE_URL by replacing database name
    admin_url = os.getenv("ADMIN_DATABASE_URL", "")
    if admin_url and "regengine_admin" in admin_url:
        entertainment_url = admin_url.replace("regengine_admin", "entertainment")
        logger.info("entertainment_database_derived_from_admin", url=entertainment_url.split("@")[-1])
        return create_engine(entertainment_url, pool_pre_ping=True, future=True)
    
    logger.warning("entertainment_database_url_missing_pcos_operations_may_fail")
    # Return same engine as fallback (won't work  but prevents crash)
    return _create_engine()


# Admin DB engine for core tables (users, tenants, memberships, roles)
_engine = _create_engine()
SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

# Entertainment DB engine for PCOS tables (all 38 pcos_* tables)
_entertainment_engine = _create_entertainment_engine()
EntertainmentSessionLocal = sessionmaker(
    bind=_entertainment_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """Create tables and functions if they do not exist. Call explicitly on startup."""
    Base.metadata.create_all(bind=_engine)
    
    # Create RLS helper functions in Admin DB
    with _engine.connect() as conn:
        conn.execute(text("DROP FUNCTION IF EXISTS set_tenant_context(text)"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id text) RETURNS void AS $$
            BEGIN
              PERFORM set_config('app.tenant_id', tenant_id, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP FUNCTION IF EXISTS get_tenant_context()"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID AS $$
            BEGIN
              RETURN COALESCE(
                NULLIF(current_setting('app.tenant_id', true), '')::UUID,
                '00000000-0000-0000-0000-000000000001'::UUID
              );
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP FUNCTION IF EXISTS set_admin_context(boolean)"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $$
            BEGIN
              PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
    
   # Create RLS helper functions in Entertainment DB  
    with _entertainment_engine.connect() as conn:
        conn.execute(text("DROP FUNCTION IF EXISTS set_tenant_context(text)"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id text) RETURNS void AS $$
            BEGIN
              PERFORM set_config('app.tenant_id', tenant_id, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP FUNCTION IF EXISTS get_tenant_context()"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID AS $$
            BEGIN
              RETURN COALESCE(
                NULLIF(current_setting('app.tenant_id', true), '')::UUID,
                '00000000-0000-0000-0000-000000000001'::UUID
              );
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP FUNCTION IF EXISTS set_admin_context(boolean)"))
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_admin_context(p_is_sysadmin boolean) RETURNS void AS $$
            BEGIN
              PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
    
    logger.info("database_tables_initialized")


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
        if tenant_id:
            session.execute(
                text("SET app.tenant_id = :tenant"),
                {"tenant": tenant_id}
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
        if tenant_id:
            session.execute(
                text("SET app.tenant_id = :tenant"),
                {"tenant": tenant_id}
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
