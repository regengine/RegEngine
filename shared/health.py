"""Deep health check utilities for production monitoring.

Provides dependency-aware health checks that verify database, cache, and
message queue connectivity. Addresses Gap Analysis finding on health checks.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger("health")


class HealthStatus(str, Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class DependencyCheck:
    """Result of a single dependency health check."""
    name: str
    status: HealthStatus
    latency_ms: float
    message: Optional[str] = None
    details: dict = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Aggregate health check result for a service."""
    status: HealthStatus
    service: str
    version: str
    uptime_seconds: float
    dependencies: list[DependencyCheck]
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "status": self.status.value,
            "service": self.service,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "dependencies": [
                {
                    "name": d.name,
                    "status": d.status.value,
                    "latency_ms": round(d.latency_ms, 2),
                    "message": d.message,
                    **d.details,
                }
                for d in self.dependencies
            ],
        }


class HealthChecker:
    """Deep health checker with dependency verification.
    
    Usage:
        checker = HealthChecker(service_name="admin-api", version="1.0.0")
        checker.add_check("postgresql", check_postgres)
        checker.add_check("redis", check_redis)
        result = await checker.check_all()
    """
    
    def __init__(self, service_name: str, version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        self.start_time = time.time()
        self.checks: dict[str, Callable] = {}
    
    def add_check(self, name: str, check_fn: Callable) -> None:
        """Register a dependency health check.
        
        Args:
            name: Dependency name (e.g., "postgresql", "redis", "kafka")
            check_fn: Async or sync function that raises on failure
        """
        self.checks[name] = check_fn
    
    async def check_all(self, timeout: float = 5.0) -> HealthCheckResult:
        """Run all registered health checks.
        
        Args:
            timeout: Maximum time to wait for each check in seconds
            
        Returns:
            Aggregate health check result
        """
        dependencies = []
        overall_status = HealthStatus.HEALTHY
        
        for name, check_fn in self.checks.items():
            start = time.perf_counter()
            try:
                # Handle both sync and async check functions
                if asyncio.iscoroutinefunction(check_fn):
                    await asyncio.wait_for(check_fn(), timeout=timeout)
                else:
                    await asyncio.wait_for(
                        asyncio.to_thread(check_fn), timeout=timeout
                    )
                latency = (time.perf_counter() - start) * 1000
                
                dependencies.append(DependencyCheck(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    message="OK",
                ))
                
            except asyncio.TimeoutError:
                latency = timeout * 1000
                dependencies.append(DependencyCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=f"Timeout after {timeout}s",
                ))
                overall_status = HealthStatus.UNHEALTHY
                logger.warning("health_check_timeout", dependency=name, timeout=timeout)
                
            except Exception as exc:
                latency = (time.perf_counter() - start) * 1000
                dependencies.append(DependencyCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=str(exc),
                ))
                overall_status = HealthStatus.UNHEALTHY
                logger.warning("health_check_failed", dependency=name, error=str(exc))
        
        uptime = time.time() - self.start_time
        
        return HealthCheckResult(
            status=overall_status,
            service=self.service_name,
            version=self.version,
            uptime_seconds=uptime,
            dependencies=dependencies,
        )


# Pre-built check functions for common dependencies

def create_postgres_check(database_url: str) -> Callable:
    """Create a PostgreSQL health check function.

    Args:
        database_url: PostgreSQL connection string

    Returns:
        Sync check function that supports psycopg with SSL
    """
    def check():
        import psycopg
        # Handle SQLAlchemy-style URLs like postgresql+psycopg://...
        # psycopg native driver expects postgresql://... format
        clean_url = database_url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
        
        # Determine sslmode based on the connection string
        sslmode = None
        if 'sslmode' not in clean_url and ('supabase' in clean_url or '@aws' in clean_url or '@db.' in clean_url):
            sslmode = 'require'
        
        # Build connection parameters
        conninfo_params = {"connect_timeout": 5}
        if sslmode:
            conninfo_params["sslmode"] = sslmode
        
        # Use conninfo parameter dictionary along with the base URL
        conn = psycopg.connect(clean_url, **conninfo_params)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
    return check


def create_redis_check(redis_url: str) -> Callable:
    """Create a Redis health check function.
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        Async check function
    """
    async def check():
        import redis.asyncio as redis
        client = redis.from_url(redis_url)
        try:
            await client.ping()
        finally:
            await client.close()
    return check


def create_neo4j_check(uri: str, user: str, password: str) -> Callable:
    """Create a Neo4j health check function.
    
    Args:
        uri: Neo4j bolt URI
        user: Neo4j username
        password: Neo4j password
        
    Returns:
        Sync check function (Neo4j driver is sync)
    """
    def check():
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session() as session:
                session.run("RETURN 1").consume()
        finally:
            driver.close()
    return check


def create_kafka_check(bootstrap_servers: str) -> Callable:
    """Create a Kafka health check function.
    
    Args:
        bootstrap_servers: Kafka bootstrap servers
        
    Returns:
        Sync check function
    """
    def check():
        from kafka.admin import KafkaAdminClient
        admin = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            request_timeout_ms=5000,
        )
        try:
            admin.list_topics(timeout_ms=5000)
        finally:
            admin.close()
    return check
