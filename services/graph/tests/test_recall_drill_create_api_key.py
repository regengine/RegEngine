"""Regression test: POST /fsma/recall/drill must accept the APIKey model.

The handler previously called ``api_key.get("user_id", ...)``, treating the
authenticated principal as a dict. ``require_api_key`` returns an
``APIKey`` / ``APIKeyResponse`` model, which has no ``.get``, so every drill
creation raised ``AttributeError`` and the handler's blanket ``except``
turned it into a 500.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared.auth import APIKey

from services.graph.app.routers.fsma import recall as recall_router

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _make_request():
    """Minimal Starlette Request satisfying slowapi's limiter wrapper."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "path": "/fsma/recall/drill",
        "query_string": b"",
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": MagicMock(state=MagicMock()),
    }
    return Request(scope)


def _make_api_key():
    return APIKey(
        key_id="rge_testkey123",
        key_hash="hash",
        name="Test Key",
        tenant_id=str(TENANT),
        created_at=datetime.now(timezone.utc),
    )


def _make_engine():
    from services.graph.app.fsma_recall import MockRecallEngine

    return MockRecallEngine(
        trace_forward_fn=lambda lot, tenant_id: {"lots": [lot], "hop_count": 1},
        trace_backward_fn=lambda lot, tenant_id: {"lots": [lot], "hop_count": 1},
    )


async def test_create_drill_with_real_api_key_model_succeeds():
    """Drill creation with a real APIKey model succeeds and records key_id."""
    request = _make_request()
    api_key = _make_api_key()
    payload = recall_router.CreateDrillRequest(
        type="forward_trace",
        target_tlc="LOT-001",
        severity="class_ii",
        reason="manual_drill",
    )
    with patch.object(recall_router, "get_recall_engine", return_value=_make_engine()):
        resp = await recall_router.create_recall_drill(
            request=request,
            payload=payload,
            tenant_id=TENANT,
            api_key=api_key,
        )
    assert resp["initiated_by"] == "rge_testkey123"
    assert resp["tenant_id"] == str(TENANT)


async def test_create_drill_without_key_id_falls_back_to_api_user():
    """A principal with no key_id still creates a drill (fallback actor)."""
    request = _make_request()
    payload = recall_router.CreateDrillRequest(
        type="forward_trace",
        target_tlc="LOT-002",
        severity="class_ii",
        reason="manual_drill",
    )
    with patch.object(recall_router, "get_recall_engine", return_value=_make_engine()):
        resp = await recall_router.create_recall_drill(
            request=request,
            payload=payload,
            tenant_id=TENANT,
            api_key=SimpleNamespace(),
        )
    assert resp["initiated_by"] == "api_user"
