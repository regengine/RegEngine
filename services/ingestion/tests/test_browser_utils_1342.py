"""Coverage for app/browser_utils.py — Playwright-based URL fetcher.

Locks:
- SSRF validation failure → raises ValueError (wrapping SSRFError)
- Happy-path HTML: response.status/headers surfaced, content encoded utf-8
- Happy-path PDF: content-type starts with application/pdf → response.body()
- page.goto returns None → TimeoutError raised, browser still closed
- page.goto raises OSError → caught-and-reraised, browser still closed
- run_browser_fetch: sync wrapper runs the async function via asyncio.run

Playwright isn't installed in the test env, so we stub
`playwright.async_api` in sys.modules before importing the module.

Issue: #1342
"""

from __future__ import annotations

import sys
from types import ModuleType

# ---------------------------------------------------------------------------
# Stub `playwright.async_api` before app.browser_utils imports it
# ---------------------------------------------------------------------------

_fake_pw_pkg = ModuleType("playwright")
_fake_async_api = ModuleType("playwright.async_api")


def _placeholder_async_playwright():
    raise RuntimeError("Should be monkeypatched before calling")


_fake_async_api.async_playwright = _placeholder_async_playwright
sys.modules.setdefault("playwright", _fake_pw_pkg)
sys.modules.setdefault("playwright.async_api", _fake_async_api)

# Now safe to import the module under test
import asyncio  # noqa: E402
import pytest  # noqa: E402

from app import browser_utils as bu  # noqa: E402
from shared.url_validation import SSRFError  # noqa: E402


# ---------------------------------------------------------------------------
# Silence the logger across all tests.
#
# NOTE: app/browser_utils.py uses `logging.getLogger(...)` (stdlib) but calls
# it with structlog-style kwargs (e.g., `logger.warning(msg, url=url,
# error=str(e))`). That crashes with `TypeError: _log() got an unexpected
# keyword argument` whenever the real stdlib log level is <= WARNING.
# The happy-path only escapes because `logger.info` is gated by
# `isEnabledFor(INFO)`, which is False at default levels.
# The fixture below swaps the logger for a permissive stub so tests can
# validate the surrounding behavior. The underlying bug is flagged
# separately as a follow-up.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    monkeypatch.setattr(bu, "logger", _Silent())


# ---------------------------------------------------------------------------
# Fakes for the Playwright async chain
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {"content-type": "text/html"}
        self._body = body

    async def body(self):
        return self._body


class _FakePage:
    def __init__(self, response=None, content_html="<html>ok</html>", goto_exc=None):
        self._response = response
        self._content = content_html
        self._goto_exc = goto_exc

    async def goto(self, url, wait_until="networkidle", timeout=30000):
        if self._goto_exc is not None:
            raise self._goto_exc
        return self._response

    async def content(self):
        return self._content


class _FakeContext:
    def __init__(self, page):
        self._page = page

    async def new_page(self):
        return self._page


class _FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False
        self.last_user_agent = None

    async def new_context(self, user_agent=None):
        self.last_user_agent = user_agent
        return _FakeContext(self._page)

    async def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser):
        self._browser = browser
        self.last_headless = None

    async def launch(self, headless=True):
        self.last_headless = headless
        return self._browser


class _FakePlaywrightSession:
    def __init__(self, chromium):
        self.chromium = chromium


class _FakeAsyncPlaywright:
    """Async context manager yielding a _FakePlaywrightSession."""
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _install_fake_browser(monkeypatch, *, response=None, content_html="<html>ok</html>", goto_exc=None):
    """Install a fake playwright chain and return the _FakeBrowser so
    tests can assert close() was called."""
    page = _FakePage(response=response, content_html=content_html, goto_exc=goto_exc)
    browser = _FakeBrowser(page)
    chromium = _FakeChromium(browser)
    session = _FakePlaywrightSession(chromium)

    monkeypatch.setattr(bu, "async_playwright", lambda: _FakeAsyncPlaywright(session))
    return browser


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


class TestSSRFGuard:
    def test_ssrf_failure_raises_valueerror(self, monkeypatch):
        def _raise(url):
            raise SSRFError("blocked hostname")

        monkeypatch.setattr(bu, "validate_url", _raise)

        with pytest.raises(ValueError, match="URL validation failed"):
            asyncio.run(bu.fetch_with_browser("http://169.254.169.254/"))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestHappyPaths:
    def test_html_response_encoded_utf8(self, monkeypatch):
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        response = _FakeResponse(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
        )
        browser = _install_fake_browser(monkeypatch, response=response, content_html="<html>hi</html>")

        result = asyncio.run(bu.fetch_with_browser("https://example.com"))

        assert result["status_code"] == 200
        assert result["content"] == b"<html>hi</html>"
        assert result["content_type"] == "text/html; charset=utf-8"
        assert result["headers"] == {"content-type": "text/html; charset=utf-8"}
        # Browser always closed in finally
        assert browser.closed is True
        # User agent threaded through context
        assert browser.last_user_agent == bu.USER_AGENT

    def test_pdf_response_uses_body_bytes(self, monkeypatch):
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        pdf_bytes = b"%PDF-1.4 ..."
        response = _FakeResponse(
            status=200,
            headers={"content-type": "application/pdf"},
            body=pdf_bytes,
        )
        browser = _install_fake_browser(monkeypatch, response=response)

        result = asyncio.run(bu.fetch_with_browser("https://example.com/doc.pdf"))

        assert result["content"] == pdf_bytes
        assert result["content_type"] == "application/pdf"
        assert browser.closed is True

    def test_default_content_type_fallback(self, monkeypatch):
        """When headers don't include content-type, default to text/html."""
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        response = _FakeResponse(status=200, headers={})
        _install_fake_browser(monkeypatch, response=response, content_html="<p>x</p>")

        result = asyncio.run(bu.fetch_with_browser("https://example.com"))

        assert result["content_type"] == "text/html"
        # Still encoded utf-8 bytes (no pdf branch)
        assert result["content"] == b"<p>x</p>"


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    def test_none_response_raises_timeout(self, monkeypatch):
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        browser = _install_fake_browser(monkeypatch, response=None)

        with pytest.raises(TimeoutError, match="No response from browser"):
            asyncio.run(bu.fetch_with_browser("https://example.com"))

        # Browser still closed even on failure
        assert browser.closed is True

    def test_goto_raises_oserror_reraises_and_closes(self, monkeypatch):
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        browser = _install_fake_browser(
            monkeypatch, goto_exc=OSError("network unreachable"),
        )

        with pytest.raises(OSError, match="network unreachable"):
            asyncio.run(bu.fetch_with_browser("https://example.com"))

        assert browser.closed is True

    def test_goto_raises_timeout_reraises(self, monkeypatch):
        monkeypatch.setattr(bu, "validate_url", lambda url: url)
        browser = _install_fake_browser(
            monkeypatch, goto_exc=TimeoutError("load timeout"),
        )

        with pytest.raises(TimeoutError):
            asyncio.run(bu.fetch_with_browser("https://example.com"))
        assert browser.closed is True


# ---------------------------------------------------------------------------
# run_browser_fetch sync wrapper
# ---------------------------------------------------------------------------


class TestRunBrowserFetch:
    def test_wraps_async_via_asyncio_run(self, monkeypatch):
        """Sync wrapper returns the async function's result via asyncio.run."""
        async def _stub(url, timeout=30000):
            return {"stub": True, "url": url, "timeout": timeout}

        monkeypatch.setattr(bu, "fetch_with_browser", _stub)

        out = bu.run_browser_fetch("https://example.com", timeout=5000)
        assert out == {"stub": True, "url": "https://example.com", "timeout": 5000}

    def test_default_timeout_passed_through(self, monkeypatch):
        captured = {}

        async def _stub(url, timeout=30000):
            captured["timeout"] = timeout
            return {}

        monkeypatch.setattr(bu, "fetch_with_browser", _stub)

        bu.run_browser_fetch("https://example.com")
        assert captured["timeout"] == 30000


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_user_agent_is_chrome_like(self):
        assert "Chrome" in bu.USER_AGENT
        assert "Mozilla/5.0" in bu.USER_AGENT
