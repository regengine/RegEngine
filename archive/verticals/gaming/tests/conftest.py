"""
Test configuration and fixtures with PostgreSQL UUID support for SQLite.

The Gaming service uses PostgreSQL-specific UUID types which aren't natively
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

# Ensure gaming service is on the path and clear any conflicting 'app' modules
_gaming_dir = Path(__file__).resolve().parent.parent
# Remove any previously-cached 'app' module from other services to avoid cross-contamination
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.')]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(_gaming_dir))

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
    from services.gaming.app.models import Base


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
