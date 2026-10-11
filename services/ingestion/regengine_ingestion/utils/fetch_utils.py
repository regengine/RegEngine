"""Ingestion-local fetcher: SSRF-safe HTTP with optional Playwright fallback.

The pure-HTTP path lives in :mod:`shared.safe_http` (one fetcher, not two).
This module is the thin ingestion-only shim that adds a headless-browser
fallback for sites that legitimately require JS execution. Playwright is
imported lazily so non-ingestion callers of ``shared.safe_http`` never pay
that import cost.

SSRF guarantees (preserved from PR #2197):

* Initial URL is validated through ``validate_url``.
* Every redirect hop is re-validated by :func:`safe_httpx_get_sync`, with the
  destination IP pinned per hop (RE-SEC-001, RE-SEC-002).
* SSRF errors are NEVER promoted to the headless-browser fallback
  (RE-SEC-004); only transient/HTTP errors qualify.
"""

from typing import Any, Dict

import httpx
import structlog
from shared.safe_http import (
    STANDARD_BROWSER_HEADERS,
    ResponseTooLargeError,
    safe_fetch_content,
    safe_httpx_get_sync,
)
from shared.url_validation import SSRFError, validate_url

logger = structlog.get_logger("ingestion.fetch")

# Re-exported for backward compat with callers that imported these names from
# this module.
STANDARD_HEADERS = STANDARD_BROWSER_HEADERS

__all__ = [
    "STANDARD_HEADERS",
    "fetch_content",
    "safe_httpx_get_sync",
]


def fetch_content(url: str, timeout: int = 30, use_browser_fallback: bool = True) -> Dict[str, Any]:
    """Fetch a URL with SSRF protection and optional Playwright fallback.

    Thin wrapper over :func:`shared.safe_http.safe_fetch_content`. On
    non-SSRF failure (network error, HTTP error, etc.) and when
    ``use_browser_fallback`` is true, retries via the headless browser.
    SSRF errors, size-cap refusals, and decode failures are fatal and never
    reach the browser path (the browser follows redirects itself with no
    byte cap, so promoting those failures would sidestep both guards).
    """
    try:
        return safe_fetch_content(url, timeout=timeout, headers=STANDARD_HEADERS)
    except ResponseTooLargeError:
        # A browser retry must not bypass the response size boundary.
        raise
    except httpx.DecodingError:
        # A decode failure means the body bytes are hostile or malformed
        # (for example a compressed bomb). The browser path has no byte cap
        # and follows redirects itself, so re-fetching there must not happen.
        raise
    except ValueError as e:
        # ``safe_fetch_content`` wraps SSRF as ValueError("URL validation
        # failed: ..."). That wrapper is fatal; do not fall back.
        if str(e).startswith("URL validation failed"):
            logger.warning("ssrf_error_no_fallback", url=url, error=str(e))
            raise
        # Other ValueError: not SSRF; treat as a transient fetch failure.
        if use_browser_fallback:
            logger.warning("fetch_failed_falling_back_to_browser", url=url, error=str(e))
            return _fetch_with_browser_sync(url)
        raise
    except SSRFError as e:
        # Defensive: should already have been wrapped, but never let SSRF
        # promote to a browser fetch.
        logger.warning("ssrf_error_no_fallback", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e
    except Exception as e:
        if use_browser_fallback:
            logger.warning("fetch_failed_falling_back_to_browser", url=url, error=str(e))
            try:
                return _fetch_with_browser_sync(url)
            except Exception as browser_e:
                logger.error("all_fetch_methods_failed", url=url, error=str(browser_e))
                raise browser_e
        raise


def _fetch_with_browser_sync(url: str) -> Dict[str, Any]:
    """Run the Playwright-based fetch synchronously.

    SSRFError must not reach this function — callers strip it out — but we
    re-validate defensively. NOTE: ``run_browser_fetch`` does not currently
    re-validate redirect hops; cross-hop SSRF protection inside the headless
    browser is a TODO tracked separately.
    """
    try:
        url = validate_url(url)
    except SSRFError as e:
        logger.warning("ssrf_validation_failed_browser_fetch", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    try:
        from app.browser_utils import run_browser_fetch

        return run_browser_fetch(url)
    except ImportError:
        logger.error("browser_utils_not_found_cannot_fallback")
        raise RuntimeError("Browser fallback requested but browser_utils not available")
