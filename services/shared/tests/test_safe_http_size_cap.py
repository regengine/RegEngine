"""Size-cap and SSRF refusal tests for ``shared.safe_http``.

The safe helpers must refuse private or link-local targets before
connecting (SSRF) and refuse response bodies larger than ``max_bytes``
(size cap). Each test below fails on the pre-fix code, which had no
``max_bytes`` parameter and no async safe GET.
"""

from __future__ import annotations

import httpx
import pytest
from shared import safe_http
from shared.url_validation import SSRFError


def _oversized_response(size: int = 100) -> httpx.Response:
    return httpx.Response(
        200,
        content=b"x" * size,
        headers={"Content-Type": "text/plain", "Content-Length": str(size)},
    )


def test_sync_get_refuses_private_address_without_connecting():
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync("http://127.0.0.1/secret", timeout=5)


def test_sync_get_refuses_link_local_address():
    with pytest.raises(SSRFError):
        safe_http.safe_httpx_get_sync("http://169.254.169.254/latest/meta-data", timeout=5)


async def test_async_get_refuses_private_address_without_connecting():
    with pytest.raises(SSRFError):
        await safe_http.safe_httpx_get_async("http://127.0.0.1/secret", timeout=5)


def test_sync_get_refuses_oversized_body(monkeypatch):
    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return _oversized_response(100)

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: FakeTransport())
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))

    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync(
            "https://example.com/big",
            timeout=5,
            max_bytes=10,
            validator=lambda url: url,
        )


def test_sync_get_refuses_oversized_declared_length(monkeypatch):
    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"tiny", headers={"Content-Length": "99999999"})

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: FakeTransport())
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))

    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync(
            "https://example.com/big",
            timeout=5,
            max_bytes=10,
            validator=lambda url: url,
        )


def test_sync_get_allows_body_within_cap(monkeypatch):
    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"small", headers={"Content-Type": "text/plain"})

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: FakeTransport())
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))

    resp = safe_http.safe_httpx_get_sync(
        "https://example.com/small",
        timeout=5,
        max_bytes=10,
        validator=lambda url: url,
    )
    assert resp.content == b"small"


async def test_async_get_refuses_oversized_body(monkeypatch):
    class FakeAsyncClient:
        async def get(self, url: str) -> httpx.Response:
            return _oversized_response(100)

        def stream(self, method: str, url: str):
            class _Ctx:
                async def __aenter__(self_inner) -> httpx.Response:
                    req = httpx.Request(method, url)
                    return httpx.Response(
                        200,
                        content=b"x" * 100,
                        headers={"Content-Type": "text/plain", "Content-Length": "100"},
                        request=req,
                    )

                async def __aexit__(self_inner, *exc) -> bool:
                    return False

            return _Ctx()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(safe_http, "safe_httpx_client", lambda **kwargs: FakeAsyncClient())

    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_httpx_get_async(
            "https://example.com/big",
            timeout=5,
            max_bytes=10,
            validator=lambda url: url,
        )


def test_safe_fetch_content_refuses_oversized_body(monkeypatch):
    monkeypatch.setattr(safe_http, "validate_url", lambda url: url)

    def boom(*args, **kwargs):
        raise safe_http.ResponseTooLargeError("Response body exceeds 10 bytes")

    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", boom)

    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_fetch_content("https://example.com/big", max_bytes=10)
