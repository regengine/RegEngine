"""Test environment configuration for pytest.

Automatically loads test environment variables before any test imports.
"""

import os

# Set test environment variables BEFORE pydantic tries to validate
# sqlite, NOT the live dev regengine URL: a Postgres dev default here armed
# every reachable-DB test against the developer's real database (2026-07-25
# incident). CI exports real service-container URLs explicitly.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# --- Standardized Bootstrap ---
import sys
from pathlib import Path

import pytest

_SERVICE_DIR = Path(__file__).resolve().parent  # services/scheduler/
_SERVICES_DIR = _SERVICE_DIR.parent  # services/
# The service dir goes in first so `from app.X import ...` resolves against
# this service's app/. The services dir stays in path for shared/cross-
# service imports.
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _module_loaded_outside_scheduler(name: str) -> bool:
    module = sys.modules.get(name)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        return not Path(module_file).resolve().is_relative_to(_SERVICE_DIR)
    except OSError:
        return False


# Several legacy service tests import bare ``main`` or ``app.*``. During a
# full-suite run, another service may have already populated those aliases.
if _module_loaded_outside_scheduler("main"):
    sys.modules.pop("main", None)
if _module_loaded_outside_scheduler("app"):
    for _name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
        sys.modules.pop(_name, None)


@pytest.fixture(autouse=True)
def _evict_cross_service_aliases() -> None:
    """Keep bare legacy imports pointed at the scheduler during full-suite runs."""
    if _module_loaded_outside_scheduler("main"):
        sys.modules.pop("main", None)
    if _module_loaded_outside_scheduler("app"):
        for name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
            sys.modules.pop(name, None)


from shared.paths import ensure_shared_importable

ensure_shared_importable()
# ------------------------------
