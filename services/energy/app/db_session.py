import os
import sys
from pathlib import Path

# Standardized path discovery
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.database import create_shared_engine, get_session_factory, get_db_generator
from shared.paths import ensure_shared_importable
ensure_shared_importable()

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://regengine:regengine@localhost:5432/regengine_admin"
)

# Use shared engine and session factory
engine = create_shared_engine(DATABASE_URL)
SessionLocal = get_session_factory(engine)

def get_db():
    """Get database session for dependency injection using shared resilience logic."""
    yield from get_db_generator(SessionLocal)
