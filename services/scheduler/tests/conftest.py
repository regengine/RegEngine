"""Static import context for the scheduler test tree.

Service dir on sys.path so any remaining bare service-local imports resolve
without the deleted root-conftest flipper. See the root conftest for the
full rationale.
"""

from __future__ import annotations

import sys
from pathlib import Path

_service_dir = str(Path(__file__).resolve().parents[1])  # services/scheduler
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)
