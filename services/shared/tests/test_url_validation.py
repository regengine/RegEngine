"""Tests for shared.url_validation, including IPv6 dual-stack (RE-SEC-006)."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest
from shared.url_validation import SSRFError, validate_url


def _addrinfo(addrs):
    """Build socket.getaddrinfo-style return value for given addresses.

    Each entry is (family, type, proto, canonname, sockaddr). For IPv6 the
    sockaddr is a 4-tuple; for IPv4 it's a 2-tuple. We match what
    getaddrinfo actually returns.
    """
    out = []
    for a in addrs:
        if ":" in a:  # IPv6
            out.append((socket.AF_INET6, socket.SOCK_STREAM, 0, "", (a, 0, 0, 0)))
        else:
            out.append((socket.AF_INET, socket.SOCK_STREAM, 0, "", (a, 0)))
    return out


def test_ipv4_public_passes():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8"])):
        assert validate_url("https://example.com/") == "https://example.com/"


def test_ipv4_private_blocked():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["10.0.0.5"])):
        with pytest.raises(SSRFError):
            validate_url("https://example.com/")


def test_dual_stack_ipv6_loopback_blocked():
    """Dual-stack: A=8.8.8.8, AAAA=::1 must be rejected via the IPv6 blocklist.

    Closes RE-SEC-006 — gethostbyname only saw the A record and let it pass.
    """
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8", "::1"])):
        with pytest.raises(SSRFError):
            validate_url("https://example.com/")


def test_dual_stack_both_public_passes():
    with patch(
        "socket.getaddrinfo",
        return_value=_addrinfo(["8.8.8.8", "2606:4700:4700::1111"]),
    ):
        assert validate_url("https://example.com/") == "https://example.com/"


def test_metadata_ip_literal_blocked():
    with pytest.raises(SSRFError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_localhost_blocked():
    with pytest.raises(SSRFError):
        validate_url("http://localhost/")


def test_credential_bearing_url_is_rejected_before_dns():
    with patch("socket.getaddrinfo") as resolver:
        with pytest.raises(SSRFError, match="embedded credentials"):
            validate_url("https://user:password@example.com/document")  # pragma: allowlist secret
    resolver.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",  # integer-encoded 127.0.0.1
        "http://0x7f000001/",  # hexadecimal 127.0.0.1
        "http://127.1/",  # shortened 127.0.0.1
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6 loopback
    ],
)
def test_alternate_loopback_encodings_are_blocked(url):
    with pytest.raises(SSRFError):
        validate_url(url)


def test_non_global_special_use_address_is_blocked():
    with pytest.raises(SSRFError):
        validate_url("http://100.64.0.1/")


def test_allowlist_exact_domain_passes():
    assert (
        validate_url("https://example.com/", allowed_domains=["example.com"], resolve_dns=False)
        == "https://example.com/"
    )


def test_allowlist_subdomain_passes():
    assert (
        validate_url("https://api.example.com/", allowed_domains=["example.com"], resolve_dns=False)
        == "https://api.example.com/"
    )


def test_allowlist_matching_is_case_insensitive():
    assert (
        validate_url("https://API.EXAMPLE.COM/", allowed_domains=["Example.COM"], resolve_dns=False)
        == "https://API.EXAMPLE.COM/"
    )


def test_allowlist_entry_with_leading_dot_matches_apex_and_subdomains():
    assert (
        validate_url("https://example.com/", allowed_domains=[".example.com"], resolve_dns=False)
        == "https://example.com/"
    )
    assert (
        validate_url("https://api.example.com/", allowed_domains=[".example.com"], resolve_dns=False)
        == "https://api.example.com/"
    )


def test_allowlist_rejects_bare_suffix_without_dot_boundary():
    """evilexample.com shares a string suffix with example.com but is a
    different domain; the allowlist must not match it."""
    with pytest.raises(SSRFError):
        validate_url("https://evilexample.com/", allowed_domains=["example.com"], resolve_dns=False)


def test_allowlist_rejects_allowlisted_domain_as_subdomain_of_attacker():
    with pytest.raises(SSRFError):
        validate_url("https://example.com.evil.com/", allowed_domains=["example.com"], resolve_dns=False)
