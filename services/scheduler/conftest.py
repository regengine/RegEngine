"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE pydantic tries to validate
os.environ.setdefault("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# #1084: allow private/unresolvable hosts in tests so existing notification
# test fixtures (hook1.example.com, hook.example.com) work without real DNS.
# The SSRF guard itself is covered in test_webhook_notifier_ssrf_1084.py.
os.environ.setdefault("WEBHOOK_ALLOW_PRIVATE", "true")
os.environ.setdefault("WEBHOOK_ALLOW_HTTP", "true")

# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parent           # services/scheduler/
_SERVICES_DIR = _SERVICE_DIR.parent                      # services/
# The service dir goes in first so `from app.X import ...` resolves against
# this service's app/. The services dir stays in path for shared/cross-
# service imports.
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------
