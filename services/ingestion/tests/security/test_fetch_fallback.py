"""Browser fallback must NOT trigger on SSRF errors (RE-SEC-004)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_ssrf_does_not_trigger_browser_fallback(monkeypatch):
    from regengine_ingestion.utils import fetch_utils
    from shared.url_validation import SSRFError

    # Make safe helper raise SSRF
    def boom(*args, **kwargs):
        raise SSRFError("Resolved IP 169.254.169.254 is in blocked network")

    monkeypatch.setattr(fetch_utils, "safe_httpx_get_sync", boom)

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

    def wrapped(*args, **kwargs):
        raise ValueError("URL validation failed: blocked")

    monkeypatch.setattr(fetch_utils, "safe_httpx_get_sync", wrapped)

    browser_mock = MagicMock(side_effect=AssertionError("browser must not run"))
    monkeypatch.setattr(fetch_utils, "_fetch_with_browser_sync", browser_mock)

    with pytest.raises(ValueError, match="URL validation failed"):
        fetch_utils.fetch_content("https://example.com/foo")

    browser_mock.assert_not_called()
