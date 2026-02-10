"""
Test configuration and fixtures with PostgreSQL UUID support for SQLite.

The Manufacturing service uses PostgreSQL-specific UUID types which aren't natively
supported in SQLite. This conftest patches the PGUUID type at import time
to use a custom TypeDecorator that works with SQLite.
"""
import pytest
import uuid as uuid_module
import sys
from pathlib import Path
from sqlalchemy import create_engine, TypeDecorator, CHAR
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure manufacturing service is on the path and clear any conflicting 'app' modules
_manufacturing_dir = Path(__file__).resolve().parent.parent
# Remove any previously-cached 'app' module from other services to avoid cross-contamination
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.')]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(_manufacturing_dir))

# First, create the custom UUID type for SQLite
class SqliteUUID(TypeDecorator):
    """Cross-database UUID type that works with SQLite."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert UUID to string for storage."""
        if value is None:
            return None
        if hasattr(value, 'hex'):
            # It's already a UUID object
            return str(value)
        # It's a string, validate and return
        return str(uuid_module.UUID(value))

    def process_result_value(self, value, dialect):
        """Convert string back to UUID."""
        if value is None:
            return None
        return uuid_module.UUID(value)


# Monkey-patch PostgreSQL UUID type BEFORE any models are imported
import sqlalchemy.dialects.postgresql as postgresql
postgresql.UUID = SqliteUUID

# NOW we can import the database models
try:
    from app.models import Base
except ImportError:
    from services.manufacturing.app.models import Base


@pytest.fixture(scope="session")
def test_db_engine():
    """Create test database engine with patched UUID support."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Enable foreign key constraints in SQLite
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(test_db_engine):
    """Create isolated database session for each test.

    After each test, all rows are deleted from all tables to ensure
    complete data isolation. This approach is simpler than nested
    transactions and compatible with code that calls commit/rollback
    internally.
    """
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        # Clean up: rollback any pending transaction, then delete all data
        try:
            session.rollback()
        except Exception:
            pass
        # Delete all rows from all tables (order matters for FK constraints)
        cleanup_session = Session()
        try:
            for table in reversed(Base.metadata.sorted_tables):
                cleanup_session.execute(table.delete())
            cleanup_session.commit()
        except Exception:
            cleanup_session.rollback()
        finally:
            cleanup_session.close()
        session.close()


@pytest.fixture(scope="function")
def test_session_factory(test_db_engine):
    """Provide a sessionmaker bound to the test engine.

    Used by tests that need to create additional sessions (e.g. concurrency tests)
    instead of importing the production SessionLocal which points at PostgreSQL.
    """
    return sessionmaker(bind=test_db_engine)


# ── Application Fixtures ─────────────────────────────

@pytest.fixture
def tenant_id():
    """Generate a test tenant UUID string."""
    return str(uuid_module.uuid4())


@pytest.fixture
def auth_headers(tenant_id):
    """Standard auth headers for testing, including tenant ID."""
    return {
        "X-RegEngine-API-Key": "test-key",
        "X-RegEngine-Tenant-ID": tenant_id,
    }


@pytest.fixture
def client(db_session, tenant_id):
    """FastAPI test client with dependency overrides.
    
    Overrides get_db to use the in-memory test database.
    """
    from fastapi.testclient import TestClient
    try:
        from app.main import app
        from app.db_session import get_db
    except ImportError:
        from services.manufacturing.app.main import app
        from services.manufacturing.app.db_session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ── Sample Data Fixtures ─────────────────────────────

@pytest.fixture
def sample_ncr_data():
    """Sample NCR creation payload."""
    from datetime import datetime
    return {
        "ncr_number": f"NCR-TEST-{uuid_module.uuid4().hex[:8].upper()}",
        "detected_date": datetime.utcnow().isoformat(),
        "detected_by": "Test Inspector",
        "detection_source": "INTERNAL_AUDIT",
        "part_number": "PART-001",
        "lot_number": "LOT-2024-A",
        "quantity_affected": 10,
        "description": "Surface finish defect detected during inspection",
        "severity": "MAJOR",
        "iso_9001_relevant": True,
        "iso_14001_relevant": False,
        "iso_45001_relevant": False,
    }


@pytest.fixture
def sample_capa_data():
    """Sample CAPA creation payload (ncr_id to be set by test)."""
    from datetime import datetime, timedelta
    return {
        "ncr_id": 1,
        "action_type": "CORRECTIVE",
        "description": "Retrain operators on surface finish requirements per SOP-QA-101",
        "assigned_to": "Quality Manager",
        "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "verification_required": True,
    }


@pytest.fixture
def sample_supplier_issue_data():
    """Sample supplier quality issue payload."""
    from datetime import datetime
    return {
        "supplier_name": "ABC Suppliers Inc",
        "supplier_code": "SUP-001",
        "issue_date": datetime.utcnow().isoformat(),
        "part_number": "RAW-MAT-042",
        "lot_number": "LOT-EXT-2024-B",
        "defect_description": "Incoming material hardness below specification (HRC 58 required, HRC 52 measured)",
    }


@pytest.fixture
def sample_audit_finding_data():
    """Sample audit finding payload."""
    from datetime import datetime, timedelta
    return {
        "audit_type": "INTERNAL",
        "audit_date": datetime.utcnow().isoformat(),
        "auditor_name": "Lead Auditor",
        "finding_number": f"AF-TEST-{uuid_module.uuid4().hex[:8].upper()}",
        "clause_reference": "8.5.1",
        "finding_type": "MINOR_NC",
        "description": "Calibration records for CMM machine not updated within required interval",
        "target_closure_date": (datetime.utcnow() + timedelta(days=14)).isoformat(),
    }

