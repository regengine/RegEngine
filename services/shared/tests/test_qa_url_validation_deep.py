"""Deep QA for shared URL validation: schemes, hosts, allowlists, S3 paths.

Deterministic throughout: DNS is disabled or mocked, no network, no sleeps.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest
from shared.url_validation import (
    PathTraversalError,
    SSRFError,
    validate_s3_key,
    validate_s3_uri,
    validate_url,
)


def _addrinfo(addrs):
    out = []
    for addr in addrs:
        if ":" in addr:
            out.append((socket.AF_INET6, socket.SOCK_STREAM, 0, "", (addr, 0, 0, 0)))
        else:
            out.append((socket.AF_INET, socket.SOCK_STREAM, 0, "", (addr, 0)))
    return out


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://LOCALHOST:8080/x",
        "http://localhost./",
        "http://127.0.0.1/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://169.254.169.254/latest/",
        "http://metadata.google.internal/",
        "http://METADATA.GOOGLE./",
    ],
)
def test_blocked_hosts_rejected_without_dns(url):
    with patch("socket.getaddrinfo") as resolver:
        with pytest.raises(SSRFError):
            validate_url(url)
    resolver.assert_not_called()


def test_uppercase_scheme_accepted():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8"])):
        assert validate_url("HTTP://example.com/") == "HTTP://example.com/"


def test_username_only_userinfo_rejected_before_dns():
    with patch("socket.getaddrinfo") as resolver:
        with pytest.raises(SSRFError, match="embedded credentials"):
            validate_url("https://user@example.com/document")
    resolver.assert_not_called()


def test_allowlist_exact_and_subdomain_pass_case_insensitively():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8"])):
        assert validate_url("https://example.com/", allowed_domains=["example.com"]) == "https://example.com/"
        assert validate_url("https://sub.example.com/", allowed_domains=["EXAMPLE.com"]) == "https://sub.example.com/"


def test_allowlist_rejects_unlisted_domain():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8"])):
        with pytest.raises(SSRFError, match="not in allowed domains"):
            validate_url("https://other.com/", allowed_domains=["example.com"])


@pytest.mark.xfail(
    strict=True,
    reason="BUG url_validation.py:validate_url allowlist uses bare endswith, "
    "so evilexample.com passes an example.com allowlist",
)
def test_allowlist_rejects_suffix_impersonation():
    with patch("socket.getaddrinfo", return_value=_addrinfo(["8.8.8.8"])):
        with pytest.raises(SSRFError):
            validate_url("https://evilexample.com/", allowed_domains=["example.com"])


@pytest.mark.xfail(
    strict=True,
    reason="BUG url_validation.py:validate_url treats an explicit empty "
    "allowed_schemes as 'use the default' instead of denying everything",
)
def test_empty_scheme_allowlist_denies_all():
    with pytest.raises(SSRFError):
        validate_url("http://example.com/", allowed_schemes=frozenset(), resolve_dns=False)


@pytest.mark.parametrize("key", ["a/b/c.csv", "file-name_1.0.txt", "x!_.*'()/-y"])
def test_valid_s3_keys_pass(key):
    assert validate_s3_key(key) == key


@pytest.mark.parametrize(
    "key",
    ["", "..", "../escape", "a/../b", "/absolute", "has space", "semi;colon", "nul\x00byte"],
)
def test_invalid_s3_keys_rejected(key):
    with pytest.raises(PathTraversalError):
        validate_s3_key(key)


def test_s3_uri_parses_bucket_and_key():
    assert validate_s3_uri("s3://my-bucket-1/path/to/key.csv") == (
        "my-bucket-1",
        "path/to/key.csv",
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://my-bucket/key",
        "s3://bucket-only",
        "s3:///key-only",
        "s3://InvalidBucket/key",
        "s3://ab/key",
        "s3://my-bucket/",
        "s3://my-bucket/../escape",
    ],
)
def test_invalid_s3_uris_rejected(uri):
    with pytest.raises((ValueError, PathTraversalError)):
        validate_s3_uri(uri)
