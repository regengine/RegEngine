"""QA: known scraper bugs that are NOT fixed in this pass.

Each test is ``xfail(strict=True)`` so it fails today (documenting the
bug) and forces cleanup the day the bug is fixed (an XPASS fails strict
mode). Details for each live under Notes for the reviewer in
.metacode_pr.md. No network: HTTP and feed layers are stubbed.

Bugs fixed since (BUG-nydfs-safe-http and BUG-generic-rss-missing-link,
both by #3283) keep their test without the marker as a regression guard.
"""

from __future__ import annotations

import pytest


def test_nydfs_fetch_routes_through_safe_http():
    import app.scrapers.state_adaptors.nydfs as nydfs_mod

    assert hasattr(nydfs_mod, "safe_httpx_get_sync"), "nydfs does not use the safe_http helper"


def test_generic_rss_entry_without_link_is_skipped_not_fatal(monkeypatch):
    import app.scrapers.state_adaptors.generic as generic_mod
    import feedparser

    class _Entry:
        def __init__(self):
            self.title = "untitled"

        def get(self, key, default=None):
            return getattr(self, key, default) if key != "link" else default

    class _Feed:
        entries = [_Entry()]

    class _Response:
        content = b"<rss/>"

        def raise_for_status(self):
            pass

    parsed = []

    def _parse(*args, **kwargs):
        parsed.append(args)
        return _Feed()

    # list_sources downloads the feed through the safe HTTP helper before
    # parsing, so stub that hop too (no network).
    monkeypatch.setattr(generic_mod, "safe_httpx_get_sync", lambda url, **kwargs: _Response())
    monkeypatch.setattr(feedparser, "parse", _parse)

    scraper = generic_mod.GenericRSSScraper(
        feed_url="https://example.com/feed", jurisdiction="US-XX", title_prefix="X"
    )
    assert list(scraper.list_sources()) == []
    assert parsed, "the feed was never parsed, so the entry loop did not run"


@pytest.mark.xfail(
    strict=True,
    reason="BUG-generic-rss-no-ssrf-check: GenericRSSScraper.list_sources "
    "yields feed entry links without validate_url, unlike "
    "FDAEnforcementScraper which validates each extracted URL and skips "
    "SSRF failures. Internal or169.254-style links flow into Sources.",
)
def test_generic_rss_entry_links_are_validated(monkeypatch):
    import app.scrapers.state_adaptors.generic as generic_mod
    import feedparser

    class _Entry:
        link = "http://169.254.169.254/latest/meta-data/"
        title = "internal"

        def get(self, key, default=None):
            return {"published": None, "summary": None}.get(key, default)

    class _Feed:
        entries = [_Entry()]

    calls: list[str] = []

    def _spy_validate(url):
        calls.append(url)
        return url

    monkeypatch.setattr(feedparser, "parse", lambda _url: _Feed())
    monkeypatch.setattr(generic_mod, "validate_url", _spy_validate)

    scraper = generic_mod.GenericRSSScraper(
        feed_url="https://example.com/feed", jurisdiction="US-XX", title_prefix="X"
    )
    list(scraper.list_sources())

    assert calls, "entry links were yielded without SSRF validation"
