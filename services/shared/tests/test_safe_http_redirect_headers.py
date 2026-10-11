"""Redirect header-leak regressions for ``shared.safe_http``.

The sync and async GET helpers must not carry caller headers (notably
``Authorization``, ``X-Api-Key``, ``Cookie``) across a cross-origin
redirect, and must reject HTTPS->HTTP downgrades. Same-origin redirects
with headers must keep working.

All tests use fake transports/clients and ``validator=lambda url: url``:
no DNS and no network.
"""

from __future__ import annotations

import httpx
import pytest
from shared import safe_http
from shared.url_validation import SSRFError


def _patch_pin(monkeypatch) -> None:
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))


class _RecordingTransport(httpx.BaseTransport):
    """Sync fake that serves a redirect then a final body."""

    def __init__(self, first_url: str, location: str) -> None:
        self.first_url = first_url
        self.location = location
        self.requested: list[str] = []
        self.seen_auth: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        self.seen_auth.append(request.headers.get("authorization"))
        if url == self.first_url:
            return httpx.Response(
                302,
                headers={"location": self.location},
                content=b"",
                request=request,
            )
        return httpx.Response(200, content=b"second-origin-body", request=request)


def _run_sync(first: str, location: str, headers, monkeypatch):
    transport = _RecordingTransport(first, location)
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    return transport


def test_sync_cross_origin_with_authorization_is_rejected(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://b.example/second", {"Authorization": "Bearer secret"}, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(
            first,
            headers={"Authorization": "Bearer secret"},
            timeout=5,
            validator=lambda url: url,
        )
    assert transport.requested == [first], "second origin must never be requested"


def test_sync_cross_origin_with_api_key_is_rejected(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://b.example/second", {"X-Api-Key": "k"}, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(first, headers={"X-Api-Key": "k"}, timeout=5, validator=lambda url: url)
    assert transport.requested == [first]


def test_sync_cross_origin_with_cookie_is_rejected(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://b.example/second", {"Cookie": "s=1"}, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(first, headers={"Cookie": "s=1"}, timeout=5, validator=lambda url: url)
    assert transport.requested == [first]


def test_sync_downgrade_is_rejected_even_without_headers(monkeypatch):
    first = "https://a.example/secure"
    transport = _run_sync(first, "http://a.example/insecure", None, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(first, timeout=5, validator=lambda url: url)
    assert transport.requested == [first]


def test_sync_same_origin_with_auth_is_preserved(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://a.example/second", {"Authorization": "Bearer s"}, monkeypatch)
    resp = safe_http.safe_httpx_get_sync(
        first,
        headers={"Authorization": "Bearer s"},
        timeout=5,
        validator=lambda url: url,
    )
    assert resp.content == b"second-origin-body"
    assert transport.requested == [first, "https://a.example/second"]


def test_sync_same_origin_case_and_default_port(monkeypatch):
    first = "https://example.com/first"
    transport = _run_sync(first, "https://EXAMPLE.com:443/second", {"Authorization": "Bearer s"}, monkeypatch)
    resp = safe_http.safe_httpx_get_sync(
        first,
        headers={"Authorization": "Bearer s"},
        timeout=5,
        validator=lambda url: url,
    )
    assert resp.content == b"second-origin-body"
    assert transport.requested == [first, "https://example.com/second"]


def test_sync_cross_port_with_auth_is_rejected(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://a.example:8443/second", {"Authorization": "B"}, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(first, headers={"Authorization": "B"}, timeout=5, validator=lambda url: url)
    assert transport.requested == [first]


# --- async (dual .get/.stream fake so RED on original is the leak, not AttributeError) ---


class _FakeAsyncRedirectClient:
    def __init__(self, first_url: str, location: str, record: list[str]) -> None:
        self.first_url = first_url
        self.location = location
        self.record = record

    def _response_for(self, url: str) -> httpx.Response:
        req = httpx.Request("GET", url)
        if url == self.first_url:
            return httpx.Response(302, headers={"location": self.location}, content=b"", request=req)
        return httpx.Response(200, content=b"second-origin-body", request=req)

    async def get(self, url: str) -> httpx.Response:
        self.record.append(str(url))
        return self._response_for(str(url))

    def stream(self, method: str, url: str):
        record = self.record
        first = self.first_url
        location = self.location

        class _Ctx:
            async def __aenter__(self_inner):
                record.append(str(url))
                req = httpx.Request(method, url)
                if str(url) == first:
                    return httpx.Response(302, headers={"location": location}, content=b"", request=req)
                return httpx.Response(200, content=b"second-origin-body", request=req)

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()

    async def aclose(self) -> None:
        pass


def _patch_async(monkeypatch, first: str, location: str, record: list[str]) -> None:
    monkeypatch.setattr(
        safe_http, "safe_httpx_client", lambda **kwargs: _FakeAsyncRedirectClient(first, location, record)
    )


async def test_async_cross_origin_with_authorization_is_rejected(monkeypatch):
    first = "https://a.example/first"
    record: list[str] = []
    _patch_async(monkeypatch, first, "https://b.example/second", record)
    with pytest.raises(SSRFError):
        await safe_http.safe_httpx_get_async(
            first,
            headers={"Authorization": "Bearer secret"},
            timeout=5,
            validator=lambda url: url,
        )
    assert record == [first], "second origin must never be requested"


async def test_async_downgrade_is_rejected(monkeypatch):
    first = "https://a.example/secure"
    record: list[str] = []
    _patch_async(monkeypatch, first, "http://a.example/insecure", record)
    with pytest.raises(SSRFError):
        await safe_http.safe_httpx_get_async(
            first, headers={"Authorization": "Bearer s"}, timeout=5, validator=lambda url: url
        )
    assert record == [first]


async def test_async_same_origin_with_auth_is_preserved(monkeypatch):
    first = "https://a.example/first"
    record: list[str] = []
    _patch_async(monkeypatch, first, "https://a.example/second", record)
    resp = await safe_http.safe_httpx_get_async(
        first,
        headers={"Authorization": "Bearer s"},
        timeout=5,
        validator=lambda url: url,
    )
    assert resp.content == b"second-origin-body"
    assert record == [first, "https://a.example/second"]


# --- benign browser-header public redirects (must stay allowed) ---


def test_sync_cross_origin_with_browser_headers_is_allowed(monkeypatch):
    from shared.safe_http import STANDARD_BROWSER_HEADERS

    first = "https://a.example/first"
    second = "https://b.example/second"
    transport = _RecordingTransport(first, second)
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    pin_calls: list[str] = []

    def _recording_pin(url: str):
        pin_calls.append(url)
        return ("93.184.216.34", "example.com")

    monkeypatch.setattr(safe_http, "_validate_and_pin", _recording_pin)
    validator_calls: list[str] = []

    def _recording_validator(url: str) -> str:
        validator_calls.append(url)
        return url

    resp = safe_http.safe_httpx_get_sync(
        first, headers=dict(STANDARD_BROWSER_HEADERS), timeout=5, validator=_recording_validator
    )
    assert resp.content == b"second-origin-body"
    assert transport.requested == [first, second]
    assert validator_calls[0] == first and second in validator_calls
    assert first in pin_calls and second in pin_calls


def test_sync_cross_origin_with_mixed_case_auth_is_rejected(monkeypatch):
    first = "https://a.example/first"
    transport = _run_sync(first, "https://b.example/second", {"x": "y"}, monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(first, headers={"aUtHoRiZaTiOn": "t"}, timeout=5, validator=lambda url: url)
    assert transport.requested == [first]


def test_sync_downgrade_with_benign_headers_is_rejected(monkeypatch):
    from shared.safe_http import STANDARD_BROWSER_HEADERS

    first = "https://a.example/secure"
    transport = _run_sync(first, "http://a.example/insecure", dict(STANDARD_BROWSER_HEADERS), monkeypatch)
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync(
            first, headers=dict(STANDARD_BROWSER_HEADERS), timeout=5, validator=lambda url: url
        )
    assert transport.requested == [first]


async def test_async_cross_origin_with_browser_headers_is_allowed(monkeypatch):
    from shared.safe_http import STANDARD_BROWSER_HEADERS

    first = "https://a.example/first"
    second = "https://b.example/second"
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url == first:
            return httpx.Response(302, headers={"location": second}, content=b"", request=request)
        return httpx.Response(200, content=b"second-origin-body", request=request)

    created: dict = {"clients": []}

    def _client_factory(**kwargs):
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False, headers=kwargs.get("headers") or {})
        created["clients"].append(client)
        return client

    monkeypatch.setattr(safe_http, "safe_httpx_client", _client_factory)
    validator_calls: list[str] = []

    def _recording_validator(url: str) -> str:
        validator_calls.append(url)
        return url

    resp = await safe_http.safe_httpx_get_async(
        first, headers=dict(STANDARD_BROWSER_HEADERS), timeout=5, validator=_recording_validator
    )
    assert resp.content == b"second-origin-body"
    assert requested == [first, second]
    assert validator_calls[0] == first and second in validator_calls
    for client in created["clients"]:
        assert client.is_closed


async def test_async_cross_origin_with_mixed_case_auth_is_rejected(monkeypatch):
    first = "https://a.example/first"
    second = "https://b.example/second"
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url == first:
            return httpx.Response(302, headers={"location": second}, content=b"", request=request)
        return httpx.Response(200, content=b"second-origin-body", request=request)

    created: dict = {"clients": []}

    def _client_factory(**kwargs):
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False, headers=kwargs.get("headers") or {})
        created["clients"].append(client)
        return client

    monkeypatch.setattr(safe_http, "safe_httpx_client", _client_factory)
    with pytest.raises(SSRFError):
        await safe_http.safe_httpx_get_async(
            first,
            headers={"AuTHoRiZaTiOn": "t"},
            timeout=5,
            validator=lambda url: url,
        )
    assert requested == [first]
    for client in created["clients"]:
        assert client.is_closed
