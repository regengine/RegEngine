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
_SERVICE_DIR = Path(__file__).resolve().parent           # services/admin/
_SERVICES_DIR = _SERVICE_DIR.parent                      # services/
# The service dir goes in first so `from app.bulk_upload.parsers import ...`
# resolves against this service's app/ (the test files use the short `app.`
# prefix, not `admin.app.`). The services dir stays in path so shared/cross-
# service imports continue to work.
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------
