"""Browser fallback must NOT trigger on SSRF errors (RE-SEC-004).

After the fold of ``fetch_utils`` into ``shared.safe_http``, the ingestion
shim still owns the Playwright fallback decision. These tests pin the
contract: SSRF (raw or wrapped) is fatal, never promoted to the browser.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_ssrf_does_not_trigger_browser_fallback(monkeypatch):
    from regengine_ingestion.utils import fetch_utils
    from shared import safe_http
    from shared.url_validation import SSRFError

    # Make the underlying transport raise SSRF. Patch on ``shared.safe_http``
    # because ``fetch_utils.fetch_content`` now delegates to
    # ``safe_http.safe_fetch_content``.
    def boom(*args, **kwargs):
        raise SSRFError("Resolved IP 169.254.169.254 is in blocked network")

    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", boom)

    browser_mock = MagicMock(side_effect=AssertionError("browser must not run"))
    monkeypatch.setattr(fetch_utils, "_fetch_with_browser_sync", browser_mock)

    with pytest.raises(ValueError, match="URL validation failed"):
        # Pass a public-looking URL so the *initial* validate_url succeeds.
        fetch_utils.fetch_content("https://example.com/foo")

    browser_mock.assert_not_called()


def test_wrapped_ssrf_value_error_does_not_trigger_fallback(monkeypatch):
    """The validator wraps SSRFError as ValueError('URL validation failed: ...').
    That wrapper must also be fatal."""
    from regengine_ingestion.utils import fetch_utils
    from shared import safe_http

    def wrapped(*args, **kwargs):
        raise ValueError("URL validation failed: blocked")

    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", wrapped)

    browser_mock = MagicMock(side_effect=AssertionError("browser must not run"))
    monkeypatch.setattr(fetch_utils, "_fetch_with_browser_sync", browser_mock)

    with pytest.raises(ValueError, match="URL validation failed"):
        fetch_utils.fetch_content("https://example.com/foo")

    browser_mock.assert_not_called()


def test_non_ssrf_failure_does_trigger_browser_fallback(monkeypatch):
    """Sanity check the other branch: a transient HTTP error promotes to the
    browser fetcher when ``use_browser_fallback`` is true."""
    from regengine_ingestion.utils import fetch_utils
    from shared import safe_http

    def http_500(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(safe_http, "safe_httpx_get_sync", http_500)

    browser_mock = MagicMock(
        return_value={
            "content": b"ok",
            "status_code": 200,
            "headers": {},
            "content_type": "text/html",
        }
    )
    monkeypatch.setattr(fetch_utils, "_fetch_with_browser_sync", browser_mock)

    result = fetch_utils.fetch_content("https://example.com/foo")
    assert result["content"] == b"ok"
    browser_mock.assert_called_once()
