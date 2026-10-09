"""Regression: /system/metrics must not assume chain validity.

The metrics endpoint used to report ``chain_valid=True`` whenever supplier
rows existed but the ingestion chain-verify service was silent. Supplier
rows carry sequence numbers but their hashes are never verified in this
endpoint, so unverified validity is reported as unknown (None).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


async def _run_metrics(monkeypatch, chain_payload, supplier_scalar):
    from services.admin.app import system_routes as routes_mod

    tenant_id = "11111111-1111-4111-8111-111111111111"

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        async def get(self, url, **kwargs):
            if "/compliance/score/" in url:
                return FakeResponse({"events_analyzed": 1})
            return FakeResponse(chain_payload)

    class FakeResilientClient:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    db = MagicMock()
    result = MagicMock()
    result.scalar.return_value = supplier_scalar
    result.fetchone.return_value = (0,)
    db.execute.return_value = result

    monkeypatch.setenv("REGENGINE_SYSTEM_METRICS_API_KEY", "server-side-service-key")
    monkeypatch.setenv("REGENGINE_SYSTEM_METRICS_TENANT_ID", tenant_id)
    monkeypatch.setattr(routes_mod, "_get_ingestion_base", lambda: "https://ingestion.test")
    monkeypatch.setattr(routes_mod, "_resolve_tenant", lambda _db: tenant_id)
    monkeypatch.setattr(routes_mod, "resilient_client", lambda **_kwargs: FakeResilientClient())

    return await routes_mod.get_system_metrics(
        current_user=SimpleNamespace(id="user-1"),
        db=db,
    )


@pytest.mark.asyncio
async def test_chain_valid_unknown_when_verifier_silent(monkeypatch):
    """Supplier rows present but no verifier answer must report unknown."""
    response = await _run_metrics(monkeypatch, {}, 5)
    assert response.chain_valid is None


@pytest.mark.asyncio
async def test_chain_valid_passes_through_verifier_answer(monkeypatch):
    """Explicit verifier True/False answers must be reported unchanged."""
    assert (await _run_metrics(monkeypatch, {"chain_valid": True}, 5)).chain_valid is True
    assert (await _run_metrics(monkeypatch, {"chain_valid": False}, 5)).chain_valid is False
