"""Static import context for the compliance test tree.

Service dir on sys.path so any remaining bare service-local imports resolve
without the deleted root-conftest flipper. See the root conftest for the
full rationale.
"""

from __future__ import annotations

import sys
from pathlib import Path

_service_dir = str(Path(__file__).resolve().parents[1])  # services/compliance
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

# Import-time environment the compliance app expects under test (previously
# pinned by the root-conftest flipper whenever the compliance service became
# active; now pinned statically for this tree).
import os as _os

_os.environ["REGENGINE_ENV"] = "test"
_os.environ["ENVIRONMENT"] = "test"
_os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
_os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-for-pytest")
