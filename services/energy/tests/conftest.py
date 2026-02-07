"""
Test configuration and fixtures with PostgreSQL UUID support for SQLite.

The Energy service uses PostgreSQL-specific UUID types which aren't natively
supported in SQLite. This conftest patches the PGUUID type at import time
to use a custom TypeDecorator that works with SQLite.
"""
import pytest
import uuid as uuid_module
from sqlalchemy import create_engine, TypeDecorator, CHAR
from sqlalchemy.orm import sessionmaker

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
from app.database import Base
from app.idempotency import SnapshotIdempotencyModel  # Import idempotency model too


@pytest.fixture(scope="session")
def test_db_engine():
    """Create test database engine with patched UUID support."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    
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
    """Create isolated database session for each test."""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    try:
        yield session
    except Exception:
        # Exception during test execution
        session.rollback()
        raise
    else:
        # Test completed successfully, try to commit
        try:
            session.commit()
        except Exception:
            # Commit failed (expected in some tests like constraint violation tests)
            session.rollback()
    finally:
        session.close()
