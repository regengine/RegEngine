"""Regression tests for Stripe redirect-URL allowlist (#1186).

Checkout and portal endpoints previously accepted
``success_url``/``cancel_url``/``return_url`` from the client with no
origin check. The Stripe-branded trust anchor plus an attacker-controlled
redirect target is a classic phishing vector. These tests lock in:

1. The allowlist blocks protocol-relative, http, javascript, data, and
   off-allowlist-host URLs.
2. Common bypass patterns (``regengine.co.attacker.com``, userinfo,
   uppercase scheme) are rejected.
3. First-party hosts (``regengine.co``, ``app.regengine.co``) and
   ``*.vercel.app`` preview deployments are accepted.
4. Operator-configured extras (via env vars) extend the allowlist.
5. Suffix-allowlist entries MUST start with a dot (refuses
   un-dotted suffixes that would match substrings).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import helpers as sh  # noqa: E402


# ── 1. Happy-path: first-party hosts accepted ──────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://regengine.co/dashboard",
        "https://www.regengine.co/pricing",
        "https://app.regengine.co/billing?foo=bar",
        "https://regengine.co/dashboard?checkout=success",
        "https://some-preview-branch-abc123.vercel.app/",
        "https://a.b.c.regengine.co/x/y/z",
    ],
)
def test_allowlisted_urls_pass(url):
    """First-party domains + Vercel previews must validate cleanly."""
    result = sh._validate_redirect_url(url, field="success_url")
    assert result is not None
    assert result.startswith("https://")


# ── 2. Scheme hardening: reject non-https ──────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://regengine.co/dashboard",            # http not allowed
        "javascript:alert(1)",                      # js pseudo-scheme
        "data:text/html,<script>alert(1)</script>", # data URI
        "file:///etc/passwd",                       # file scheme
        "ftp://regengine.co/x",                     # ftp
    ],
)
def test_non_https_scheme_rejected(url):
    with pytest.raises(HTTPException) as exc:
        sh._validate_redirect_url(url, field="success_url")
    assert exc.value.status_code == 400
    assert "redirect" in exc.value.detail["error"]


# ── 3. Bypass patterns: allowlist bypass attempts ──────────────────────────


@pytest.mark.parametrize(
    "url,why",
    [
        (
            "https://regengine.co.attacker.com/dashboard",
            "subdomain-suffix bypass — 'regengine.co' is NOT a suffix match "
            "for this host; attacker-controlled apex",
        ),
        (
            "https://attacker-regengine.co/dashboard",
            "prefix-pollution: host isn't exactly regengine.co, nor a "
            "subdomain (suffix .regengine.co would not match)",
        ),
        (
            "https://evil.com/regengine.co/dashboard",
            "path-level decoration — host is evil.com",
        ),
        (
            "//evil.com/dashboard",
            "protocol-relative rolls with the caller's scheme",
        ),
        (
            "https://regengineaco/dashboard",
            "typo-squat without dot — no suffix match",
        ),
        (
            "https://evil.com@regengine.co/dashboard",
            "userinfo trick — real host is regengine.co but log lines may "
            "show 'evil.com', and some parsers get it wrong",
        ),
        (
            "https://regengine.co@evil.com/dashboard",
            "userinfo trick — real host is evil.com",
        ),
        (
            "https://vercel.app/dashboard",
            "'vercel.app' bare is NOT a preview subdomain; the suffix "
            "match requires a real subdomain",
        ),
    ],
)
def test_bypass_patterns_rejected(url, why):
    """Known open-redirect bypass patterns must be rejected."""
    with pytest.raises(HTTPException) as exc:
        sh._validate_redirect_url(url, field="success_url")
    assert exc.value.status_code == 400, f"{url} should be rejected: {why}"


# ── 4. Structural validation ───────────────────────────────────────────────


def test_empty_url_rejected_by_default():
    with pytest.raises(HTTPException) as exc:
        sh._validate_redirect_url("", field="return_url")
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "missing_redirect_url"


def test_none_url_rejected_by_default():
    with pytest.raises(HTTPException) as exc:
        sh._validate_redirect_url(None, field="return_url")
    assert exc.value.status_code == 400


def test_none_url_allowed_when_allow_none():
    """Callers that fall back to a server default use allow_none=True."""
    assert sh._validate_redirect_url(None, field="return_url", allow_none=True) is None
    assert sh._validate_redirect_url("", field="return_url", allow_none=True) is None


def test_non_string_rejected():
    with pytest.raises(HTTPException):
        sh._validate_redirect_url(12345, field="success_url")  # type: ignore[arg-type]


def test_missing_host_rejected():
    """A URL like ``https:///path`` parses with empty hostname."""
    with pytest.raises(HTTPException) as exc:
        sh._validate_redirect_url("https:///path", field="success_url")
    assert exc.value.status_code == 400


# ── 5. Env-var-extended allowlist ──────────────────────────────────────────


def test_env_var_extends_exact_hosts(monkeypatch):
    """Operators can whitelist additional exact hostnames via env."""
    monkeypatch.setenv("STRIPE_REDIRECT_ALLOWED_HOSTS", "partner.example.com")
    result = sh._validate_redirect_url(
        "https://partner.example.com/oauth/return", field="return_url"
    )
    assert result is not None

    # Random other hosts still rejected.
    with pytest.raises(HTTPException):
        sh._validate_redirect_url(
            "https://random.example.com/x", field="return_url"
        )


def test_env_var_extends_suffix_hosts(monkeypatch):
    """Operators can whitelist suffix matches (must start with a dot)."""
    monkeypatch.setenv(
        "STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES", ".partner.example.com"
    )
    # A subdomain of the suffix passes.
    assert sh._validate_redirect_url(
        "https://tenant-42.partner.example.com/back", field="return_url"
    )
    # Bare apex does NOT match (suffix requires a real subdomain).
    with pytest.raises(HTTPException):
        sh._validate_redirect_url(
            "https://partner.example.com/back", field="return_url"
        )


def test_dotless_suffix_rejected_on_read(monkeypatch):
    """An operator-configured suffix without a leading dot must be
    dropped (otherwise ``regengine.co`` as a suffix would match
    ``evil-regengine.co``)."""
    monkeypatch.setenv(
        "STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES", "regengine.co"  # no dot
    )
    with pytest.raises(HTTPException):
        # Must still reject ``evil-regengine.co``: the dotless suffix
        # was dropped.
        sh._validate_redirect_url(
            "https://evil-regengine.co/phish", field="success_url"
        )


# ── 6. Default values match allowlist ──────────────────────────────────────


def test_default_success_url_passes():
    """The default CheckoutRequest.success_url value must not be
    self-rejected — if it ever changes to an off-allowlist URL, every
    unauthenticated signup breaks."""
    from app.stripe_billing.models import DEFAULT_SUCCESS_URL, DEFAULT_CANCEL_URL
    assert sh._validate_redirect_url(DEFAULT_SUCCESS_URL, field="success_url")
    assert sh._validate_redirect_url(DEFAULT_CANCEL_URL, field="cancel_url")


def test_default_portal_return_url_passes():
    from app.stripe_billing.plans import DEFAULT_PORTAL_RETURN_URL
    assert sh._validate_redirect_url(DEFAULT_PORTAL_RETURN_URL, field="return_url")


# ── 7. Tracking-param / fragment round-trip ────────────────────────────────


def test_query_and_fragment_preserved():
    """Stripe replaces ``{CHECKOUT_SESSION_ID}`` in URLs — our cleaner
    must not strip path/query/fragment."""
    url = "https://regengine.co/dashboard?checkout=success&sid={CHECKOUT_SESSION_ID}#section"
    cleaned = sh._validate_redirect_url(url, field="success_url")
    assert cleaned is not None
    assert "{CHECKOUT_SESSION_ID}" in cleaned
    assert cleaned.endswith("#section")


# ── 8. Case-insensitive host match ─────────────────────────────────────────


def test_uppercase_host_normalized():
    """Hostnames are case-insensitive per RFC 3986. Our validator
    must not be fooled by case variations."""
    cleaned = sh._validate_redirect_url(
        "https://REGENGINE.CO/dashboard", field="success_url"
    )
    assert cleaned is not None
    assert "regengine.co" in cleaned.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
