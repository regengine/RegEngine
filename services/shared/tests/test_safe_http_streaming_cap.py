"""Streaming size-cap regressions for ``shared.safe_http``.

The GET helpers must stream bodies, check ``Content-Length`` before
reading, count decoded bytes while reading (absent or misleading
length included), stop consumption immediately on breach, and close
client+response on errors. Returned responses keep
content/text/json/request/headers semantics.

Chunked fakes raise if consumed beyond the breach point, so the old
``client.get`` buffering fails RED. No DNS/network.
"""

from __future__ import annotations

import gzip
from types import SimpleNamespace

import httpx
import pytest
from shared import safe_http


def _patch_pin(monkeypatch) -> None:
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))


def _raising_gen(consumed: list[int], chunk: bytes = b"x" * 5, allowed: int = 3, total: int = 10):
    def gen():
        for i in range(total):
            if i >= allowed:
                raise AssertionError(f"consumed beyond cap breach point (chunk {i})")
            consumed.append(i)
            yield chunk

    return gen()


class _StreamTransport(httpx.BaseTransport):
    def __init__(self, body_iter, headers: dict) -> None:
        self.body_iter = body_iter
        self.headers = headers

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=self.body_iter, headers=self.headers, request=request)


def test_sync_stops_consumption_on_breach(monkeypatch):
    consumed: list[int] = []
    body = _raising_gen(consumed, chunk=b"x" * 5, allowed=3, total=10)
    transport = _StreamTransport(body, {"Content-Type": "text/plain"})
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync("https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url)
    assert len(consumed) == 3


def test_sync_misleading_content_length_still_streams(monkeypatch):
    consumed: list[int] = []
    body = _raising_gen(consumed, chunk=b"y" * 5, allowed=3, total=10)
    transport = _StreamTransport(body, {"Content-Length": "5"})
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync("https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url)
    assert len(consumed) == 3


def test_sync_declared_length_refused_before_read(monkeypatch):
    consumed: list[int] = []

    def gen():
        consumed.append(0)
        yield b"tiny"

    transport = _StreamTransport(gen(), {"Content-Length": "99999999"})
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync("https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url)
    assert consumed == [], "declared-length refusal must not read the body"


def test_sync_within_cap_preserves_semantics(monkeypatch):
    import json

    payload = {"hello": "world"}
    raw = json.dumps(payload).encode()

    class SmallTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=raw,
                headers={"Content-Type": "application/json"},
                request=request,
            )

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: SmallTransport())
    _patch_pin(monkeypatch)
    resp = safe_http.safe_httpx_get_sync(
        "https://example.com/small", timeout=5, max_bytes=1024, validator=lambda url: url
    )
    assert resp.content == raw
    assert resp.text == raw.decode()
    assert resp.json() == payload
    assert resp.request.method == "GET"
    assert resp.headers["content-type"] == "application/json"
    assert resp.status_code == 200
    resp.raise_for_status()


def test_sync_compressed_decoded_bytes_are_capped(monkeypatch):
    raw_gz = gzip.compress(b"z" * 100)
    assert len(raw_gz) < 50  # raw fits, decoded (100) must breach max_bytes=50

    class GzipTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=raw_gz,
                headers={"Content-Encoding": "gzip", "Content-Length": str(len(raw_gz))},
                request=request,
            )

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: GzipTransport())
    _patch_pin(monkeypatch)
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync("https://example.com/gz", timeout=5, max_bytes=50, validator=lambda url: url)


# --- async ---


def _async_raising_gen(consumed: list[int], chunk: bytes = b"x" * 5, allowed: int = 3, total: int = 10):
    async def gen():
        for i in range(total):
            if i >= allowed:
                raise AssertionError(f"consumed beyond cap breach point (chunk {i})")
            consumed.append(i)
            yield chunk

    return gen()


class _FakeAsyncStreamClient:
    """Dual .get/.stream fake: .get buffers fully (old path hits the raise)."""

    def __init__(self, consumed: list[int], headers: dict | None = None) -> None:
        self.consumed = consumed
        self.headers = headers or {"Content-Type": "text/plain"}

    async def get(self, url: str) -> httpx.Response:
        body = b""
        async for chunk in _async_raising_gen(self.consumed):
            body += chunk
        req = httpx.Request("GET", url)
        return httpx.Response(200, content=body, headers=self.headers, request=req)

    def stream(self, method: str, url: str):
        consumed = self.consumed
        headers = self.headers

        class _Ctx:
            async def __aenter__(self_inner):
                req = httpx.Request(method, url)
                return SimpleNamespace(
                    status_code=200,
                    headers=httpx.Headers(headers),
                    request=req,
                    is_redirect=False,
                    aiter_bytes=lambda: _async_raising_gen(consumed),
                )

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()

    async def aclose(self) -> None:
        pass


async def test_async_stops_consumption_on_breach(monkeypatch):
    consumed: list[int] = []
    monkeypatch.setattr(safe_http, "safe_httpx_client", lambda **kwargs: _FakeAsyncStreamClient(consumed))
    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_httpx_get_async(
            "https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url
        )
    assert len(consumed) == 3


class _FakeAsyncSmallClient:
    async def get(self, url: str) -> httpx.Response:
        req = httpx.Request("GET", url)
        return httpx.Response(200, content=b'{"a":1}', headers={"Content-Type": "application/json"}, request=req)

    def stream(self, method: str, url: str):
        class _Ctx:
            async def __aenter__(self_inner):
                req = httpx.Request(method, url)

                async def gen():
                    yield b'{"a":1}'

                return SimpleNamespace(
                    status_code=200,
                    headers=httpx.Headers({"Content-Type": "application/json"}),
                    request=req,
                    is_redirect=False,
                    aiter_bytes=lambda: gen(),
                )

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()

    async def aclose(self) -> None:
        pass


async def test_async_within_cap_preserves_semantics(monkeypatch):
    monkeypatch.setattr(safe_http, "safe_httpx_client", lambda **kwargs: _FakeAsyncSmallClient())
    resp = await safe_http.safe_httpx_get_async(
        "https://example.com/small", timeout=5, max_bytes=1024, validator=lambda url: url
    )
    assert resp.content == b'{"a":1}'
    assert resp.json() == {"a": 1}
    assert resp.request.method == "GET"
    assert resp.headers["content-type"] == "application/json"
    resp.raise_for_status()


async def test_async_compressed_decoded_bytes_are_capped(monkeypatch):
    raw_gz = gzip.compress(b"q" * 100)

    class _GzClient:
        async def get(self, url: str) -> httpx.Response:
            req = httpx.Request("GET", url)
            return httpx.Response(
                200,
                content=raw_gz,
                headers={"Content-Encoding": "gzip", "Content-Length": str(len(raw_gz))},
                request=req,
            )

        def stream(self, method: str, url: str):
            class _Ctx:
                async def __aenter__(self_inner):
                    req = httpx.Request(method, url)
                    return httpx.Response(
                        200,
                        content=raw_gz,
                        headers={
                            "Content-Encoding": "gzip",
                            "Content-Length": str(len(raw_gz)),
                        },
                        request=req,
                    )

                async def __aexit__(self_inner, *exc):
                    return False

            return _Ctx()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(safe_http, "safe_httpx_client", lambda **kwargs: _GzClient())
    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_httpx_get_async(
            "https://example.com/gz", timeout=5, max_bytes=50, validator=lambda url: url
        )


# --- compressed UNDER-cap happy path (real streaming transports) ---


def test_sync_compressed_under_cap_preserves_semantics(monkeypatch):
    """Small gzip body must decode once and keep content/text/json/request/status/headers."""
    import json

    payload = {"hello": "world", "n": 123}
    raw = json.dumps(payload).encode()
    raw_gz = gzip.compress(raw)
    assert len(raw) < 1024 and len(raw_gz) < 1024

    class GzipSmallTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=httpx.ByteStream(raw_gz),
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(raw_gz)),
                    "X-Keep-Me": "yes",
                },
                request=request,
            )

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: GzipSmallTransport())
    _patch_pin(monkeypatch)
    resp = safe_http.safe_httpx_get_sync(
        "https://example.com/small-gz", timeout=5, max_bytes=1024, validator=lambda url: url
    )
    # Must not raise httpx.DecodingError (double-decode); body is decoded once.
    assert resp.content == raw
    assert resp.text == raw.decode()
    assert resp.json() == payload
    assert resp.request.method == "GET"
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["x-keep-me"] == "yes"
    assert "content-encoding" not in resp.headers
    assert resp.headers["content-length"] == str(len(raw))
    resp.raise_for_status()


async def test_async_compressed_under_cap_preserves_semantics(monkeypatch):
    """Async gzip happy path via real AsyncClient+MockTransport streaming (no fakes)."""
    import json

    payload = {"hello": "world", "n": 123}
    raw = json.dumps(payload).encode()
    raw_gz = gzip.compress(raw)
    assert len(raw) < 1024 and len(raw_gz) < 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(raw_gz),
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "Content-Length": str(len(raw_gz)),
                "X-Keep-Me": "yes",
            },
            request=request,
        )

    created: dict = {}

    def _client_factory(**kwargs):
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=False, headers=kwargs.get("headers") or {})
        created["client"] = client
        return client

    monkeypatch.setattr(safe_http, "safe_httpx_client", _client_factory)
    resp = await safe_http.safe_httpx_get_async(
        "https://example.com/small-gz", timeout=5, max_bytes=1024, validator=lambda url: url
    )
    assert resp.content == raw
    assert resp.text == raw.decode()
    assert resp.json() == payload
    assert resp.request.method == "GET"
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["x-keep-me"] == "yes"
    assert "content-encoding" not in resp.headers
    assert resp.headers["content-length"] == str(len(raw))
    resp.raise_for_status()
    assert created["client"].is_closed


# --- close verification on early reject and read exceptions ---


def test_sync_declared_length_closes_response_and_transport(monkeypatch):
    consumed: list[int] = []

    def gen():
        consumed.append(0)
        yield b"tiny"

    captured: dict = {}

    class TrackingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.transport_closed = False

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            resp = httpx.Response(200, content=gen(), headers={"Content-Length": "99999999"}, request=request)
            captured["response"] = resp
            return resp

        def close(self) -> None:
            self.transport_closed = True
            super().close()

    transport = TrackingTransport()
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    with pytest.raises(safe_http.ResponseTooLargeError):
        safe_http.safe_httpx_get_sync("https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url)
    assert consumed == [], "declared-length refusal must not read the body"
    assert captured["response"].is_closed, "streaming response must be closed on early reject"
    assert transport.transport_closed, "client/transport must be closed on early reject"


def test_sync_read_exception_closes_response_and_transport(monkeypatch):
    def boom_gen():
        yield b"a" * 5
        raise RuntimeError("boom")

    captured: dict = {}

    class TrackingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.transport_closed = False

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            resp = httpx.Response(200, content=boom_gen(), headers={"Content-Type": "text/plain"}, request=request)
            captured["response"] = resp
            return resp

        def close(self) -> None:
            self.transport_closed = True
            super().close()

    transport = TrackingTransport()
    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: transport)
    _patch_pin(monkeypatch)
    with pytest.raises(RuntimeError, match="boom"):
        safe_http.safe_httpx_get_sync("https://example.com/boom", timeout=5, max_bytes=1024, validator=lambda url: url)
    assert captured["response"].is_closed, "response must be closed on read exception"
    assert transport.transport_closed, "client/transport must be closed on read exception"


async def test_async_declared_length_closes_response_and_client(monkeypatch):
    captured: dict = {}

    class TrackingAsyncTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.transport_closed = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            async def _gen():
                yield b"tiny"

            resp = httpx.Response(200, content=_gen(), headers={"Content-Length": "99999999"}, request=request)
            captured["response"] = resp
            return resp

        async def aclose(self) -> None:
            self.transport_closed = True

    transport = TrackingAsyncTransport()
    created: dict = {}

    def _client_factory(**kwargs):
        client = httpx.AsyncClient(transport=transport, follow_redirects=False, headers=kwargs.get("headers") or {})
        created["client"] = client
        return client

    monkeypatch.setattr(safe_http, "safe_httpx_client", _client_factory)
    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_httpx_get_async(
            "https://example.com/big", timeout=5, max_bytes=10, validator=lambda url: url
        )
    assert captured["response"].is_closed, "streaming response must be closed on early reject"
    assert transport.transport_closed, "transport must be closed on early reject"
    assert created["client"].is_closed, "async client must be closed on early reject"


async def test_async_read_exception_closes_response_and_client(monkeypatch):
    captured: dict = {}

    class BoomAsyncTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.transport_closed = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            async def _boom():
                yield b"a" * 5
                raise RuntimeError("boom")

            resp = httpx.Response(200, content=_boom(), headers={"Content-Type": "text/plain"}, request=request)
            captured["response"] = resp
            return resp

        async def aclose(self) -> None:
            self.transport_closed = True

    transport = BoomAsyncTransport()
    created: dict = {}

    def _client_factory(**kwargs):
        client = httpx.AsyncClient(transport=transport, follow_redirects=False, headers=kwargs.get("headers") or {})
        created["client"] = client
        return client

    monkeypatch.setattr(safe_http, "safe_httpx_client", _client_factory)
    with pytest.raises(RuntimeError, match="boom"):
        await safe_http.safe_httpx_get_async(
            "https://example.com/boom", timeout=5, max_bytes=1024, validator=lambda url: url
        )
    assert captured["response"].is_closed, "response must be closed on read exception"
    assert transport.transport_closed, "transport must be closed on read exception"
    assert created["client"].is_closed, "async client must be closed on read exception"
