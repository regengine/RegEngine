"""FTL-commodity scoping tests for POST /validate (issue #1105).

FSMA 204 applies ONLY to foods on the FDA Food Traceability List. Issue
#1105 covers the false-positive risk where a caller submitting a non-FTL
food (bananas, apples, beef) received a clean validation response — a
compliance stamp for an out-of-scope product.

These tests exercise the catalog-level gate added to
``services/compliance/app/routes.py`` at POST /validate:

1. ``test_non_ftl_food_rejected`` — a commodity absent from the FTL
   catalog returns HTTP 400 with ``detail == "E_NON_FTL_FOOD"``.
2. ``test_ftl_commodity_required`` — omitting the field returns HTTP 422
   via Pydantic validation, so callers cannot accidentally skip scoping.
3. ``test_valid_ftl_commodity_passes_basic_validation`` — a real FTL
   commodity ("leafy_greens") clears the gate and returns 200 with a
   normalized ``ftl_commodity`` echoed back.

The shared FTL catalog we import from is
``services/shared/rules/ftl.FTL_CATEGORIES``.
"""

from __future__ import annotations

# Environment must be set BEFORE importing app — the service's main.py
# validates config at import time.
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REGENGINE_ENV", "test")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-1105")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-1105-at-least-sixteen-chars")
os.environ.setdefault("API_KEY", "test-api-key-1105")

import sys
from pathlib import Path

# Match the pattern in other compliance tests — ensure the service dir is
# on sys.path so ``from main import app`` resolves, and clear any cached
# ``app`` module from a sibling service that may have been imported first.
_SERVICE_DIR = Path(__file__).resolve().parent.parent
_to_remove = [k for k in sys.modules if k == "app" or k.startswith("app.") or k == "main"]
for _k in _to_remove:
    del sys.modules[_k]
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import pytest
from fastapi.testclient import TestClient

from main import app  # noqa: E402 — path must be set first


client = TestClient(app)

# The bypass token configured above is accepted by shared/auth.py when
# REGENGINE_ENV == "test". Any endpoint guarded by ``require_api_key``
# will treat this header as a valid request.
AUTH_HEADER = {"X-RegEngine-API-Key": os.environ["AUTH_TEST_BYPASS_TOKEN"]}


class TestValidateFTLScoping:
    """Catalog-level FTL gate on POST /validate (#1105)."""

    def test_non_ftl_food_rejected(self) -> None:
        """A commodity not on the FDA FTL catalog returns 400 E_NON_FTL_FOOD.

        Bananas are the canonical non-FTL example — they are a common food
        FSMA 204 does not cover, and receiving a "compliant" stamp for
        them is the false-positive this issue fixes.

        The compliance service installs a shared exception handler that
        wraps HTTPException detail as ``{"error": {"type": ..., "message": ...}}``;
        we also accept the vanilla FastAPI ``{"detail": ...}`` shape so
        this test doesn't break if the handler layout is refactored.
        """
        resp = client.post(
            "/validate",
            json={"ftl_commodity": "bananas"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        # Support both the wrapped ("error":{"message":...}) and raw
        # ("detail":"...") shapes so a handler refactor doesn't flake this.
        message = (
            body.get("detail")
            or (body.get("error") or {}).get("message")
        )
        assert message == "E_NON_FTL_FOOD", body

    def test_ftl_commodity_required(self) -> None:
        """Omitting ``ftl_commodity`` returns 422 via Pydantic validation.

        The field is required at the schema layer specifically so a caller
        cannot silently skip FTL scoping; dropping to a default would
        re-open the false-positive path.
        """
        resp = client.post(
            "/validate",
            json={},  # no ftl_commodity field at all
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        # The shared exception handler reshapes the Pydantic error envelope
        # to ``{"error": {"type": "validation_error", "details": [...]}}``;
        # raw FastAPI would return ``{"detail": [...]}``. Accept either.
        details = (
            body.get("detail")
            or (body.get("error") or {}).get("details")
        )
        assert details, body
        if isinstance(details, list):
            assert any(
                "ftl_commodity" in str(err.get("loc", [])) for err in details
            ), details

    def test_valid_ftl_commodity_passes_basic_validation(self) -> None:
        """A real FTL commodity clears the gate and returns 200.

        ``leafy_greens`` is in the FTL catalog (stored as "leafy greens")
        — the endpoint canonicalizes underscores to spaces before the
        membership check, so either form is accepted.
        """
        resp = client.post(
            "/validate",
            json={"ftl_commodity": "leafy_greens"},
            headers=AUTH_HEADER,
        )
        # The gate passes — deeper rule-engine logic is pending #1203,
        # so the handler currently returns a clean 200.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["valid"] is True
        assert body["ftl_commodity"] == "leafy greens"
        assert body["errors"] == []
