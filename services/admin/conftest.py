"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE pydantic tries to validate
os.environ.setdefault("ADMIN_MASTER_KEY", "admin-master-key-dev")
os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
os.environ.setdefault("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine_admin")
os.environ.setdefault("ENABLE_DB_API_KEYS", "false")  # Use in-memory store in tests (no api_keys table in CI)
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("AUTH_SECRET_KEY", "dev_secret_key_change_me")

# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------
