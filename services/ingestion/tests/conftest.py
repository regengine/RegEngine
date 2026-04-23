"""Ensure ``services/ingestion`` is on sys.path so bare ``from app.X`` imports
resolve correctly when pytest collects from the repo root.

The root conftest.py provides a ``pytest_collectstart`` hook for this, but
``--import-mode=importlib`` can race ahead of the hook when conftest files are
imported.  Placing an explicit sys.path insert here runs at conftest-import
time, which is guaranteed to precede any test-module import in this directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

_service_dir = str(Path(__file__).resolve().parents[1])  # services/ingestion
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

# Multiple services in this repo expose a top-level ``app`` package. When pytest
# reuses a Python process, an ``app`` module imported from another service can
# stay cached and make ingestion tests import the wrong config/auth/router code.
_cached_app = sys.modules.get("app")
_cached_app_file = str(getattr(_cached_app, "__file__", "") or "")
if _cached_app is not None and _service_dir not in _cached_app_file:
    for _key in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[_key]
