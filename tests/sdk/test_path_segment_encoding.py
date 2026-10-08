"""Lot codes interpolated into URL paths must be percent-encoded (audit low).

``trace_forward``, ``trace_backward`` and ``get_timeline`` put the lot
code in the path, and ``verify_record_online`` does the same. A raw lot
code with spaces, slashes or query characters would split one path
segment into several or change the request target, so each of these
must emit ``quote(tlc, safe="")``. ``_request`` is stubbed, no network
call is made.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from regengine import RegEngineClient, verify_records

NASTY_TLC = "LOT 001/2026?&x=1"
ENCODED = quote(NASTY_TLC, safe="")


def _client(calls: list) -> RegEngineClient:
    client = RegEngineClient(api_key="rge_test")

    def fake_request(method, path, params=None, json=None, **kwargs):
        calls.append((method, path))
        return {}

    client._request = fake_request  # type: ignore[assignment]
    return client


def test_trace_forward_encodes_lot_code():
    calls: list = []
    client = _client(calls)
    try:
        client.trace_forward(NASTY_TLC)
    finally:
        client._session.close()
    assert calls == [("GET", f"/api/v1/fsma/traceability/trace/forward/{ENCODED}")]


def test_trace_backward_encodes_lot_code():
    calls: list = []
    client = _client(calls)
    try:
        client.trace_backward(NASTY_TLC)
    finally:
        client._session.close()
    assert calls == [("GET", f"/api/v1/fsma/traceability/trace/backward/{ENCODED}")]


def test_get_timeline_encodes_lot_code():
    calls: list = []
    client = _client(calls)
    try:
        client.get_timeline(NASTY_TLC)
    finally:
        client._session.close()
    assert calls == [("GET", f"/api/v1/fsma/traceability/timeline/{ENCODED}")]


def test_plain_lot_code_is_unchanged():
    """Ordinary lot codes must keep working exactly as before."""
    calls: list = []
    client = _client(calls)
    try:
        client.get_timeline("LOT-2026-001")
    finally:
        client._session.close()
    assert calls == [("GET", "/api/v1/fsma/traceability/timeline/LOT-2026-001")]


def _record(tlc: str) -> dict:
    record = {
        "event_id": "evt-1",
        "event_type": "shipping",
        "traceability_lot_code": tlc,
        "product_reference": "urn:gtin:0614141000001",
        "quantity": 10,
        "unit_of_measure": "cases",
        "from_facility_reference": "GLN:111",
        "to_facility_reference": "GLN:222",
        "event_timestamp": "2026-02-06T12:00:00Z",
        "kdes": {},
    }
    record["sha256_hash"] = verify_records.compute_record_hash(record)
    return record


@pytest.mark.skipif(not verify_records.HAS_REQUESTS, reason="requests is not installed")
def test_verify_record_online_encodes_lot_code(monkeypatch):
    urls: list = []

    class FakeResponse:
        ok = False

        def raise_for_status(self):
            pass

        def json(self):
            return _record(NASTY_TLC)

    def fake_get(url, **kwargs):
        urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(verify_records.requests, "get", fake_get)
    result = verify_records.verify_record_online(NASTY_TLC, "rge_test", "https://regengine.co/")

    assert result.valid, f"offline check of the fetched record should pass: {result.error}"
    assert urls == [
        f"https://regengine.co/api/graph/fsma/v1/records/{ENCODED}",
        f"https://regengine.co/api/graph/fsma/v1/records/{ENCODED}/verify",
    ]
