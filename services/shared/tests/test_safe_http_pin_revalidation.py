"""Regression test for the safe_http pin re-validation (#2449 low).

``_validate_and_pin`` resolves the host a second time (to pick the address to
pin) after ``validate_url`` has already vetted an earlier resolution. A DNS
rebind between the two lookups could hand back an internal address that then
got pinned unchecked — reopening the SSRF window. The fix re-checks the exact
address being pinned against BLOCKED_NETWORKS.
"""

import pytest
from shared import safe_http
from shared.url_validation import SSRFError


def test_pinned_address_revalidated_against_blocklist(monkeypatch):
    # validate_url passes (simulating the earlier resolution being clean)...
    monkeypatch.setattr(safe_http, "validate_url", lambda url: url)
    # ...but the second resolution rebinds to a loopback address.
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )

    with pytest.raises(SSRFError):
        safe_http._validate_and_pin("https://rebind.example")


def test_public_address_is_pinned(monkeypatch):
    monkeypatch.setattr(safe_http, "validate_url", lambda url: url)
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    addr, host = safe_http._validate_and_pin("https://example.com")
    assert addr == "93.184.216.34"
    assert host == "example.com"
