"""Static import context for the ingestion test tree.

Historically this conftest also purged ``app``/``shared``/
``regengine_ingestion`` modules at every test setup to defend against
synthetic module injection by sibling tests. That purge is deleted together
with the root-conftest flipper: test imports are canonical
(``services.ingestion.app.*``), synthetic ``app.*`` stubs no longer shadow
the real package for anyone, and module identity is stable for the whole
run. The explicit ``sys.path`` insert stays as a safety net for the few
remaining bare-import stragglers and for ``--import-mode=importlib``
collection races (conftest import precedes any test-module import here).
"""

from __future__ import annotations

import sys
from pathlib import Path

_service_dir = str(Path(__file__).resolve().parents[1])  # services/ingestion
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)
