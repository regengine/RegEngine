"""
Database session management.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://regengine:regengine@localhost:5432/regengine_admin"
)

# Production-ready connection pool configuration
# Added as part of Platform Audit remediation (P0 priority)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,                    # Validate connections before use (detect stale connections)
    pool_size=10,                          # Base connection pool size
    max_overflow=20,                       # Allow burst to 30 total connections
    pool_recycle=3600,                     # Recycle connections after 1 hour
    connect_args={
        'connect_timeout': 10,             # Connection timeout (seconds)
        'options': '-c statement_timeout=30000'  # PostgreSQL query timeout (30s)
    },
    echo_pool=os.getenv("DEBUG", "false").lower() == "true"  # Pool debugging in dev
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
