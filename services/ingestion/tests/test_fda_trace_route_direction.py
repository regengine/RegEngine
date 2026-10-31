"""Route-level tests for ``GET /api/v1/fda/trace/{tlc}``.

Gap analysis 2026-10-28, S2: the trace graph route gains a ``direction``
query parameter (forward, backward, both) and its response carries
``depth_exhausted`` so a depth-capped trace never reads as complete. No
route-level test existed for this endpoint before; the handler is driven
here with the persistence and session factory stubbed out.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.authz import IngestionPrincipal  # noqa: E402

# ``app.fda_export`` re-exports the APIRouter as ``router``; import the module
# itself so ``fetch_trace_graph_data`` can be monkeypatched where the handler
# looks it up.
fda_router_module = importlib.import_module("app.fda_export.router")

from tests.authz_overrides import (  # noqa: E402
    install_active_subscription_override,
    install_ingestion_principal_override,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"


class _FakeSession:
    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _client(monkeypatch: pytest.MonkeyPatch, captured: dict) -> TestClient:
    app = FastAPI()
    app.include_router(fda_router_module.router)
    principal = IngestionPrincipal(key_id="test-key", tenant_id=TENANT_ID, scopes=["fda.read"], auth_mode="test")
    install_ingestion_principal_override(app, principal)
    install_active_subscription_override(app)

    import shared.database as shared_database

    monkeypatch.setattr(shared_database, "SessionLocal", lambda: _FakeSession())

    def _fake_fetch(**kwargs):
        captured.update(kwargs)
        return {
            "seed_tlc": kwargs["tlc"],
            "tenant_id": kwargs["tenant_id"],
            "traversal_depth": kwargs["depth"],
            "direction": kwargs["direction"],
            "depth_exhausted": True,
            "node_count": 1,
            "edge_count": 0,
            "nodes": [{"tlc": kwargs["tlc"], "is_seed": True, "role": "seed", "depth": 0, "event_count": 0}],
            "edges": [],
            "total_events": 0,
        }

    monkeypatch.setattr(fda_router_module, "fetch_trace_graph_data", _fake_fetch)
    return TestClient(app)


def test_direction_defaults_to_both_and_depth_exhausted_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    client = _client(monkeypatch, captured)
    resp = client.get("/api/v1/fda/trace/LOT-1", params={"tenant_id": TENANT_ID})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert captured["direction"] == "both"
    assert captured["depth"] == 5
    assert captured["tenant_id"] == TENANT_ID
    assert body["direction"] == "both"
    assert body["depth_exhausted"] is True
    assert body["nodes"][0]["depth"] == 0


@pytest.mark.parametrize("direction", ["forward", "backward", "both"])
def test_direction_is_passed_through(monkeypatch: pytest.MonkeyPatch, direction: str) -> None:
    captured: dict = {}
    client = _client(monkeypatch, captured)
    resp = client.get("/api/v1/fda/trace/LOT-1", params={"tenant_id": TENANT_ID, "direction": direction, "depth": 3})
    assert resp.status_code == 200, resp.text
    assert captured["direction"] == direction
    assert captured["depth"] == 3
    assert resp.json()["direction"] == direction


def test_invalid_direction_is_rejected_with_422(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    client = _client(monkeypatch, captured)
    resp = client.get("/api/v1/fda/trace/LOT-1", params={"tenant_id": TENANT_ID, "direction": "sideways"})
    assert resp.status_code == 422
    # The handler never ran: no persistence call was made.
    assert captured == {}
