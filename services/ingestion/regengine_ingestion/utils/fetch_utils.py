import httpx
import asyncio
import structlog
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from shared.url_validation import validate_url, SSRFError

from shared.url_validation import validate_url

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
    """
    Standard fetch utility with browser fallback support.
    """
    validate_url(url)
    try:
        # SSRF protection: validate URL before fetching
        try:
            url = validate_url(url)
        except SSRFError as e:
            logger.warning("ssrf_validation_failed", url=url, error=str(e))
            raise ValueError(f"URL validation failed: {str(e)}") from e

        response = httpx.get(url, headers=STANDARD_HEADERS, timeout=timeout, follow_redirects=True)
        
        # If blocked or server error, try browser fallback
        if use_browser_fallback and response.status_code in [403, 502, 401]:
             logger.info("fetch_blocked_falling_back_to_browser", url=url, status=response.status_code)
             return _fetch_with_browser_sync(url)
             
        response.raise_for_status()
        
        return {
            "content": response.content,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content_type": response.headers.get("Content-Type", "application/octet-stream")
        }
        
    except Exception as e:
        if use_browser_fallback:
            logger.warning("fetch_failed_falling_back_to_browser", url=url, error=str(e))
            try:
                return _fetch_with_browser_sync(url)
            except Exception as browser_e:
                logger.error("all_fetch_methods_failed", url=url, error=str(browser_e))
                raise browser_e
        raise e

def _fetch_with_browser_sync(url: str) -> Dict[str, Any]:
    """Helper to run browser fetch synchronously."""
    # SSRF protection: validate URL before browser fetch
    try:
        url = validate_url(url)
    except SSRFError as e:
        logger.warning("ssrf_validation_failed_browser_fetch", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    # We import here to avoid circular dependencies if browser_utils imports from here
    # and to keep Playwright dependency isolated.
    try:
        from app.browser_utils import run_browser_fetch
        return run_browser_fetch(url)
    except ImportError:
        logger.error("browser_utils_not_found_cannot_fallback")
        raise RuntimeError("Browser fallback requested but browser_utils not available")
