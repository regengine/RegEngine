"""Test configuration for manufacturing service.

Sets up test environment variables and fixtures.
"""
import os
import sys
from pathlib import Path
from typing import Generator
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, String, TypeDecorator
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from fastapi.testclient import TestClient

# Add parent directory to path for imports
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

# Add shared directory to path
shared_dir = service_dir.parent.parent / "shared"
sys.path.insert(0, str(shared_dir.parent))

# Set test environment variables before importing app
os.environ.setdefault("MANUFACTURING_DATABASE_URL", "sqlite:///./test_manufacturing.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "ERROR")

from app.models import Base
from app.main import app as manufacturing_app
from app.db_session import get_db


# Custom UUID type for SQLite (stores as string)
class SQLiteUUID(TypeDecorator):
    """SQLite-compatible UUID type that stores UUIDs as strings."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


@pytest.fixture(scope="session")
def engine():
    """Create a test database engine."""
    # Override UUID type for SQLite
    from sqlalchemy.dialects import registry
    registry.register("sqlite", "sqlalchemy.dialects.sqlite", "dialect")
    
    test_engine = create_engine(
        "sqlite:///./test_manufacturing.db",
        connect_args={"check_same_thread": False}
    )
    
    # Monkey-patch UUID columns to use string for SQLite
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, UUID):
                column.type = SQLiteUUID()
    
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        # Clean up all tables after each test
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    manufacturing_app.dependency_overrides[get_db] = override_get_db
    with TestClient(manufacturing_app) as test_client:
        yield test_client
    manufacturing_app.dependency_overrides.clear()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Provide a fixed tenant ID for testing."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def auth_headers(tenant_id) -> dict:
    """Provide authentication headers for requests."""
    return {
        "X-RegEngine-API-Key": "test-api-key-123",
        "X-Tenant-ID": str(tenant_id),
        "Content-Type": "application/json"
    }


@pytest.fixture
def sample_ncr_data() -> dict:
    """Provide sample NCR data for testing."""
    import time
    # Use timestamp to make NCR numbers unique per test
    unique_id = str(int(time.time() * 1000))[-6:]
    return {
        "ncr_number": f"NCR-2024-{unique_id}",
        "detected_date": "2024-01-15T10:30:00",
        "detected_by": "John Smith",
        "detection_source": "INTERNAL_AUDIT",
        "part_number": "PART-001",
        "lot_number": "LOT-2024-001",
        "quantity_affected": 100,
        "description": "Surface finish out of specification",
        "severity": "MAJOR",
        "containment_action": "Quarantine affected parts",
        "iso_9001_relevant": True,
        "iso_14001_relevant": False,
        "iso_45001_relevant": False
    }


@pytest.fixture
def sample_capa_data() -> dict:
    """Provide sample CAPA data for testing."""
    return {
        "ncr_id": 1,
        "action_type": "CORRECTIVE",
        "description": "Implement process monitoring checks",
        "assigned_to": "Jane Doe",
        "due_date": "2024-03-15T17:00:00",
        "verification_required": True
    }


@pytest.fixture
def sample_supplier_issue_data() -> dict:
    """Provide sample supplier issue data for testing."""
    return {
        "supplier_name": "ABC Suppliers Inc",
        "supplier_code": "SUP-001",
        "issue_date": "2024-01-20T14:00:00",
        "part_number": "PART-002",
        "lot_number": "LOT-2024-002",
        "defect_description": "Material hardness below specification"
    }


@pytest.fixture
def sample_audit_finding_data() -> dict:
    """Provide sample audit finding data for testing."""
    import time
    # Use timestamp to make finding numbers unique per test
    unique_id = str(int(time.time() * 1000))[-6:]
    return {
        "audit_type": "INTERNAL",
        "audit_date": "2024-01-10T09:00:00",
        "auditor_name": "Sarah Johnson",
        "finding_number": f"AF-2024-{unique_id}",
        "clause_reference": "8.5.1",
        "finding_type": "MINOR_NC",
        "description": "Process documentation incomplete",
        "target_closure_date": "2024-02-10T17:00:00"
    }
