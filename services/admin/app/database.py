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
``SELECT set_config('app.tenant_id', '', false)`` and resets
``regengine.is_sysadmin`` to the fail-closed ``false`` baseline
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
from typing import AsyncIterator, Iterator

# #2461: installs the class-level RLS GUC "begin" hook before the
# module-level _create_engine() below (see shared/tenant_context.py).
# ``shared.`` alias on purpose — one module instance, one ContextVar pair.
import shared.tenant_context  # noqa: F401,E402  (side effect: install_rls_guc_hook)
import structlog
from shared.db_liveness import postgres_liveness_connect_args

# #2512: single shared cloud-marker tuple — keep this in lockstep with the
# central security gate in shared.env rather than maintaining a divergent copy.
from shared.env import CLOUD_ENV_VARS as _CLOUD_ENV_MARKERS
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger("admin-db")

_LOCAL_FALLBACK_ENVS = {"development", "dev", "test", "local"}


def _sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _admin_fallback_environment() -> str:
    """Return the explicitly configured environment for admin DB fallback checks."""
    return (
        os.getenv("REGENGINE_ENV", "").strip().lower()
        or os.getenv("ENVIRONMENT", "").strip().lower()
        or os.getenv("ENV", "").strip().lower()
    )


def _cloud_deployment_detected() -> bool:
    return any(os.getenv(marker) for marker in _CLOUD_ENV_MARKERS)


def _sqlite_fallback_allowed() -> bool:
    return _admin_fallback_environment() in _LOCAL_FALLBACK_ENVS and not _cloud_deployment_detected()


def _create_engine():
    """Create the Admin database engine for core tables (users, tenants, roles)."""
    database_url = os.getenv("ADMIN_DATABASE_URL")
    if database_url:
        sqlalchemy_url = _sqlalchemy_url(database_url)
        logger.info("admin_database_configured", url=database_url.split("@")[-1])
        if sqlalchemy_url.startswith("sqlite"):
            return create_engine(
                sqlalchemy_url,
                connect_args={"check_same_thread": False},
                future=True,
            )
        # prepare_threshold=None disables psycopg3 client-side prepared
        # statements. Required for Supabase's transaction-mode pooler
        # (PgBouncer-style) which hands out a different backend connection
        # per query, so prep statements like `_pg3_0` either don't exist
        # on the new backend or collide with another tenant's prep cache.
        # `0` (the previous value) means "prepare on first use" — the
        # opposite of the desired behavior.
        # The liveness args bound each connect and detect a dead peer, so a
        # Postgres restart cannot hang an auth/admin request (2026-09-28).
        return create_engine(
            sqlalchemy_url,
            pool_pre_ping=True,
            future=True,
            pool_size=int(os.getenv("ADMIN_DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("ADMIN_DB_MAX_OVERFLOW", "20")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
            connect_args={
                "prepare_threshold": None,
                **postgres_liveness_connect_args(sqlalchemy_url),
            },
        )

    fallback_url = os.getenv("ADMIN_FALLBACK_SQLITE")
    if not fallback_url or not _sqlite_fallback_allowed():
        environment = _admin_fallback_environment() or "unset"
        logger.critical(
            "admin_database_url_missing",
            environment=environment,
            cloud_deployment=_cloud_deployment_detected(),
            fallback_configured=bool(fallback_url),
        )
        raise RuntimeError(
            "ADMIN_DATABASE_URL is required. SQLite fallback is only allowed when "
            "ADMIN_FALLBACK_SQLITE is explicitly set with REGENGINE_ENV=development, "
            "test, or local outside cloud deployments."
        )

    if not fallback_url.startswith("sqlite"):
        raise RuntimeError("ADMIN_FALLBACK_SQLITE must be a sqlite URL")

    logger.warning(
        "admin_database_url_missing_using_explicit_sqlite_fallback",
        fallback=fallback_url,
    )
    return create_engine(
        fallback_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


# Admin DB engine for core tables (users, tenants, memberships, roles)
_engine = _create_engine()
SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_admin_engine():
    """Return the canonical audited control-plane engine.

    Cross-tenant queue coordination and global maintenance must use this
    engine rather than attempting to arm an unprivileged GUC on
    ``DATABASE_URL``.  Production startup independently verifies that it is
    connected as the exact ``regengine_sysadmin`` role.
    """

    return _engine


def arm_global_admin_context(db_session) -> None:
    """Explicitly arm one classified global control-plane transaction.

    Merely connecting with ``regengine_sysadmin`` never enables global RLS
    policies. Callers that intentionally coordinate across tenants must invoke
    this helper in the same transaction before their first protected query.
    Tenant-scoped request handlers must set ``app.tenant_id`` and leave this
    flag false.
    """

    bind = getattr(db_session, "bind", None) or getattr(db_session, "engine", None)
    if bind is not None and getattr(bind.dialect, "name", None) == "sqlite":
        db_session.info["is_admin"] = True
        return
    db_session.execute(
        text("SELECT set_config('regengine.is_sysadmin', 'true', true)")
    )


def disarm_global_admin_context(db_session) -> None:
    """Force the current transaction back to tenant-scoped admin posture."""

    bind = getattr(db_session, "bind", None) or getattr(db_session, "engine", None)
    if bind is not None and getattr(bind.dialect, "name", None) == "sqlite":
        db_session.info["is_admin"] = False
        return
    db_session.execute(
        text("SELECT set_config('regengine.is_sysadmin', 'false', true)")
    )


def bind_authenticated_user_context(db_session, user_id) -> None:
    """Bind self-service auth policies to one verified user for this transaction."""

    bind = getattr(db_session, "bind", None) or getattr(db_session, "engine", None)
    if bind is not None and getattr(bind.dialect, "name", None) == "sqlite":
        db_session.info["authenticated_user_id"] = str(user_id)
        return
    db_session.execute(
        text("SELECT set_config('regengine.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


def _dbapi_connection_is_idle(dbapi_connection) -> bool:
    """Return whether a psycopg connection has no open transaction.

    A checkout hook must never commit an inherited transaction merely to make
    its GUC reset durable.  Psycopg 2 exposes ``get_transaction_status``;
    psycopg 3 exposes ``info.transaction_status``.  Unknown drivers fail
    closed because this listener is installed only on PostgreSQL engines.
    """

    status = None
    status_getter = getattr(dbapi_connection, "get_transaction_status", None)
    if callable(status_getter):
        status = status_getter()
    else:
        info = getattr(dbapi_connection, "info", None)
        status = getattr(info, "transaction_status", None)

    if status is None:
        return False
    status_name = getattr(status, "name", None)
    if isinstance(status_name, str):
        return status_name.upper() == "IDLE"
    try:
        # psycopg2.extensions.TRANSACTION_STATUS_IDLE and psycopg3's enum
        # both have the integer value zero.
        return int(status) == 0
    except (TypeError, ValueError):
        return False


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
        # Pool reset-on-return should already have rolled back application
        # work.  Prove that invariant before issuing or committing anything;
        # an unknown/inherited transaction makes the connection disposable.
        if not _dbapi_connection_is_idle(dbapi_connection):
            raise RuntimeError(
                "PostgreSQL connection was not idle before checkout GUC reset"
            )

        cursor = dbapi_connection.cursor()
        try:
            # Clear tenant GUC. Third arg 'false' == session-level set,
            # which matches set_tenant_context's scope.
            cursor.execute("SELECT set_config('app.tenant_id', '', false)")
            cursor.execute("SELECT set_config('app.portal_link_token', '', false)")
            cursor.execute("SELECT set_config('app.remediation_token_hash', '', false)")
            cursor.execute("SELECT set_config('regengine.tenant_id', '', false)")
            cursor.execute("SELECT set_config('regengine.user_id', '', false)")
            # Database-role identity is necessary but not sufficient for a
            # global operation. Every checkout starts disarmed; classified
            # global auth/worker/control-plane callers explicitly arm their
            # own transaction with ``arm_global_admin_context``.
            cursor.execute(
                "SELECT set_config('regengine.is_sysadmin', 'false', false)"
            )
            cursor.execute(
                "SELECT set_config('regengine.system_context', 'false', false)"
            )
            cursor.execute(
                "SELECT set_config('regengine.api_key_lookup_id', '', false)"
            )
            cursor.execute(
                "SELECT set_config('regengine.api_key_lookup_hash_current', '', false)"
            )
            cursor.execute(
                "SELECT set_config('regengine.api_key_lookup_hash_legacy', '', false)"
            )
            cursor.execute(
                "SELECT set_config('audit.allow_break_glass', 'false', false)"
            )
            cursor.execute(
                "SELECT set_config('fsma.allow_mutation', 'false', false)"
            )
        finally:
            cursor.close()

        # SET/set_config is transactional in PostgreSQL.  The connection was
        # proven idle immediately above, so this commit contains only the
        # reset statements and makes them immune to a later request rollback.
        dbapi_connection.commit()
        if not _dbapi_connection_is_idle(dbapi_connection):
            raise RuntimeError(
                "PostgreSQL connection did not return to idle after GUC reset"
            )
    except Exception as exc:  # noqa: BLE001
        # Never hand out a connection after a partial reset.  Rollback is safe
        # here because an inherited transaction was rejected before any reset
        # statement ran; otherwise it contains only our reset work.
        try:
            dbapi_connection.rollback()
        except Exception:  # noqa: BLE001 - connection is discarded below
            pass
        # Fail closed: a connection whose GUC reset failed may still carry
        # the previous tenant's session-scoped app.tenant_id — handing it
        # out would scope RLS reads to the WRONG tenant (#1381 re-opened on
        # the mitigation's own error path). DisconnectionError makes the
        # pool discard this connection and retry the checkout on a fresh
        # one instead of proceeding with a possibly-stale tenant scope.
        logger.error(
            "pool_checkout_tenant_reset_failed",
            error=str(exc),
        )
        raise DisconnectionError("tenant GUC reset failed on pool checkout; discarding connection") from exc


if _engine.dialect.name != "sqlite":
    event.listen(_engine, "checkout", _reset_tenant_guc_on_checkout)


def init_db() -> None:
    """Probe DB posture on startup. Schema and DDL are managed by Alembic.

    NOTE: Base.metadata.create_all() and the RLS helper-function DDL were
    removed intentionally for PostgreSQL — Alembic owns all DDL, including
    set_tenant_context (v099), get_tenant_context (v056, pinned by v097) and
    set_admin_context (v051/v056, public copy pinned by v099). For SQLite
    (local dev fallback), we create tables directly since Alembic migrations
    are PostgreSQL-specific.
    """
    # #2461: probe the ADMIN engine's role posture (it may point at a
    # different database than the shared engine in dual-DB deployments).
    # RuntimeError (REGENGINE_REQUIRE_RLS_ENFORCEMENT=1 + inert role) must
    # propagate; anything else is a best-effort probe.
    try:
        from shared.database import check_rls_posture  # noqa: PLC0415

        check_rls_posture(_engine, label="admin", expected_role="regengine_sysadmin")
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover — probe must not block init
        logger.warning("rls_posture_check_skipped", engine="admin", error=str(exc))

    dialect = _engine.dialect.name

    if dialect == "sqlite":
        # SQLite dev fallback: create only core auth tables (no Alembic, no RLS).
        # SQLite dev fallback doesn't support PostgreSQL ARRAY types.
        from .sqlalchemy_models import (
            AuditLogModel,
            AuthChallengeModel,
            Base,
            InviteModel,
            MembershipModel,
            OrganizationMembershipModel,
            OrganizationModel,
            ReviewItemModel,
            RoleModel,
            SessionModel,
            TenantModel,
            UserEmailModel,
            UserModel,
            WebAuthnChallengeModel,
            WebAuthnCredentialModel,
        )

        _core_tables = [
            Base.metadata.tables[m.__tablename__]
            for m in (
                TenantModel,
                UserModel,
                UserEmailModel,
                OrganizationModel,
                OrganizationMembershipModel,
                AuthChallengeModel,
                WebAuthnCredentialModel,
                WebAuthnChallengeModel,
                RoleModel,
                MembershipModel,
                AuditLogModel,
                InviteModel,
                SessionModel,
                ReviewItemModel,
            )
            if m.__tablename__ in Base.metadata.tables
        ]
        Base.metadata.create_all(bind=_engine, tables=_core_tables)
        logger.info("database_tables_initialized", dialect="sqlite", tables=len(_core_tables))
        return

    # No runtime DDL for PostgreSQL (#2461 follow-up to v098/#2645): the RLS
    # helper functions this block used to CREATE OR REPLACE are migration-owned
    # — set_admin_context (v051/v056, public copy pinned by v099),
    # get_tenant_context (v056, pinned by v097), set_tenant_context (v099).
    # Under the least-privilege cutover the app role is denied that DDL anyway;
    # attempting it here only produced the boot-time
    # admin_database_init_skipped warning.
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

    Raises ValueError on a falsy ``tenant_id`` (#2696): silently yielding a
    session with no ``app.tenant_id`` GUC would rely solely on the RLS
    fail-closed predicate and hide the caller's bug.
    """
    if not tenant_id:
        raise ValueError("get_tenant_session requires a non-empty tenant_id")
    session = SessionLocal()
    try:
        if _engine.dialect.name != "sqlite":
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
