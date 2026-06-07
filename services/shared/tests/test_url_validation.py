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
