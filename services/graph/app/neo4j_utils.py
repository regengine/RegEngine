from __future__ import annotations

import threading
from typing import Any, Optional
from uuid import UUID

from neo4j import AsyncGraphDatabase, GraphDatabase

from .config import settings

_driver = None
_driver_lock = threading.Lock()


def driver():
    """Legacy driver function for backward compatibility."""
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    max_connection_lifetime=settings.neo4j_max_lifetime,
                    max_connection_pool_size=settings.neo4j_pool_size,
                    connection_acquisition_timeout=settings.neo4j_pool_timeout,
                    encrypted=settings.neo4j_encrypted,
                )
    return _driver


def close_driver() -> None:
    """Close the legacy global driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


class Neo4jClient:
    """Neo4j client with multi-database support for tenant isolation."""

    # Database naming convention
    DB_GLOBAL = "neo4j"  # Default global database for regulatory data
    DB_TENANT_PREFIX = "reg_tenant_"

    def __init__(self, database: Optional[str] = None):
        """Initialize Neo4j client.

        Args:
            database: Database name. When ``settings.neo4j_enterprise`` is
                True, this value selects the per-tenant database (so passing
                ``database=Neo4jClient.get_tenant_database_name(tenant_id)``
                yields real DB-level isolation). When False (Community
                Edition, the default), the client is pinned to the global
                ``neo4j`` database — isolation is property-based only.

        Previously this argument was silently overridden to DB_GLOBAL on
        every construction, which defeated the per-tenant isolation the
        caller believed it was getting. The current behavior makes the
        isolation contract explicit and opt-in via ``NEO4J_ENTERPRISE``.
        See issue #1229.
        """
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=settings.neo4j_max_lifetime,
            max_connection_pool_size=settings.neo4j_pool_size,
            connection_acquisition_timeout=settings.neo4j_pool_timeout,
            encrypted=settings.neo4j_encrypted,
        )
        # Honor the caller's database= argument when Enterprise is enabled so
        # per-tenant DBs are actually used. On Community, pin to the global
        # database — callers MUST NOT rely on DB-level isolation in that case;
        # all queries must enforce tenant_id property predicates.
        if getattr(settings, "neo4j_enterprise", False):
            self.database = database or self.DB_GLOBAL
        else:
            self.database = self.DB_GLOBAL

    @staticmethod
    def get_tenant_database_name(tenant_id: UUID) -> str:
        """Generate tenant-specific database name.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Database name in format: reg_tenant_<uuid>
        """
        return f"{Neo4jClient.DB_TENANT_PREFIX}{tenant_id}"

    @staticmethod
    def get_global_database_name() -> str:
        """Get global regulatory database name."""
        return Neo4jClient.DB_GLOBAL

    def session(self, **kwargs) -> Any:
        """Create a new async session for this database.

        Returns:
            Neo4j async session configured for this client's database
        """
        return self._driver.session(database=self.database, **kwargs)

    async def close(self) -> None:
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()

    async def create_tenant_database(self, tenant_id: UUID) -> None:
        """Create a new tenant database (requires admin privileges).

        Args:
            tenant_id: Tenant UUID

        Note:
            This requires the user to have CREATE DATABASE privileges in Neo4j.
            In Neo4j Community Edition, this may not be supported.
        """
        db_name = self.get_tenant_database_name(tenant_id)
        # Sanitize database name — strict allowlist only.
        # Neo4j DDL does not support parameterized database names, so
        # regex validation is the primary defense against injection.
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{0,62}$', db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        # Connect to system database to create new database
        async with self._driver.session(database="system") as session:
            # Check if database already exists (parameterized — safe)
            result = await session.run("SHOW DATABASES WHERE name = $name", name=db_name)
            if not await result.single():
                # DDL does not support parameters; name is validated above
                await session.run(f"CREATE DATABASE {db_name} IF NOT EXISTS")

    async def __aenter__(self):
        """Async context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager cleanup."""
        await self.close()
