"""Online verifier hardening: host validation, TLC encoding, bad-JSON handling.

Regression coverage for the audit finding on
``regengine.verify_records.verify_record_online``: the TLC went raw into the
request path, the base URL was never validated, and a non-JSON (or non-object)
response body raised out of the verifier instead of coming back as a failed
``VerificationResult``.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from regengine import verify_records
from regengine.verify_records import compute_record_hash, verify_record_online


def _record(tlc: str) -> dict:
    """Build a canonical-shaped record carrying its own correct digest."""
    record = {
        "event_id": f"evt-{tlc}",
        "event_type": "shipping",
        "traceability_lot_code": tlc,
        "product_reference": "urn:gtin:0614141000001",
        "quantity": 10,
        "unit_of_measure": "cases",
        "from_facility_reference": "GLN:111",
        "to_facility_reference": "GLN:222",
        "event_timestamp": "2026-02-06T12:00:00Z",
        "kdes": {"lot_date": "2026-02-05"},
    }
    record["sha256_hash"] = compute_record_hash(record)
    return record


class _FakeResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, payload=None, *, ok=True, json_error=None):
        self._payload = payload
        self._ok = ok
        self._json_error = json_error

    def raise_for_status(self):
        return None

    @property
    def ok(self):
        return self._ok

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def _patch_get(monkeypatch, responses):
    """Replace ``requests.get`` with a stub serving ``responses`` in order."""
    calls = []
    pending = list(responses)

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return pending.pop(0)

    monkeypatch.setattr(verify_records.requests, "get", fake_get)
    return calls


def test_tlc_is_url_encoded_in_request_path(monkeypatch):
    tlc = "LOT 2026/001?&x=1"
    calls = _patch_get(
        monkeypatch,
        [_FakeResponse(_record(tlc)), _FakeResponse(None, ok=False)],
    )

    result = verify_record_online(tlc, "rge_test_key")

    assert result.valid, f"expected local verification to pass, got error: {result.error}"
    assert len(calls) == 2
    encoded = quote(tlc, safe="")
    for url in calls:
        # The raw TLC (with a space, a slash and query characters) must
        # never appear verbatim in the request URL.
        assert encoded in url
        assert tlc not in url


def test_bad_json_record_response_returns_error_result(monkeypatch):
    _patch_get(monkeypatch, [_FakeResponse(json_error=ValueError("No JSON object could be decoded"))])

    result = verify_record_online("LOT-A", "rge_test_key")

    assert result.valid is False
    assert result.error is not None and "JSON" in result.error


def test_non_object_record_payload_returns_error_result(monkeypatch):
    _patch_get(monkeypatch, [_FakeResponse(["not", "a", "record"])])

    result = verify_record_online("LOT-A", "rge_test_key")

    assert result.valid is False
    assert result.error is not None


@pytest.mark.parametrize("base_url", ["ftp://example.com/api", "not-a-url", "https://"])
def test_invalid_base_url_is_rejected_without_request(monkeypatch, base_url):
    def fail_if_called(url, headers=None, timeout=None):  # pragma: no cover
        raise AssertionError(f"no request should be made with base_url={base_url!r}")

    monkeypatch.setattr(verify_records.requests, "get", fail_if_called)

    result = verify_record_online("LOT-A", "rge_test_key", base_url=base_url)

    assert result.valid is False
    assert result.error is not None and "base URL" in result.error


def test_bad_json_verify_endpoint_keeps_local_result(monkeypatch):
    tlc = "LOT-A"
    _patch_get(
        monkeypatch,
        [
            _FakeResponse(_record(tlc)),
            _FakeResponse(ok=True, json_error=ValueError("No JSON object could be decoded")),
        ],
    )

    result = verify_record_online(tlc, "rge_test_key")

    assert result.valid is True
    assert result.chain_position is None


def test_non_object_verify_payload_keeps_local_result(monkeypatch):
    tlc = "LOT-A"
    _patch_get(
        monkeypatch,
        [_FakeResponse(_record(tlc)), _FakeResponse(["not", "a", "dict"], ok=True)],
    )

    result = verify_record_online(tlc, "rge_test_key")

    assert result.valid is True
    assert result.chain_position is None
