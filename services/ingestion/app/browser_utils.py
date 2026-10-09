from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import structlog
from playwright.async_api import async_playwright
from shared.url_validation import SSRFError, validate_url

logger = structlog.get_logger("ingestion.browser")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _host_of(url: str) -> str:
    """Normalized hostname of ``url`` (lowercased, no trailing dot)."""
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:
        return ""


def _navigation_allowed(request_url: str, allowed_host: str) -> bool:
    """Check a browser navigation target stays on the validated host.

    The headless browser follows HTTP redirects on its own, unlike the
    pure-HTTP path where every hop is re-validated before connecting.
    Navigation (document redirects, meta refresh, scripted location
    changes) is therefore constrained to the host of the initially
    validated URL. Anything else is treated as an SSRF failure.
    """
    if not allowed_host:
        return False
    return _host_of(request_url) == allowed_host


async def fetch_with_browser(url: str, timeout: int = 30000) -> Dict[str, Any]:
    """
    Fetch content from a URL using Playwright (Chromium).
    Useful for sites with anti-bot measures or heavy JavaScript.
    """
    # SSRF protection: validate URL before browser navigation
    try:
        url = validate_url(url)
    except SSRFError as e:
        logger.warning("ssrf_validation_failed_browser", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    logger.info("browser_fetch_start", url=url)
    allowed_host = _host_of(url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        async def _guard_route(route, request) -> None:
            """Abort requests the SSRF policy forbids before they connect.

            Every request URL is re-validated (blocks private or metadata
            targets, including malicious subresources). Top-level
            navigation must additionally stay on the validated host, so
            a redirect chain cannot carry the browser elsewhere.
            """
            target = request.url
            try:
                validate_url(target)
            except SSRFError as e:
                logger.warning("ssrf_validation_failed_browser_request", url=target, error=str(e))
                await route.abort()
                return
            try:
                is_navigation = request.is_navigation_request()
            except Exception:
                is_navigation = True
            if is_navigation and not _navigation_allowed(target, allowed_host):
                logger.warning("browser_navigation_outside_validated_host", url=target, host=allowed_host)
                await route.abort()
                return
            await route.continue_()

        # Proactive guard: block disallowed hops before the browser
        # connects. Playwright versions without route interception fall
        # back to the post-navigation final-URL check below.
        route_target = getattr(context, "route", None) or getattr(page, "route", None)
        if route_target is not None:
            try:
                await route_target("**/*", _guard_route)
            except (AttributeError, TypeError) as e:
                logger.warning("browser_route_guard_unavailable", error=str(e))

        try:
            # SSRF validation before navigation
            validate_url(url)
            response = await page.goto(url, wait_until="networkidle", timeout=timeout)

            if not response:
                raise TimeoutError("No response from browser")

            # Backstop when route interception is unavailable or a hop
            # slipped through: the landed document must still be on the
            # validated host and pass SSRF validation. Never return
            # content from an off-host or unvalidated document.
            final_url = getattr(page, "url", None)
            if final_url:
                try:
                    validate_url(final_url)
                except SSRFError as e:
                    logger.warning("ssrf_validation_failed_browser_final", url=final_url, error=str(e))
                    raise ValueError(f"URL validation failed: {str(e)}") from e
                if not _navigation_allowed(final_url, allowed_host):
                    logger.warning(
                        "browser_navigation_outside_validated_host",
                        url=final_url,
                        host=allowed_host,
                    )
                    raise ValueError(
                        f"URL validation failed: browser navigated outside validated host '{allowed_host}'"
                    )

            # Get content and metadata
            content = await page.content()
            status = response.status
            headers = response.headers

            # For PDF/Binary, content() won't work well, but for regulatory sites it's mostly HTML
            # If it's a binary response, we'd need response.body()
            if "application/pdf" in headers.get("content-type", "").lower():
                body = await response.body()
                content_bytes = body
            else:
                content_bytes = content.encode("utf-8")

            logger.info("browser_fetch_success", url=url, status=status)

            return {
                "content": content_bytes,
                "status_code": status,
                "headers": headers,
                "content_type": headers.get("content-type", "text/html"),
            }

        except (OSError, IOError, TimeoutError, AttributeError, TypeError) as e:
            logger.error("browser_fetch_failed", url=url, error=str(e))
            raise e
        finally:
            await browser.close()


def run_browser_fetch(url: str, timeout: int = 30000) -> Dict[str, Any]:
    """Sync wrapper for fetch_with_browser."""
    return asyncio.run(fetch_with_browser(url, timeout))
