"""Regression guardrail for #1062: CORSMiddleware must be registered exactly once.

Background
----------
Historically ``services/ingestion/main.py`` installed CORSMiddleware twice:
once via the shared ``add_security()`` single-source-of-truth policy, and once
again directly in ``main.py`` with its own ``allow_origins`` / ``allow_methods``
/ ``allow_headers``. Starlette stacks middleware LIFO, so the second
registration became the outermost wrapper and silently shadowed the hardened
shared policy. Future tightening of ``shared/middleware/security.py`` would
not apply to this service.

The duplicate has been removed. This test pins that fix: if a second
CORSMiddleware is ever re-added to the ingestion app, this test fails.

Fix contract
------------
If the ingestion service needs a CORS tweak (e.g. an additional
``allow_headers`` entry like ``X-Tenant-ID``), extend ``add_security()`` in
``services/shared/middleware/security.py``. Do NOT add a second
``CORSMiddleware`` to the ingestion app.
"""

import sys
from pathlib import Path

import pytest

# Add service directory to path so ``from main import app`` resolves.
_SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

pytest.importorskip("fastapi")
pytest.importorskip("starlette")


def test_cors_registered_exactly_once() -> None:
    """The ingestion app must install CORSMiddleware exactly once (#1062)."""
    from starlette.middleware.cors import CORSMiddleware

    try:
        from main import app
    except ModuleNotFoundError as exc:  # pragma: no cover - optional deps
        pytest.skip(
            f"ingestion guardrail requires optional dependency '{exc.name}'",
        )

    cors_count = sum(1 for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors_count == 1, (
        f"CORS registered {cors_count} times; must be exactly 1. "
        "If a custom CORS tweak is needed, extend add_security() in "
        "services/shared/middleware/security.py rather than adding a second "
        "CORSMiddleware here (see #1062)."
    )
