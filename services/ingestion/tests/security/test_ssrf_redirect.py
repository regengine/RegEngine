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


def test_redirect_to_metadata_ip_blocked(monkeypatch):
    """Redirect target 169.254.169.254 must raise SSRFError."""
    # The local server is at 127.0.0.1 which is in BLOCKED_NETWORKS, so we
    # need to bypass the *initial* validation but keep the *redirect*
    # validation hot. Easiest approach: patch validate_url to allow the
    # initial 127.0.0.1 URL while still rejecting metadata IP via the same
    # blocklist on subsequent calls.
    from shared import url_validation

    real_validate = url_validation.validate_url
    bypass_first = {"done": False}

    def patched(url, *args, **kwargs):
        if not bypass_first["done"]:
            bypass_first["done"] = True
            return url
        return real_validate(url, *args, **kwargs)

    monkeypatch.setattr("shared.safe_http.validate_url", patched)

    with _running_server() as (host, port):
        url = f"http://{host}:{port}/start"
        with pytest.raises(SSRFError):
            # validator kwarg uses our patched validate_url (via shared.safe_http)
            safe_httpx_get_sync(url, validator=patched, max_redirects=3)


def test_validate_url_blocks_metadata_directly():
    from shared.url_validation import validate_url

    with pytest.raises(SSRFError):
        validate_url("http://169.254.169.254/latest/meta-data/")
