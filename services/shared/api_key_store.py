"""
SEC-005: Database-backed API key store using PostgreSQL.

This module provides a persistent, secure API key storage solution with:
- PostgreSQL-backed storage with SQLAlchemy ORM
- SHA-256 key hashing (raw keys never stored)
- Thread-safe operations with connection pooling
- Tenant isolation via key association
- Automatic rate limit tracking in Redis (optional)
- Key rotation support

Usage:
    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore(database_url="postgresql://...")
    raw_key, metadata = await store.create_key(name="Production Key", tenant_id="...")
    
    # Validate incoming requests
    api_key = await store.validate_key(raw_key_from_header)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, ClassVar, Optional, Sequence

# Imported only for annotations — breaks the runtime circular dep with
# ``shared.auth`` which itself imports from this module.
if TYPE_CHECKING:
    from shared.auth import APIKeyStore

import structlog
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = structlog.get_logger("api_key_store")

Base = declarative_base()


class APIKeyModel(Base):
    """SQLAlchemy model for API keys stored in PostgreSQL."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_id = Column(String(64), unique=True, nullable=False, index=True)
    key_hash = Column(String(64), nullable=False)  # SHA-256 hash
    key_prefix = Column(String(12), nullable=False)  # First 8 chars for identification
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Tenant association
    tenant_id = Column(String(36), nullable=True, index=True)  # UUID
    
    # Access control
    billing_tier = Column(String(50), nullable=True)  # DEVELOPER, PROFESSIONAL, ENTERPRISE
    allowed_jurisdictions = Column(ARRAY(String), default=list)
    scopes = Column(ARRAY(String), default=list)
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=60)
    rate_limit_per_hour = Column(Integer, default=1000)
    rate_limit_per_day = Column(Integer, default=10000)
    
    # Status
    enabled = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit
    created_by = Column(String(36), nullable=True)  # User ID who created the key
    revoked_by = Column(String(36), nullable=True)  # User ID who revoked the key
    revoke_reason = Column(Text, nullable=True)
    
    # Metadata (renamed to avoid conflict with SQLAlchemy's metadata)
    extra_data = Column(JSONB, default=dict)
    
    # Usage stats
    total_requests = Column(Integer, default=0)
    
    __table_args__ = (
        Index("ix_api_keys_tenant_enabled", "tenant_id", "enabled"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )


class APIKeyResponse(BaseModel):
    """API key response model (for API responses - never includes raw key or hash)."""

    key_id: str
    key_prefix: str
    name: str
    description: Optional[str] = None
    tenant_id: Optional[str] = None
    billing_tier: Optional[str] = None
    allowed_jurisdictions: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    rate_limit_per_day: int = 10000
    enabled: bool = True
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    total_requests: int = 0

    # The underlying SQLAlchemy columns are nullable (no DB-side NOT NULL),
    # so historical rows inserted before the Python defaults existed — or rows
    # inserted by tools that bypass the ORM — can legitimately have NULL in
    # these columns. Pydantic v2 rejects None against non-Optional typed fields
    # even when a default is set, which was 500'ing POST /v1/admin/keys and
    # 400'ing GET /v1/admin/keys. Coerce None → field default instead.
    @field_validator("allowed_jurisdictions", "scopes", mode="before")
    @classmethod
    def _coerce_none_list(cls, v: object) -> object:
        return [] if v is None else v

    _INT_DEFAULTS: ClassVar[dict[str, int]] = {
        "rate_limit_per_minute": 60,
        "rate_limit_per_hour": 1000,
        "rate_limit_per_day": 10000,
        "total_requests": 0,
    }

    @field_validator(
        "rate_limit_per_minute",
        "rate_limit_per_hour",
        "rate_limit_per_day",
        "total_requests",
        mode="before",
    )
    @classmethod
    def _coerce_none_int(cls, v: object, info) -> object:
        return cls._INT_DEFAULTS[info.field_name] if v is None else v

    class Config:
        from_attributes = True


class APIKeyCreateResponse(APIKeyResponse):
    """Response when creating a new API key - includes raw key (only time it's shown)."""

    raw_key: str  # Only included once, at creation time


class RateLimitInfo(BaseModel):
    """Rate limit information for a request."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None


class DatabaseAPIKeyStore:
    """PostgreSQL-backed API key store with async support.
    
    This implementation provides:
    - Persistent storage in PostgreSQL
    - Async/await support for non-blocking operations
    - SHA-256 hashing of keys (raw keys never stored)
    - Constant-time hash comparison for security
    - Connection pooling for performance
    - Optional Redis integration for rate limiting
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        pool_size: int = 5,
        max_overflow: int = 10,
    ):
        """Initialize the database-backed API key store.
        
        Args:
            database_url: PostgreSQL connection URL (async driver)
                         e.g., "postgresql+asyncpg://user:pass@host/db"
            redis_url: Optional Redis URL for rate limiting
            pool_size: SQLAlchemy connection pool size
            max_overflow: Max additional connections beyond pool_size
        """
        self._database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self._database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to your PostgreSQL connection string."
            )
        
        # Build engine kwargs (pool settings only for PostgreSQL, not SQLite)
        engine_kwargs: dict[str, Any] = {
            "echo": os.environ.get("SQL_ECHO", "false").lower() == "true",
        }
        
        # Force async driver for PostgreSQL
        if self._database_url.startswith("postgresql://"):
            # Default to asyncpg as it's the primary async driver used in this project
            self._database_url = self._database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif "postgresql" in self._database_url and "+" not in self._database_url:
            # Handle cases like "postgres://..."
            self._database_url = self._database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self._database_url.startswith("postgresql+psycopg2://"):
            # psycopg2 removed — migrate any leftover URLs to asyncpg
            self._database_url = self._database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        elif self._database_url.startswith("postgresql+psycopg://"):
             # psycopg (v3) is already async-capable, so this is usually fine,
             # but SQLAlchemy create_async_engine might still prefer explicit dialect.
             pass

        # Fix for asyncpg not supporting 'sslmode' query param (but psycopg2/psycopg needing it)
        if "asyncpg" in self._database_url and "sslmode=" in self._database_url:
            self._database_url = self._database_url.replace("?sslmode=require", "").replace("&sslmode=require", "")
            # Inject SSL for Supabase if not present
            if "ssl" not in engine_kwargs.get("connect_args", {}):
                engine_kwargs.setdefault("connect_args", {})["ssl"] = "require"

        # Supabase/pgbouncer transaction-pool compatibility (#1874): asyncpg
        # caches prepared statements per-connection by default, but pgbouncer
        # with pool_mode=transaction rotates the backend on every transaction,
        # so cached statement handles from one transaction are invalid in the
        # next — queries fail with "prepared statement … does not exist" and
        # the server returns 500. Disabling the cache makes asyncpg send plain
        # text protocol messages, which pgbouncer can route safely. Matches
        # asyncpg docs and Supabase's own pgbouncer guidance.
        if "asyncpg" in self._database_url:
            connect_args: dict[str, Any] = engine_kwargs.setdefault("connect_args", {})
            connect_args.setdefault("statement_cache_size", 0)
            connect_args.setdefault("prepared_statement_cache_size", 0)

        self._redis_url = redis_url or os.environ.get("REDIS_URL")
        
        # Only add pool settings for databases that support them (not SQLite)
        if "sqlite" not in self._database_url:
            engine_kwargs["pool_size"] = pool_size
            engine_kwargs["max_overflow"] = max_overflow
            engine_kwargs["pool_pre_ping"] = True
        
        # Create async engine
        self._engine = create_async_engine(self._database_url, **engine_kwargs)
        
        # Create async session factory
        self._session_factory = sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Optional Redis client for rate limiting
        self._redis = None
        if self._redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url)
            except ImportError:
                logger.warning("redis_not_available", message="Install redis for distributed rate limiting")

    async def init_db(self) -> None:
        """Create database tables if they don't exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_initialized", tables=["api_keys"])

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session with automatic cleanup."""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise
        finally:
            await session.close()

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Hash an API key using SHA-256.
        
        The raw key is never stored - only this hash.
        """
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @staticmethod
    def _generate_key_id() -> str:
        """Generate a unique key identifier."""
        return f"rge_{secrets.token_urlsafe(16)}"

    @staticmethod
    def _generate_secret() -> str:
        """Generate a cryptographically secure secret."""
        return secrets.token_urlsafe(32)

    def _validate_uuid(self, uuid_str: str) -> None:
        """Validate UUID format to prevent SQL injection in SET LOCAL."""
        if not uuid_str:
            return
        import uuid
        try:
            uuid.UUID(uuid_str)
        except ValueError:
            raise ValueError(f"Invalid UUID: {uuid_str}")

    async def _set_context(self, session: AsyncSession, tenant_id: Optional[str]) -> None:
        """Set tenant context for RLS if provided.

        Delegates to ``services.shared.tenant_context.set_tenant_guc`` —
        the canonical Phase B primitive, now async-compatible. Both
        forms (``SET LOCAL`` vs. ``SELECT set_config('app.tenant_id',
        :tid, true)``) are transaction-scoped per Postgres docs; the
        helper emits the latter so the same primitive works under
        psycopg (sync) and asyncpg (async). See #1879 for the
        original async-incompat issue.

        ``set_tenant_guc`` is a sync function but its body issues
        ``session.execute(...)``. Under an ``AsyncSession`` that
        execute returns an awaitable that must be awaited before the
        GUC write actually lands. We do that here.

        UUID validation happens inside ``set_tenant_guc``; the local
        ``_validate_uuid`` call below is now redundant but kept as a
        belt-and-suspenders guard.
        """
        if tenant_id:
            self._validate_uuid(tenant_id)
            from shared.tenant_context import set_tenant_guc  # noqa: PLC0415
            result = set_tenant_guc(session, tenant_id)
            # Async session: ``execute()`` returns a coroutine; await it
            # so the GUC write actually lands before subsequent queries.
            # Sync session: ``execute()`` returns a Result object directly,
            # nothing to await.
            if result is not None and hasattr(result, "__await__"):
                await result

    async def create_key(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        tenant_id: Optional[str] = None,
        billing_tier: Optional[str] = None,
        allowed_jurisdictions: Optional[list[str]] = None,
        scopes: Optional[list[str]] = None,
        rate_limit_per_minute: int = 60,
        rate_limit_per_hour: int = 1000,
        rate_limit_per_day: int = 10000,
        expires_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> APIKeyCreateResponse:
        """Create a new API key.
        
        IMPORTANT: The raw key is returned ONLY at creation time.
        It is not stored and cannot be retrieved later.
        
        Args:
            name: Human-readable name for the key
            description: Optional description
            tenant_id: UUID of the tenant this key belongs to
            billing_tier: DEVELOPER, PROFESSIONAL, or ENTERPRISE
            allowed_jurisdictions: List of jurisdiction codes (e.g., ["US", "EU"])
            scopes: Permission scopes (e.g., ["read:regulations", "write:analysis"])
            rate_limit_per_minute: Requests per minute limit
            rate_limit_per_hour: Requests per hour limit
            rate_limit_per_day: Requests per day limit
            expires_at: Optional expiration datetime
            created_by: User ID of creator (for audit)
            metadata: Additional metadata dict
            
        Returns:
            APIKeyCreateResponse with the raw key (show only once!)
        """
        key_id = self._generate_key_id()
        raw_secret = self._generate_secret()
        raw_key = f"{key_id}.{raw_secret}"
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:12]  # For user identification
        now = datetime.now(timezone.utc)

        api_key = APIKeyModel(
            key_id=key_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            description=description,
            tenant_id=tenant_id,
            billing_tier=billing_tier,
            allowed_jurisdictions=allowed_jurisdictions or ["US"],
            scopes=scopes or [],
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_hour=rate_limit_per_hour,
            rate_limit_per_day=rate_limit_per_day,
            expires_at=expires_at,
            created_by=created_by,
            created_at=now,  # Explicitly set
            extra_data=metadata or {},
        )

        async with self._session() as session:
            if tenant_id:
                await self._set_context(session, tenant_id)
            
            session.add(api_key)
            await session.flush()

        logger.info(
            "api_key_created",
            key_id=key_id,
            name=name,
            tenant_id=tenant_id,
            created_by=created_by,
        )

        return APIKeyCreateResponse(
            key_id=key_id,
            key_prefix=key_prefix,
            name=name,
            description=description,
            tenant_id=tenant_id,
            billing_tier=billing_tier,
            allowed_jurisdictions=allowed_jurisdictions or ["US"],
            scopes=scopes or [],
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_hour=rate_limit_per_hour,
            rate_limit_per_day=rate_limit_per_day,
            enabled=True,
            created_at=now,
            expires_at=expires_at,
            last_used_at=None,
            total_requests=0,
            raw_key=raw_key,  # Only returned at creation!
        )

    async def validate_key(self, raw_key: str) -> Optional[APIKeyResponse]:
        """Validate an API key and return its metadata.
        
        Uses constant-time comparison to prevent timing attacks.
        Updates last_used_at and total_requests on successful validation.
        
        Args:
            raw_key: The raw API key from the request header
            
        Returns:
            APIKeyResponse if valid, None otherwise
        """
        if not raw_key or not raw_key.startswith("rge_"):
            return None

        # Extract key_id
        try:
            key_id, _ = raw_key.split(".", 1)
        except ValueError:
            return None

        key_hash = self._hash_key(raw_key)

        async with self._session() as session:
            result = await session.execute(
                select(APIKeyModel).where(APIKeyModel.key_id == key_id)
            )
            api_key = result.scalar_one_or_none()

            if not api_key:
                logger.warning("api_key_not_found", key_id=key_id)
                return None

            # Constant-time hash comparison
            if not hmac.compare_digest(key_hash, api_key.key_hash):
                logger.warning("api_key_hash_mismatch", key_id=key_id)
                return None

            # Check if enabled
            if not api_key.enabled:
                logger.warning("api_key_disabled", key_id=key_id)
                return None

            # Check if expired
            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                logger.warning("api_key_expired", key_id=key_id)
                return None

            # Check if revoked
            if api_key.revoked_at:
                logger.warning("api_key_revoked", key_id=key_id)
                return None

            # Update usage stats
            api_key.last_used_at = datetime.now(timezone.utc)
            api_key.total_requests = (api_key.total_requests or 0) + 1
            await session.flush()

            return APIKeyResponse.model_validate(api_key)

    async def check_rate_limit(
        self,
        key_id: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitInfo:
        """Check if a key has exceeded its rate limit.
        
        Uses Redis if available for distributed rate limiting,
        otherwise falls back to a simple in-memory counter.
        
        Args:
            key_id: The API key identifier
            limit: Maximum requests allowed in the window
            window_seconds: Time window in seconds (default: 60)
            
        Returns:
            RateLimitInfo with allowed status and remaining quota
        """
        now = datetime.now(timezone.utc)
        window_key = f"ratelimit:{key_id}:{window_seconds}"
        
        if self._redis:
            # Use Redis for distributed rate limiting
            pipe = self._redis.pipeline()
            # AIORedis pipeline methods are sync, they just buffer commands
            pipe.incr(window_key)
            pipe.expire(window_key, window_seconds)
            results = await pipe.execute()
            current_count = results[0]
        else:
            # Fail closed: no Redis means no distributed rate limiting.
            # Deny requests to prevent unbounded access when Redis is down.
            logger.error(
                "rate_limit_fail_closed",
                message="Redis unavailable — denying request to enforce rate limits",
                key_id=key_id,
            )
            return RateLimitInfo(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=now,
                retry_after=window_seconds,
            )

        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        # Start of next minute (next rate-limit bucket boundary).
        # Use ``timedelta`` arithmetic rather than ``.replace(minute=minute+1)``
        # because Python rejects ``minute=60`` with ``ValueError: minute must
        # be in 0..59`` — so at XX:59 the old code raised and the global
        # value_error handler returned HTTP 400 for every authenticated
        # ingest request during that minute (#1887). ``timedelta`` correctly
        # rolls minute/hour/day boundaries.
        reset_at = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        retry_after = None if allowed else window_seconds

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                key_id=key_id,
                current=current_count,
                limit=limit,
            )

        return RateLimitInfo(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    async def revoke_key(
        self,
        key_id: str,
        revoked_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Revoke an API key.
        
        Args:
            key_id: The key identifier to revoke
            revoked_by: User ID who initiated the revocation
            reason: Reason for revocation (for audit)
            
        Returns:
            True if key was found and revoked, False otherwise
        """
        async with self._session() as session:
            result = await session.execute(
                update(APIKeyModel)
                .where(APIKeyModel.key_id == key_id)
                .values(
                    enabled=False,
                    revoked_at=datetime.now(timezone.utc),
                    revoked_by=revoked_by,
                    revoke_reason=reason,
                )
            )

            if result.rowcount > 0:
                logger.info(
                    "api_key_revoked",
                    key_id=key_id,
                    revoked_by=revoked_by,
                    reason=reason,
                )
                return True

            return False

    async def rotate_key(
        self,
        key_id: str,
        created_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[APIKeyCreateResponse]:
        """Rotate an API key by creating a new one and revoking the old.
        
        The new key inherits all settings from the old key.
        
        Args:
            key_id: The key identifier to rotate
            created_by: User ID performing the rotation
            reason: Reason for rotation (for audit)
            
        Returns:
            APIKeyCreateResponse with new key, or None if old key not found
        """
        async with self._session() as session:
            # Get the old key
            result = await session.execute(
                select(APIKeyModel).where(APIKeyModel.key_id == key_id)
            )
            old_key = result.scalar_one_or_none()

            if not old_key:
                return None

        # Create new key with same settings
        new_key = await self.create_key(
            name=f"{old_key.name} (rotated)",
            description=old_key.description,
            tenant_id=old_key.tenant_id,
            billing_tier=old_key.billing_tier,
            allowed_jurisdictions=list(old_key.allowed_jurisdictions or []),
            scopes=list(old_key.scopes or []),
            rate_limit_per_minute=old_key.rate_limit_per_minute,
            rate_limit_per_hour=old_key.rate_limit_per_hour,
            rate_limit_per_day=old_key.rate_limit_per_day,
            expires_at=old_key.expires_at,
            created_by=created_by,
            metadata={
                **(old_key.extra_data or {}),
                "rotated_from": key_id,
                "rotation_reason": reason,
            },
        )

        # Revoke old key
        await self.revoke_key(key_id, revoked_by=created_by, reason=f"Rotated: {reason}")

        logger.info(
            "api_key_rotated",
            old_key_id=key_id,
            new_key_id=new_key.key_id,
            rotated_by=created_by,
        )

        return new_key

    async def list_keys(
        self,
        tenant_id: Optional[str] = None,
        include_disabled: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> Sequence[APIKeyResponse]:
        """List API keys, optionally filtered by tenant.

        Args:
            tenant_id: Filter by tenant ID (None = all tenants)
            include_disabled: Include revoked/disabled keys
            limit: Maximum number of keys to return (default 500)
            offset: Number of keys to skip (default 0)

        Returns:
            List of APIKeyResponse objects
        """
        async with self._session() as session:
            query = select(APIKeyModel)

            if tenant_id:
                await self._set_context(session, tenant_id)
                query = query.where(APIKeyModel.tenant_id == tenant_id)

            if not include_disabled:
                query = query.where(APIKeyModel.enabled == True)

            query = query.order_by(APIKeyModel.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            keys = result.scalars().all()

            return [APIKeyResponse.model_validate(k) for k in keys]

    async def get_key(self, key_id: str) -> Optional[APIKeyResponse]:
        """Get API key metadata by key_id.
        
        Args:
            key_id: The key identifier
            
        Returns:
            APIKeyResponse or None if not found
        """
        async with self._session() as session:
            result = await session.execute(
                select(APIKeyModel).where(APIKeyModel.key_id == key_id)
            )
            api_key = result.scalar_one_or_none()

            if not api_key:
                return None

            return APIKeyResponse.model_validate(api_key)

    async def update_key(
        self,
        key_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        rate_limit_per_minute: Optional[int] = None,
        rate_limit_per_hour: Optional[int] = None,
        rate_limit_per_day: Optional[int] = None,
        scopes: Optional[list[str]] = None,
        enabled: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[APIKeyResponse]:
        """Update API key settings.
        
        Note: Cannot update key_hash, tenant_id, or billing_tier.
        Use rotate_key() to change security-sensitive fields.
        
        Args:
            key_id: The key identifier
            **kwargs: Fields to update
            
        Returns:
            Updated APIKeyResponse or None if not found
        """
        updates = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if rate_limit_per_minute is not None:
            updates["rate_limit_per_minute"] = rate_limit_per_minute
        if rate_limit_per_hour is not None:
            updates["rate_limit_per_hour"] = rate_limit_per_hour
        if rate_limit_per_day is not None:
            updates["rate_limit_per_day"] = rate_limit_per_day
        if scopes is not None:
            updates["scopes"] = scopes
        if enabled is not None:
            updates["enabled"] = enabled
        if metadata is not None:
            updates["extra_data"] = metadata

        if not updates:
            return await self.get_key(key_id)

        async with self._session() as session:
            result = await session.execute(
                update(APIKeyModel)
                .where(APIKeyModel.key_id == key_id)
                .values(**updates)
                .returning(APIKeyModel)
            )
            api_key = result.scalar_one_or_none()

            if not api_key:
                return None

            return APIKeyResponse.model_validate(api_key)

    async def close(self) -> None:
        """Close database connections."""
        await self._engine.dispose()
        if self._redis:
            await self._redis.close()


# Global instance (lazy initialization)
_db_key_store: Optional[DatabaseAPIKeyStore] = None


async def get_db_key_store() -> DatabaseAPIKeyStore:
    """Get the global database-backed API key store instance.
    
    Initializes on first call.
    """
    global _db_key_store
    if _db_key_store is None:
        _db_key_store = DatabaseAPIKeyStore()
        await _db_key_store.init_db()
    return _db_key_store

async def get_api_key_store() -> DatabaseAPIKeyStore:
    """Compatibility alias for get_db_key_store()"""
    return await get_db_key_store()


# Migration helper
async def migrate_from_memory_store(
    memory_store: "APIKeyStore",  # From shared.auth
    db_store: DatabaseAPIKeyStore,
    created_by: Optional[str] = None,
) -> dict[str, str]:
    """Migrate API keys from in-memory store to database.
    
    IMPORTANT: This cannot recover the raw keys - new keys will be generated.
    
    Args:
        memory_store: The in-memory APIKeyStore instance
        db_store: The database APIKeyStore to migrate to
        created_by: User ID for audit trail
        
    Returns:
        Mapping of old key_id -> new raw_key
    """
    migrated = {}

    for old_key in memory_store.list_keys():
        new_response = await db_store.create_key(
            name=f"{old_key.name} (migrated)",
            tenant_id=old_key.tenant_id,
            billing_tier=old_key.billing_tier,
            allowed_jurisdictions=list(old_key.allowed_jurisdictions),
            scopes=list(old_key.scopes),
            rate_limit_per_minute=old_key.rate_limit_per_minute,
            expires_at=old_key.expires_at,
            created_by=created_by,
            metadata={
                "migrated_from": old_key.key_id,
                "original_created_at": old_key.created_at.isoformat(),
            },
        )
        migrated[old_key.key_id] = new_response.raw_key
        logger.info(
            "api_key_migrated",
            old_key_id=old_key.key_id,
            new_key_id=new_response.key_id,
        )

    return migrated
