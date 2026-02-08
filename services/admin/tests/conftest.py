"""
PCOS Test Configuration and Fixtures

Provides shared fixtures for testing the Production Compliance OS module.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Add app to path
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.admin.app.pcos_models import (
    PCOSCompanyModel,
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSPersonModel,
    PCOSEngagementModel,
    PCOSTimecardModel,
    PCOSTaskModel,
    PCOSEvidenceModel,
    EntityType,
    LocationType,
    Jurisdiction,
    ClassificationType,
    GateState,
    TaskStatus,
    EvidenceType,
    ProjectType,
)


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite database for testing."""
    # Use in-memory SQLite for fast tests
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
    from services.admin.app.pcos_models import PCOSCompanyModel  # Import to register models
    
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
# Domain Object Fixtures
# =============================================================================

@pytest.fixture
def sample_company(tenant_id: uuid.UUID) -> dict:
    """Provide sample company data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "legal_name": "Test Productions LLC",
        "dba_name": "Test Films",
        "entity_type": EntityType.LLC_SINGLE_MEMBER,
        "ein": "12-3456789",
        "has_la_city_presence": True,
        "mailing_address": "123 Test St, Los Angeles, CA 90001",
        "physical_address": "123 Test St, Los Angeles, CA 90001",
        "owner_pay_mode": "owner_draw",
        "status": "active",
    }


@pytest.fixture
def sample_project(tenant_id: uuid.UUID, sample_company: dict) -> dict:
    """Provide sample project data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "company_id": sample_company["id"],
        "name": "Test Commercial 2026",
        "project_type": ProjectType.COMMERCIAL,
        "is_commercial": True,
        "first_shoot_date": date.today() + timedelta(days=30),
        "last_shoot_date": date.today() + timedelta(days=32),
        "union_status": "non_union",
        "minor_involved": False,
        "gate_state": GateState.DRAFT,
        "risk_score": 0,
    }


@pytest.fixture
def sample_location(tenant_id: uuid.UUID, sample_project: dict) -> dict:
    """Provide sample location data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": sample_project["id"],
        "name": "Downtown LA Office",
        "address": "456 Main St, Los Angeles, CA 90012",
        "location_type": LocationType.PRIVATE_PROPERTY,
        "jurisdiction": Jurisdiction.LA_CITY,
        "is_certified_studio": False,
        "requires_permit": True,
        "shoot_dates": [date.today() + timedelta(days=30)],
    }


@pytest.fixture
def sample_person(tenant_id: uuid.UUID) -> dict:
    """Provide sample person data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "legal_name": "John Smith",
        "email": "john@example.com",
        "phone": "310-555-0100",
        "ssn_last_four": "1234",
        "is_minor": False,
    }


@pytest.fixture
def sample_engagement(
    tenant_id: uuid.UUID,
    sample_project: dict,
    sample_person: dict
) -> dict:
    """Provide sample engagement data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": sample_project["id"],
        "person_id": sample_person["id"],
        "role": "Camera Operator",
        "department": "Camera",
        "classification": ClassificationType.CONTRACTOR,
        "daily_rate": 650.00,
        "start_date": date.today() + timedelta(days=30),
        "end_date": date.today() + timedelta(days=32),
        "status": "active",
    }


@pytest.fixture
def sample_timecard(
    tenant_id: uuid.UUID,
    sample_engagement: dict
) -> dict:
    """Provide sample timecard data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "engagement_id": sample_engagement["id"],
        "work_date": date.today() + timedelta(days=30),
        "call_time": "07:00",
        "wrap_time": "19:00",
        "meal_break_minutes": 60,
        "hours_worked": 11.0,
        "daily_rate": 650.00,
        "status": "pending",
        "wage_floor_met": True,
    }


@pytest.fixture
def sample_task(tenant_id: uuid.UUID, sample_project: dict) -> dict:
    """Provide sample task data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": sample_project["id"],
        "task_type": "filmla_permit_packet",
        "title": "Submit FilmLA Permit Application",
        "description": "Complete and submit the FilmLA permit packet for public ROW filming",
        "status": TaskStatus.PENDING,
        "is_blocking": True,
        "due_date": date.today() + timedelta(days=14),
        "assigned_role": "production_admin",
    }


@pytest.fixture
def sample_evidence(
    tenant_id: uuid.UUID,
    sample_project: dict
) -> dict:
    """Provide sample evidence data."""
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": sample_project["id"],
        "evidence_type": EvidenceType.PERMIT_APPROVED,
        "file_name": "filmla_permit_approved.pdf",
        "file_path": "/evidence/projects/test/filmla_permit_approved.pdf",
        "content_type": "application/pdf",
        "file_size_bytes": 102400,
        "uploaded_at": datetime.now(timezone.utc),
        "status": "verified",
    }


# =============================================================================
# Mock Service Fixtures
# =============================================================================

@pytest.fixture
def mock_gate_evaluator():
    """Provide a mock gate evaluator."""
    evaluator = MagicMock()
    evaluator.evaluate.return_value = MagicMock(
        project_id=uuid.uuid4(),
        current_state=GateState.DRAFT,
        can_transition=True,
        blocking_tasks_count=0,
        blocking_tasks=[],
        missing_evidence=[],
        risk_score=0,
        reasons=[],
    )
    return evaluator


# =============================================================================
# Test Data Generators
# =============================================================================

def create_test_company(session: Session, tenant_id: uuid.UUID, **overrides) -> PCOSCompanyModel:
    """Create a company record in the database."""
    data = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "legal_name": f"Test Company {uuid.uuid4().hex[:8]}",
        "entity_type": EntityType.LLC_SINGLE_MEMBER,
        "has_la_city_presence": True,
        "status": "active",
    }
    data.update(overrides)
    
    company = PCOSCompanyModel(**data)
    session.add(company)
    session.commit()
    return company


def create_test_project(
    session: Session,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    **overrides
) -> PCOSProjectModel:
    """Create a project record in the database."""
    data = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "name": f"Test Project {uuid.uuid4().hex[:8]}",
        "project_type": ProjectType.COMMERCIAL,
        "is_commercial": True,
        "gate_state": GateState.DRAFT,
        "first_shoot_date": date.today() + timedelta(days=30),
    }
    data.update(overrides)
    
    project = PCOSProjectModel(**data)
    session.add(project)
    session.commit()
    return project


def create_test_task(
    session: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    is_blocking: bool = True,
    status: TaskStatus = TaskStatus.PENDING,
    **overrides
) -> PCOSTaskModel:
    """Create a task record in the database."""
    data = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "task_type": "test_task",
        "title": f"Test Task {uuid.uuid4().hex[:8]}",
        "status": status,
        "is_blocking": is_blocking,
    }
    data.update(overrides)
    
    task = PCOSTaskModel(**data)
    session.add(task)
    session.commit()
    return task


def create_test_evidence(
    session: Session,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    evidence_type: EvidenceType,
    **overrides
) -> PCOSEvidenceModel:
    """Create an evidence record in the database."""
    data = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "evidence_type": evidence_type,
        "file_name": f"test_evidence_{uuid.uuid4().hex[:8]}.pdf",
        "file_path": f"/evidence/test_{uuid.uuid4().hex}.pdf",
        "content_type": "application/pdf",
        "file_size_bytes": 1024,
        "status": "verified",
    }
    data.update(overrides)
    
    evidence = PCOSEvidenceModel(**data)
    session.add(evidence)
    session.commit()
    return evidence


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
        "X-API-Key": "admin",  # Test bypass key
        "X-Tenant-ID": str(tenant_id),
        "X-User-ID": str(user_id),
    }
