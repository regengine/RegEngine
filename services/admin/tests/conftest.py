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
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO tenants (id, name) VALUES ('test-tenant-id', 'Test Tenant')
        """))
        connection.commit()

    try:
        Base.metadata.create_all(engine)
    except Exception:
        # Tables might already exist or have SQLite incompatibilities
        # (e.g., ARRAY columns not supported in SQLite)
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
