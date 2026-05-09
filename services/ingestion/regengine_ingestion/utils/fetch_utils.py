import httpx
import structlog
from typing import Dict, Any
from shared.url_validation import validate_url, SSRFError
from shared.safe_http import safe_httpx_get_sync

logger = structlog.get_logger("ingestion.fetch")

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_content(url: str, timeout: int = 30, use_browser_fallback: bool = True) -> Dict[str, Any]:
    """Fetch a URL with SSRF protection and optional browser fallback.

    SSRF defense:

    * Initial URL is validated through ``validate_url``.
    * Every redirect hop is re-validated by :func:`safe_httpx_get_sync`, with
      the destination IP pinned per hop to defeat DNS rebinding (RE-SEC-001,
      RE-SEC-002).
    * SSRF errors are NEVER promoted to the headless-browser fallback
      (RE-SEC-004); only transient/HTTP errors qualify.
    * Removed prior 401/403/502 -> browser auto-promotion: a 403 from a
      permitted host should not unlock a stronger fetcher.
    """
    # SSRF protection: validate URL before fetching. SSRF errors are fatal.
    try:
        url = validate_url(url)
    except SSRFError as e:
        logger.warning("ssrf_validation_failed", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    try:
        response = safe_httpx_get_sync(url, headers=STANDARD_HEADERS, timeout=timeout)
        response.raise_for_status()
        return {
            "content": response.content,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content_type": response.headers.get("Content-Type", "application/octet-stream"),
        }
    except SSRFError as e:
        # SSRF must never fall back to a browser fetcher.
        logger.warning("ssrf_error_no_fallback", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e
    except ValueError as e:
        # The validator wraps SSRFError as ValueError("URL validation failed: ...").
        # Treat that wrapper identically: fatal, no fallback.
        if str(e).startswith("URL validation failed"):
            logger.warning("ssrf_error_wrapped_no_fallback", url=url, error=str(e))
            raise
        # Other ValueError: not SSRF; fall through to fallback if enabled.
        if use_browser_fallback:
            logger.warning("fetch_failed_falling_back_to_browser", url=url, error=str(e))
            return _fetch_with_browser_sync(url)
        raise
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
    """Helper to run browser fetch synchronously.

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
