"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""
import os

# Set test environment variables BEFORE any imports  
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("GRAPH_SERVICE_URL", "http://localhost:8200")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test-password-for-ci")
# Fixed HMAC key so producer / consumer round-trips work in unit
# tests without hitting a real KMS / secret store (#1078).
os.environ.setdefault("KAFKA_EVENT_SIGNING_KEY", "test-nlp-kafka-signing-key-ci-only")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# --- Standardized Bootstrap ---
import sys
from pathlib import Path
_SERVICE_DIR = Path(__file__).resolve().parent        # services/graph/
_SERVICES_DIR = _SERVICE_DIR.parent                   # services/
_REPO_ROOT = _SERVICES_DIR.parent                     # repo root

# Insert repo root FIRST so local kernel/ package takes precedence
# over any pip-installed 'kernel' module
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

# Force-clear any pip-installed 'kernel' module that shadows repo kernel/
if 'kernel' in sys.modules:
    _cached = sys.modules['kernel']
    _cached_file = str(getattr(_cached, '__file__', '') or '')
    if 'site-packages' in _cached_file or not hasattr(_cached, '__path__'):
        for _key in [k for k in sys.modules if k == 'kernel' or k.startswith('kernel.')]:
            del sys.modules[_key]

from shared.paths import ensure_shared_importable
ensure_shared_importable()
# ------------------------------
