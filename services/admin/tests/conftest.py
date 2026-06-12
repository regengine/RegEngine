"""
Admin Service Test Configuration and Fixtures
"""

import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture(scope="session")
def tables(engine):
    """Create all tables for testing."""
    from services.admin.app.sqlalchemy_models import Base

    # Create tenant and user tables first (mock)
    with engine.connect() as connection:
        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        )
        connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        )
        connection.execute(
            text("""
            INSERT OR IGNORE INTO tenants (id, name) VALUES ('test-tenant-id', 'Test Tenant')
        """)
        )
        connection.commit()

    try:
        Base.metadata.create_all(engine)
    except Exception:
        # Tables might already exist or have SQLite incompatibilities
        # (e.g., ARRAY columns not supported in SQLite)
        pass

    # Mirror the Postgres ``graph_outbox`` migration as SQLite TEXT
    # columns so any test using db_session can exercise the
    # ``enqueue_graph_write`` SQLite fallback path. graph_outbox is
    # defined in alembic SQL, not in SQLAlchemy Base metadata, so
    # ``Base.metadata.create_all`` doesn't cover it. This block matches
    # the schema in tests/test_bulk_upload_graph_sync_wiring.py and
    # tests/test_graph_outbox.py.
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS graph_outbox (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id       TEXT NULL,
                    operation       TEXT NOT NULL,
                    cypher          TEXT NOT NULL,
                    params          TEXT NOT NULL DEFAULT '{}',
                    status          TEXT NOT NULL DEFAULT 'pending',
                    attempts        INTEGER NOT NULL DEFAULT 0,
                    max_attempts    INTEGER NOT NULL DEFAULT 10,
                    last_error      TEXT NULL,
                    enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    drained_at      TEXT NULL,
                    next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    dedupe_key      TEXT NULL
                )
            """)
            )
    except Exception:
        pass

    yield

    try:
        Base.metadata.drop_all(engine)
    except Exception:
        pass


@pytest.fixture
def db_session(engine, tables) -> Generator[Session, None, None]:
    """Provide a transactional database session for each test."""
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# =============================================================================
# Tenant Fixtures
# =============================================================================


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Provide a consistent test tenant ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def user_id() -> uuid.UUID:
    """Provide a consistent test user ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
def client():
    """Provide a FastAPI TestClient for API testing."""
    from fastapi.testclient import TestClient

    from services.admin.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(tenant_id, user_id):
    """Provide authentication headers for API requests."""
    return {
        "X-RegEngine-API-Key": "admin",  # Test bypass key
        "X-Tenant-ID": str(tenant_id),
        "X-User-ID": str(user_id),
    }


@pytest.fixture(autouse=True)
def _clear_admin_brute_force_state():
    """Clear ``admin_auth:*`` brute-force counters in local Redis before each test.

    ``BruteForceLimiter(namespace="admin_auth")`` in services/admin/app/routes.py
    is Redis-backed whenever a reachable Redis URL is in the environment (the
    contract suite exports ``REDIS_URL=redis://localhost:6379/0`` into the
    process env). Failure counts for ip="testclient" persist across pytest
    processes, so runs within the 60s window poison each other with 429s.

    Only localhost is flushed -- a remote REDIS_URL must never be touched, and
    production stays Redis-backed (#1392).
    """
    try:
        import redis

        client = redis.Redis.from_url(
            "redis://localhost:6379/0",
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        keys = list(client.scan_iter("admin_auth:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        # No local Redis -> the limiter falls back to in-memory and each
        # pytest process starts clean; nothing to clear.
        pass
