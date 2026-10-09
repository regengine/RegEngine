"""Lot codes interpolated into URL paths must be percent-encoded.

Covers the audit finding on regengine/client.py (trace_forward,
trace_backward, get_timeline) and regengine/verify_records.py
(verify_record_online): a lot code containing a path separator, space,
query or fragment character must arrive as one encoded segment.
"""

from __future__ import annotations

import httpx

from regengine import RegEngineClient


def _client_with_capture(seen: dict, payload: dict):
    client = RegEngineClient(api_key="rge_test", retry_backoff_factor=0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=payload)

    client._session = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_trace_forward_encodes_lot_code_segment():
    seen: dict = {}
    client = _client_with_capture(seen, {"events": [], "tlc": "x"})
    try:
        client.trace_forward("LOT 1/2?x#y")
    finally:
        client._session.close()
    assert "/trace/forward/LOT%201%2F2%3Fx%23y" in seen["url"]
    assert "LOT 1/2" not in seen["url"]


def test_trace_backward_encodes_lot_code_segment():
    seen: dict = {}
    client = _client_with_capture(seen, {"events": [], "tlc": "x"})
    try:
        client.trace_backward("LOT 1/2?x#y")
    finally:
        client._session.close()
    assert "/trace/backward/LOT%201%2F2%3Fx%23y" in seen["url"]


def test_get_timeline_encodes_lot_code_segment():
    seen: dict = {}
    client = _client_with_capture(seen, {"events": []})
    try:
        client.get_timeline("LOT 1/2?x#y")
    finally:
        client._session.close()
    assert "/timeline/LOT%201%2F2%3Fx%23y" in seen["url"]


def test_plain_lot_code_is_unchanged():
    seen: dict = {}
    client = _client_with_capture(seen, {"events": []})
    try:
        client.get_timeline("LOT-2026-001")
    finally:
        client._session.close()
    assert seen["url"].endswith("/timeline/LOT-2026-001")


def test_verify_record_online_encodes_lot_code(monkeypatch):
    from regengine import verify_records

    urls: list[str] = []

    class FakeResponse:
        ok = True

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    def fake_get(url, headers=None, timeout=None):
        urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(verify_records.requests, "get", fake_get)
    result = verify_records.verify_record_online("LOT 1/2?x#y", "rge_test")
    assert isinstance(result.tlc, str)
    assert len(urls) == 2
    assert urls[0].endswith("/records/LOT%201%2F2%3Fx%23y")
    assert urls[1].endswith("/records/LOT%201%2F2%3Fx%23y/verify")
