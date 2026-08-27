"""WS-11: unit coverage for RegEngineClient retry/backoff and error mapping.

The sdk-ci acceptance requires the suite to cover client *behavior*, not
just the verifier. These tests drive the real `_request` code path through
an httpx.MockTransport — no network, no monkeypatched private helpers — so
the retry loop, Retry-After handling, backoff schedule, and status→exception
mapping are exercised as installed customers hit them.
"""

from __future__ import annotations

import httpx
import pytest

from regengine import RegEngineClient
from regengine.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RegEngineError,
)


def make_client(handler, **kwargs) -> RegEngineClient:
    client = RegEngineClient(api_key="rge_test", retry_backoff_factor=0.0, **kwargs)
    client._session = httpx.Client(transport=httpx.MockTransport(handler))
    return client


class TestRetryBehavior:
    def test_retries_transient_500_then_succeeds(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if len(calls) < 3:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"ok": True})

        client = make_client(handler)
        try:
            assert client._request("GET", "/api/v1/thing") == {"ok": True}
            assert len(calls) == 3
        finally:
            client._session.close()

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_retryable_statuses_are_retried(self, status):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(status)
            return httpx.Response(200, json={})

        client = make_client(handler)
        try:
            client._request("GET", "/api/v1/thing")
            assert len(calls) == 2
        finally:
            client._session.close()

    def test_respects_numeric_retry_after_header(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("regengine.client.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "7"})
            return httpx.Response(200, json={})

        client = make_client(handler)
        try:
            client._request("GET", "/api/v1/thing")
            assert sleeps == [7.0]
        finally:
            client._session.close()

    def test_exponential_backoff_schedule(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("regengine.client.time.sleep", lambda s: sleeps.append(s))

        def handler(request):
            return httpx.Response(200, json={}) if len(sleeps) >= 2 else httpx.Response(503)

        client = RegEngineClient(api_key="rge_test", retry_backoff_factor=1.0)
        client._session = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            client._request("GET", "/api/v1/thing")
            # factor * 2**attempt: 1.0, 2.0
            assert sleeps == [1.0, 2.0]
        finally:
            client._session.close()

    def test_exhausted_retries_on_status_raise_rate_limit_error(self):
        # 429 on every attempt: after max_retries the final response is
        # mapped like any non-retryable pass — RateLimitError, not a
        # generic failure, so callers can back off intelligently.
        def handler(request):
            return httpx.Response(429)

        client = make_client(handler, max_retries=1)
        try:
            with pytest.raises(RateLimitError):
                client._request("GET", "/api/v1/thing")
        finally:
            client._session.close()

    def test_network_errors_retry_then_raise_regengine_error(self, monkeypatch):
        monkeypatch.setattr("regengine.client.time.sleep", lambda s: None)
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.ConnectError("refused")

        client = make_client(handler, max_retries=2)
        try:
            with pytest.raises(RegEngineError, match="after 3 attempts"):
                client._request("GET", "/api/v1/thing")
            assert len(calls) == 3
        finally:
            client._session.close()


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status", "exc"),
        [(401, AuthenticationError), (404, NotFoundError)],
    )
    def test_auth_and_not_found(self, status, exc):
        client = make_client(lambda request: httpx.Response(status))
        try:
            with pytest.raises(exc):
                client._request("GET", "/api/v1/thing")
        finally:
            client._session.close()

    def test_other_4xx_maps_to_regengine_error_with_detail(self):
        client = make_client(lambda request: httpx.Response(422, json={"detail": "bad payload"}))
        try:
            with pytest.raises(RegEngineError, match="bad payload"):
                client._request("GET", "/api/v1/thing")
        finally:
            client._session.close()

    def test_204_returns_empty_dict(self):
        client = make_client(lambda request: httpx.Response(204))
        try:
            assert client._request("DELETE", "/api/v1/thing") == {}
        finally:
            client._session.close()

    def test_headers_carry_api_key_and_tenant(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json={})

        client = make_client(handler)
        client.tenant_id = "tenant-42"
        try:
            client._request("GET", "/api/v1/thing")
            assert seen.get("x-regengine-api-key") == "rge_test"
            assert seen.get("x-tenant-id") == "tenant-42"
        finally:
            client._session.close()


class TestExportFdaBytesPath:
    """#2956: `export_fda` used to run through a bare `_request_bytes` — one
    attempt, `raise_for_status()`, and a blanket `except httpx.HTTPError` that
    collapsed 401/404/429 into a generic `RegEngineError` (HTTPStatusError
    subclasses HTTPError). It now shares `_request`'s retry loop and status
    mapping, and validates that a 200 body is actually CSV.
    """

    CSV_HEADERS = {"Content-Type": "text/csv; charset=utf-8"}

    def test_retries_transient_502_then_returns_csv_bytes(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(502)
            return httpx.Response(200, content=b"Traceability Lot Code\nLOT-A\n", headers=self.CSV_HEADERS)

        client = make_client(handler)
        try:
            body = client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
            assert body.startswith(b"Traceability Lot Code")
            assert len(calls) == 2, "the export path must retry like every other call"
        finally:
            client._session.close()

    def test_honours_retry_after_on_export(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("regengine.client.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "5"})
            return httpx.Response(200, content=b"a,b\n", headers=self.CSV_HEADERS)

        client = make_client(handler)
        try:
            client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
            assert sleeps == [5.0]
        finally:
            client._session.close()

    @pytest.mark.parametrize(
        ("status", "exc"),
        [(401, AuthenticationError), (404, NotFoundError)],
    )
    def test_export_maps_status_to_documented_exception(self, status, exc):
        client = make_client(lambda request: httpx.Response(status))
        try:
            with pytest.raises(exc):
                client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
        finally:
            client._session.close()

    def test_export_raises_rate_limit_error_when_retries_exhausted(self):
        client = make_client(lambda request: httpx.Response(429), max_retries=1)
        try:
            with pytest.raises(RateLimitError):
                client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
        finally:
            client._session.close()

    def test_export_requests_csv_accept_header(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, content=b"a,b\n", headers=self.CSV_HEADERS)

        client = make_client(handler)
        try:
            client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
            assert seen.get("accept") == "text/csv"
        finally:
            client._session.close()

    def test_export_refuses_a_non_csv_200_body(self):
        """A 200 that is not CSV must not be handed back as a spreadsheet."""
        client = make_client(lambda request: httpx.Response(200, json={"detail": "not a csv"}))
        try:
            with pytest.raises(RegEngineError, match="Content-Type"):
                client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
        finally:
            client._session.close()

    def test_json_requests_still_get_json_accept_header(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json={})

        client = make_client(handler)
        try:
            client._request("GET", "/api/v1/thing")
            assert seen.get("accept") == "application/json"
        finally:
            client._session.close()
