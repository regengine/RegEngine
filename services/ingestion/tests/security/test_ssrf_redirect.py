"""SSRF-on-redirect tests for the safe HTTP helper (RE-SEC-001/002).

A local HTTP server returns 302 -> http://169.254.169.254/latest/meta-data/.
The safe helper must reject the redirect *before* connecting to the metadata
service.
"""

from __future__ import annotations

import http.server
import socket
import threading
from contextlib import contextmanager

import pytest
from shared.safe_http import safe_httpx_get_sync
from shared.url_validation import SSRFError


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    target = "http://169.254.169.254/latest/meta-data/"

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", self.target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args, **kwargs):  # silence
        pass


class _CanaryHandler(http.server.BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):  # noqa: N802
        type(self).hits += 1
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args, **kwargs):  # silence
        pass


@contextmanager
def _running_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address  # (host, port)
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def _running_canary():
    _CanaryHandler.hits = 0
    server = http.server.HTTPServer(("127.0.0.1", 0), _CanaryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()


def test_redirect_to_metadata_ip_blocked(monkeypatch):
    """Redirect target 169.254.169.254 must raise SSRFError."""
    # The local server is at 127.0.0.1 which is in BLOCKED_NETWORKS, so we
    # need to bypass the *initial* validation but keep the *redirect*
    # validation hot. Easiest approach: patch validate_url to allow the
    # initial 127.0.0.1 URL while still rejecting metadata IP via the same
    # blocklist on subsequent calls.
    from shared import url_validation

    with _running_server() as (host, port):
        url = f"http://{host}:{port}/start"

        real_validate = url_validation.validate_url

        def patched(candidate, *args, **kwargs):
            if candidate == url:
                return candidate
            return real_validate(candidate, *args, **kwargs)

        monkeypatch.setattr("shared.safe_http.validate_url", patched)
        with pytest.raises(SSRFError):
            safe_httpx_get_sync(url, validator=patched, max_redirects=3)


def test_redirect_to_internal_canary_is_blocked_before_outbound_request(monkeypatch):
    """The internal target must receive zero requests after a public-hop redirect."""
    from shared import url_validation

    original_target = _RedirectHandler.target
    try:
        with _running_canary() as (canary_host, canary_port):
            _RedirectHandler.target = f"http://{canary_host}:{canary_port}/private-canary"
            with _running_server() as (source_host, source_port):
                source_url = f"http://{source_host}:{source_port}/start"
                real_validate = url_validation.validate_url

                def allow_test_source(candidate, *args, **kwargs):
                    if candidate == source_url:
                        return candidate
                    return real_validate(candidate, *args, **kwargs)

                monkeypatch.setattr("shared.safe_http.validate_url", allow_test_source)
                with pytest.raises(SSRFError):
                    safe_httpx_get_sync(source_url, validator=allow_test_source, max_redirects=3)

            assert _CanaryHandler.hits == 0
    finally:
        _RedirectHandler.target = original_target


def test_validate_url_blocks_metadata_directly():
    from shared.url_validation import validate_url

    with pytest.raises(SSRFError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def _allow_local_hops(monkeypatch, source_url, *, pin_only=()):
    """Let local test URLs connect for real, nothing else.

    ``_validate_and_pin`` refuses 127.0.0.1 before connecting, so without
    this wrapper the tests below would pass via first-hop refusal and never
    exercise redirect-hop validation. ``source_url`` passes both the
    validator and the pin check. ``pin_only`` URLs pass the pin check but
    are still rejected by the real validator, which isolates the validator
    hop re-check as the sole guard for those hops. Returns the recording
    validator, which must be passed explicitly (the helpers capture the
    default validator at def time).
    """
    import shared.safe_http as safe_http_mod
    from shared import url_validation

    real_validate = url_validation.validate_url
    real_pin = safe_http_mod._validate_and_pin
    validated_urls: list[str] = []
    pinnable = {source_url, *pin_only}

    def recording_validator(candidate, *args, **kwargs):
        validated_urls.append(candidate)
        if candidate == source_url:
            return candidate
        return real_validate(candidate, *args, **kwargs)

    def pin_allow_listed(url):
        if url in pinnable:
            return ("127.0.0.1", "127.0.0.1")
        return real_pin(url)

    monkeypatch.setattr(safe_http_mod, "validate_url", recording_validator)
    monkeypatch.setattr(safe_http_mod, "_validate_and_pin", pin_allow_listed)
    return recording_validator, validated_urls


async def test_async_redirect_to_metadata_ip_blocked(monkeypatch):
    """Async twin: a 302 to 169.254.169.254 must raise SSRFError.

    The vendor connectors use ``safe_httpx_get_async``, not the sync
    helper. The async redirect tests elsewhere stub the HTTP client and
    the validator, so this live test (real client constructor, real
    validator on the second hop) is the only proof the async path
    re-validates redirects.
    """
    from shared.safe_http import safe_httpx_get_async

    with _running_server() as (host, port):
        url = f"http://{host}:{port}/start"
        validator, validated_urls = _allow_local_hops(monkeypatch, url)
        with pytest.raises(SSRFError):
            await safe_httpx_get_async(url, validator=validator, max_redirects=3)
        # The link-local target went through validation (via the hop
        # re-check or the pin layer) and was never connected to.
        assert "http://169.254.169.254/latest/meta-data/" in validated_urls


async def test_async_redirect_to_internal_canary_blocked_before_outbound_request(monkeypatch):
    """Async twin: the internal target must receive zero requests.

    Both the source and the canary are pin-allowed, so the validator hop
    re-check is the only guard standing between the client and the
    canary. Deleting that re-check connects to the canary (hits == 1,
    no SSRFError) and fails this test.
    """
    from shared.safe_http import safe_httpx_get_async

    original_target = _RedirectHandler.target
    try:
        with _running_canary() as (canary_host, canary_port):
            canary_url = f"http://{canary_host}:{canary_port}/private-canary"
            _RedirectHandler.target = canary_url
            with _running_server() as (source_host, source_port):
                source_url = f"http://{source_host}:{source_port}/start"
                validator, validated_urls = _allow_local_hops(monkeypatch, source_url, pin_only=[canary_url])
                with pytest.raises(SSRFError):
                    await safe_httpx_get_async(source_url, validator=validator, max_redirects=3)
                assert canary_url in validated_urls

            assert _CanaryHandler.hits == 0
    finally:
        _RedirectHandler.target = original_target


async def test_async_get_tags_logical_final_url(monkeypatch):
    """The finalized response must carry the logical final-hop URL.

    The pinned transport rewrites ``request.url`` to the validated IP
    literal, so feed parsers cannot use ``response.url`` as a base for
    relative links. They read ``extensions["safe_final_url"]`` instead.
    """
    from shared.safe_http import safe_httpx_get_async

    with _running_canary() as (host, port):
        url = f"http://{host}:{port}/feed.xml"
        validator, _ = _allow_local_hops(monkeypatch, url)
        resp = await safe_httpx_get_async(url, validator=validator)
        assert resp.status_code == 204
        assert resp.extensions["safe_final_url"] == url
