"""Focused tests for Google Discovery jurisdiction host matching.

Regression for CodeQL py/incomplete-url-substring-sanitization: jurisdiction
must be derived from the parsed URL *hostname* (exact host or subdomain), not a
substring of the raw URL. A crafted path/query containing ``.ny.gov`` must not
be misclassified.
"""

from __future__ import annotations

import pytest

from app.scrapers.state_adaptors.google_discovery import _jurisdiction_from_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.dec.ny.gov/regs/doc.pdf", "US-NY"),
        # Fully-qualified host with a terminal DNS root dot still matches.
        ("https://health.ny.gov./doc.pdf", "US-NY"),
        ("https://ny.gov/alert", "US-NY"),
        ("https://cppa.ca.gov/regulations/", "US-CA"),
        ("https://ca.gov", "US-CA"),
        ("https://www.tdlr.tx.gov/notice", "US-TX"),
        ("https://tx.gov/", "US-TX"),
        ("https://www.fda.gov/food", "US"),
    ],
)
def test_legitimate_hosts_map_to_jurisdiction(url, expected):
    assert _jurisdiction_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        # Government domain appears only in the path/query -> must NOT match.
        "https://evil.example.com/?redirect=.ny.gov",
        "https://evil.example.com/.ca.gov/path",
        "https://attacker.test/#.tx.gov",
        # Lookalike suffix domains must NOT match (no leading dot boundary).
        "https://notny.gov.evil.com/x",
        "https://evilny.gov/x",
    ],
)
def test_spoofed_urls_default_to_generic_us(url):
    assert _jurisdiction_from_url(url) == "US"
