"""Tests for ``shared.safe_http.safe_fetch_content``.

This is the canonical SSRF-safe sync HTTP fetcher consumed by ingestion-style
callers after the PR #2197 follow-up consolidation. The tests pin two
properties:

1. SSRF errors raised by the transport are wrapped as
   ``ValueError("URL validation failed: ...")`` and never silently swallowed.
2. Successful responses are returned as a normalized dict with ``content``,
   ``status_code``, ``headers``, ``content_type``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_ssrf_in_transport_is_wrapped_as_value_error(monkeypatch):
    from shared import safe_http
    from shared.url_validation import SSRFError

    def boom(*args, **kwargs):
        raise SSRFError("Resolved IP 169.254.169.254 is in blocked network")

    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", boom)
    # Bypass initial validate_url call — we want to exercise the
    # transport-error branch.
    monkeypatch.setattr(safe_http, "validate_url", lambda u: u)

    with pytest.raises(ValueError, match="URL validation failed"):
        safe_http.safe_fetch_content("https://example.com/foo")


def test_initial_validation_failure_is_wrapped(monkeypatch):
    from shared import safe_http
    from shared.url_validation import SSRFError

    def block(_url):
        raise SSRFError("blocked")

    monkeypatch.setattr(safe_http, "validate_url", block)

    with pytest.raises(ValueError, match="URL validation failed"):
        safe_http.safe_fetch_content("https://internal.local/")


def test_successful_response_is_normalized(monkeypatch):
    from shared import safe_http

    fake_response = MagicMock()
    fake_response.content = b"hello"
    fake_response.status_code = 200
    fake_response.headers = {"Content-Type": "text/plain"}
    fake_response.raise_for_status = MagicMock()

    monkeypatch.setattr(safe_http, "validate_url", lambda u: u)
    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", lambda *a, **kw: fake_response)

    result = safe_http.safe_fetch_content("https://example.com/")
    assert result == {
        "content": b"hello",
        "status_code": 200,
        "headers": {"Content-Type": "text/plain"},
        "content_type": "text/plain",
    }
