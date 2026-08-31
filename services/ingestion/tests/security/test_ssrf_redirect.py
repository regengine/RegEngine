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
