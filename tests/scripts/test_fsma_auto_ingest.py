"""Regression tests for the fsma_auto_ingest fail-loud fix.

The scheduler used to simulate every ingestion as a success (the real HTTP
send was commented out) and only warned when no API key was configured while
still contacting the service unauthenticated. These tests pin the fixed
behavior: only a 2xx response counts as success, and an API key is required
outside demo mode.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scheduler" / "fsma_auto_ingest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fsma_auto_ingest", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient."""

    def __init__(self, status_code: int = 200, error: Exception | None = None):
        self.status_code = status_code
        self.error = error
        self.calls: list[dict] = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json})
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.status_code)


def _chain() -> dict:
    return {
        "tlc": "TLC-TEST-1",
        "product": {"name": "Romaine Lettuce"},
        "events": [{"type": "CREATION", "facility": "Green Valley Farms"}],
    }


def _ingester_with(client: _FakeClient):
    ingester = _MODULE.FSMAAutoIngester(api_key="test-key")
    ingester.client = client
    return ingester


async def test_ingest_returns_true_on_success_and_sends_events():
    client = _FakeClient(status_code=200)
    ingester = _ingester_with(client)

    assert await ingester.ingest_supply_chain(_chain()) is True

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"].endswith("/v1/fsma/ingest")
    assert call["json"] == {"events": _chain()["events"]}
    assert call["headers"]["X-RegEngine-API-Key"] == "test-key"


async def test_ingest_returns_false_on_server_error():
    client = _FakeClient(status_code=500)
    ingester = _ingester_with(client)

    assert await ingester.ingest_supply_chain(_chain()) is False


async def test_ingest_returns_false_on_transport_error():
    client = _FakeClient(error=ConnectionError("connection refused"))
    ingester = _ingester_with(client)

    assert await ingester.ingest_supply_chain(_chain()) is False


async def test_ingest_without_client_fails_loudly():
    ingester = _MODULE.FSMAAutoIngester(api_key="test-key")
    ingester.client = None

    with pytest.raises(RuntimeError):
        await ingester.ingest_supply_chain(_chain())


def test_api_key_optional_in_demo_mode():
    _MODULE.validate_api_key("demo", "")


@pytest.mark.parametrize("mode", ["watch", "schedule"])
def test_api_key_required_outside_demo_mode(mode):
    with pytest.raises(SystemExit):
        _MODULE.validate_api_key(mode, "")


def test_api_key_accepted_when_provided():
    _MODULE.validate_api_key("watch", "test-key")
    _MODULE.validate_api_key("schedule", "test-key")


def test_demo_mode_exits_nonzero_when_load_incomplete(monkeypatch):
    class _FailingIngester:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def run_demo_load(self, num_chains=5):
            return 0

    monkeypatch.setattr(_MODULE, "FSMAAutoIngester", _FailingIngester)
    monkeypatch.setattr(sys, "argv", ["fsma_auto_ingest.py", "--mode", "demo", "--chains", "2"])

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(_MODULE.main())
    assert exc_info.value.code != 0


def test_demo_mode_exits_zero_when_load_complete(monkeypatch):
    class _PassingIngester:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def run_demo_load(self, num_chains=5):
            return num_chains

    monkeypatch.setattr(_MODULE, "FSMAAutoIngester", _PassingIngester)
    monkeypatch.setattr(sys, "argv", ["fsma_auto_ingest.py", "--mode", "demo", "--chains", "2"])

    asyncio.run(_MODULE.main())
