from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from shared.url_validation import validate_url, SSRFError

from shared.url_validation import validate_url

logger = logging.getLogger("ingestion.browser")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        try:
            # SSRF validation before navigation
            validate_url(url)
            response = await page.goto(url, wait_until="networkidle", timeout=timeout)
            
            if not response:
                raise TimeoutError("No response from browser")
                
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
                "content_type": headers.get("content-type", "text/html")
            }
            
        except (OSError, IOError, TimeoutError, AttributeError, TypeError) as e:
            logger.error("browser_fetch_failed", url=url, error=str(e))
            raise e
        finally:
            await browser.close()

def run_browser_fetch(url: str, timeout: int = 30000) -> Dict[str, Any]:
    """Sync wrapper for fetch_with_browser."""
    return asyncio.run(fetch_with_browser(url, timeout))
