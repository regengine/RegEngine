"""SSRF refusal and size-cap tests for vendor connectors.

``SafetyCultureConnector``, ``FoodReadyConnector``, ``FoodDocsConnector``
and ``TiveConnector`` take a tenant-configurable ``base_url``. Every
outbound GET must go through ``shared.safe_http.safe_httpx_get_async``,
which validates each hop and caps the response body, instead of a raw
``httpx.AsyncClient``.

Every test fails on the pre-fix code, which has no ``safe_httpx_get_async``
symbol in these modules.
"""

from __future__ import annotations

import httpx
import pytest

from services.shared.external_connectors.base import ConnectorConfig
from services.shared.external_connectors.food_safety import (
    FoodDocsConnector,
    FoodReadyConnector,
    TiveConnector,
)
from services.shared.external_connectors.safetyculture import SafetyCultureConnector


def _config(base_url: str = "https://api.example.com") -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="c1",
        display_name="test",
        category="food_safety",
        tenant_id="t1",
        base_url=base_url,
        api_key="key-123",
    )


def _ok_response(payload) -> httpx.Response:
    import json

    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})


async def test_safetyculture_routes_through_safe_helper(monkeypatch):
    import services.shared.external_connectors.safetyculture as sc_module

    calls: list = []

    async def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        assert kwargs.get("max_bytes", 0) > 0, "connector fetch must carry a size cap"
        return _ok_response({"organisation_id": "org-1", "email": "ops@example.com"})

    monkeypatch.setattr(sc_module, "safe_httpx_get_async", fake_get)

    connector = SafetyCultureConnector(_config(base_url="https://api.safetyculture.io"))
    assert await connector.test_connection() is True
    assert len(calls) == 1
    assert calls[0][0] == "https://api.safetyculture.io/users/v1/users/me"


async def test_safetyculture_private_base_url_is_refused():
    from shared.url_validation import SSRFError

    connector = SafetyCultureConnector(_config(base_url="http://127.0.0.1:9"))
    assert await connector.test_connection() is False
    with pytest.raises(SSRFError):
        await connector.fetch_events(limit=10)


async def test_safetyculture_oversized_response_is_refused(monkeypatch):
    from shared.safe_http import ResponseTooLargeError

    import services.shared.external_connectors.safetyculture as sc_module

    async def too_big(url, **kwargs):
        raise ResponseTooLargeError("Response body exceeds 5242880 bytes")

    monkeypatch.setattr(sc_module, "safe_httpx_get_async", too_big)

    connector = SafetyCultureConnector(_config())
    assert await connector.test_connection() is False
    with pytest.raises(ResponseTooLargeError):
        await connector.fetch_events(limit=10)


@pytest.mark.parametrize(
    ("cls", "path"),
    [
        (FoodReadyConnector, "/records"),
        (FoodDocsConnector, "/monitoring-tasks"),
        (TiveConnector, "/shipments"),
    ],
)
async def test_food_safety_fetch_refuses_ssrf_gracefully(monkeypatch, cls, path):
    from shared.url_validation import SSRFError

    import services.shared.external_connectors.food_safety as fs_module

    calls: list = []

    async def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        assert kwargs.get("max_bytes", 0) > 0, "connector fetch must carry a size cap"
        raise SSRFError("Resolved IP 127.0.0.1 is not a public global address")

    monkeypatch.setattr(fs_module, "safe_httpx_get_async", fake_get)

    connector = cls(_config(base_url="http://127.0.0.1:9"))
    events, cursor = await connector.fetch_events(limit=10)
    assert events == [] and cursor is None
    assert len(calls) == 1
    assert calls[0][0].endswith(path)


@pytest.mark.parametrize("cls", [FoodReadyConnector, TiveConnector])
async def test_food_safety_test_connection_refuses_private_base(monkeypatch, cls):
    from shared.url_validation import SSRFError

    import services.shared.external_connectors.food_safety as fs_module

    async def fake_get(url, **kwargs):
        raise SSRFError("Resolved IP 127.0.0.1 is not a public global address")

    monkeypatch.setattr(fs_module, "safe_httpx_get_async", fake_get)

    connector = cls(_config(base_url="http://127.0.0.1:9"))
    assert await connector.test_connection() is False


async def test_foodready_private_base_url_needs_no_network():
    connector = FoodReadyConnector(_config(base_url="http://127.0.0.1:9"))
    assert await connector.test_connection() is False
    events, cursor = await connector.fetch_events(limit=10)
    assert events == [] and cursor is None
