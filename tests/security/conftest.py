"""Conftest for security tests — ensures shared modules are importable."""
import sys
import os
from pathlib import Path

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ensure services/shared is importable as 'shared'
_SERVICES_DIR = _PROJECT_ROOT / "services"
for p in (str(_PROJECT_ROOT), str(_SERVICES_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from shared.paths import ensure_shared_importable
ensure_shared_importable()

# Default env vars for test isolation
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("INTERNAL_SERVICE_SECRET", "trusted-internal-v1")
