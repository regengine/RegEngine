"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE any imports
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")  
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-ingestion-bucket")
os.environ.setdefault("OBJECT_STORAGE_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Subscription gate fails closed when Redis is unreachable (correct in
# prod, wrong for tests that don't ship a Redis). Default to fail-open
# here; the gate's own dedicated tests (test_subscription_gate_fail_closed.py)
# patch os.getenv so they exercise both paths regardless of this default.
os.environ.setdefault("SUBSCRIPTION_GATE_FAIL_OPEN", "true")

# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parent           # services/ingestion/
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
