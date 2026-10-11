"""QA5: domain-allowlist boundary for shared/url_validation.py."""

import pytest
from shared.url_validation import SSRFError, validate_url


def test_allowlist_rejects_lookalike_suffix_domain() -> None:
    with pytest.raises(SSRFError):
        validate_url(
            "http://evilexample.com/",
            allowed_domains=["example.com"],
            resolve_dns=False,
        )


def test_allowlist_accepts_exact_and_subdomain() -> None:
    validate_url(
        "https://example.com/x",
        allowed_domains=["example.com"],
        resolve_dns=False,
    )
    validate_url(
        "https://sub.example.com/x",
        allowed_domains=["example.com"],
        resolve_dns=False,
    )


def test_allowlist_match_is_case_insensitive() -> None:
    validate_url(
        "https://SUB.EXAMPLE.COM/x",
        allowed_domains=["example.com"],
        resolve_dns=False,
    )
