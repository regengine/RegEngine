from __future__ import annotations

import httpx
import pytest
from shared.safe_http import _IPPinnedAsyncTransport, _IPPinnedSyncTransport


def test_sync_pinned_transport_preserves_tls_sni(monkeypatch):
    observed = {}

    def fake_handle(_transport, request):
        observed["url"] = str(request.url)
        observed["host"] = request.headers["Host"]
        observed["sni"] = request.extensions["sni_hostname"]
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    transport = _IPPinnedSyncTransport(pinned_ip="8.8.8.8", original_host="example.com")
    try:
        response = transport.handle_request(httpx.Request("GET", "https://example.com/document"))
    finally:
        transport.close()

    assert response.status_code == 200
    assert observed == {
        "url": "https://8.8.8.8/document",
        "host": "example.com",
        "sni": "example.com",
    }


def test_sync_pinned_transport_rejects_different_host(monkeypatch):
    sent = []

    def fake_handle(_transport, request):
        sent.append(str(request.url))
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    transport = _IPPinnedSyncTransport(pinned_ip="8.8.8.8", original_host="example.com")
    try:
        with pytest.raises(ValueError, match="pinned to"):
            transport.handle_request(httpx.Request("GET", "https://other.example/document"))
    finally:
        transport.close()

    assert sent == []


def test_sync_pinned_transport_accepts_case_and_trailing_dot(monkeypatch):
    observed = {}

    def fake_handle(_transport, request):
        observed["url"] = str(request.url)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)
    transport = _IPPinnedSyncTransport(pinned_ip="8.8.8.8", original_host="example.com")
    try:
        response = transport.handle_request(httpx.Request("GET", "https://EXAMPLE.com./document"))
    finally:
        transport.close()

    assert response.status_code == 200
    assert observed == {"url": "https://8.8.8.8/document"}


@pytest.mark.asyncio
async def test_async_pinned_transport_rejects_different_host(monkeypatch):
    sent = []

    async def fake_handle(_transport, request):
        sent.append(str(request.url))
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)
    transport = _IPPinnedAsyncTransport(pinned_ip="8.8.4.4", original_host="example.com")
    try:
        with pytest.raises(ValueError, match="pinned to"):
            await transport.handle_async_request(httpx.Request("GET", "https://other.example/document"))
    finally:
        await transport.aclose()

    assert sent == []


@pytest.mark.asyncio
async def test_async_pinned_transport_preserves_tls_sni(monkeypatch):
    observed = {}

    async def fake_handle(_transport, request):
        observed["url"] = str(request.url)
        observed["host"] = request.headers["Host"]
        observed["sni"] = request.extensions["sni_hostname"]
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)
    transport = _IPPinnedAsyncTransport(pinned_ip="8.8.4.4", original_host="example.com")
    try:
        response = await transport.handle_async_request(httpx.Request("GET", "https://example.com/document"))
    finally:
        await transport.aclose()

    assert response.status_code == 200
    assert observed == {
        "url": "https://8.8.4.4/document",
        "host": "example.com",
        "sni": "example.com",
    }
