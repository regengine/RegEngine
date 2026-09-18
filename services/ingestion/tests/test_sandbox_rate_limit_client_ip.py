"""
Security regression coverage for sandbox per-IP rate-limit keying
(PR #2757/#2759).

Background
----------
The sandbox ``/evaluate`` (30/min) and ``/share`` (10/hour) endpoints
advertise a *per-IP* rate limit, but the handlers keyed the limiter on
``request.client.host``. Behind the Vercel BFF -> Railway topology that is
always the proxy's socket address, so every public caller shared ONE global
bucket — a single scraper starved the sandbox for everyone.

The fix routes both call sites through
``app.sandbox.client_ip.resolve_client_ip``, which honors ``X-Forwarded-For``
ONLY when the immediate peer is a configured trusted proxy
(``SANDBOX_TRUSTED_PROXY_CIDRS`` falling back to the shared
``TRUSTED_PROXY_CIDRS``). A wrong fix that blindly trusted the header would be
WORSE than the original bug — an attacker could rotate the header to mint a
fresh bucket per request. These tests pin both halves:

(a) With a trusted proxy configured, two requests carrying DIFFERENT
    ``X-Forwarded-For`` client IPs resolve to DIFFERENT rate-limit keys and
    therefore get SEPARATE buckets.
(b) With NO trusted proxy configured, a spoofed ``X-Forwarded-For`` is
    ignored and the limiter falls back to the socket peer IP.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from services.ingestion.app.sandbox import rate_limiting
from services.ingestion.app.sandbox.client_ip import resolve_client_ip
from starlette.datastructures import Headers

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env_and_buckets(monkeypatch):
    """Start every test from a known state: no trusted-proxy env configured
    and an empty in-memory bucket dict (so bucket keys are unambiguous)."""
    monkeypatch.delenv("SANDBOX_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    rate_limiting._rate_buckets.clear()
    yield
    rate_limiting._rate_buckets.clear()


def _make_request(peer_ip: str | None, headers: dict | None = None):
    """Build a minimal Starlette-ish request stand-in.

    ``resolve_client_ip`` only touches ``request.client.host`` and
    ``request.headers.get(...)``; ``Headers`` gives us the same
    case-insensitive lookup the real object provides.
    """
    client = SimpleNamespace(host=peer_ip) if peer_ip is not None else None
    return SimpleNamespace(client=client, headers=Headers(headers or {}))


def _distinct_bucket_keys_for(*resolved_ips: str) -> set[str]:
    """Drive the in-memory limiter with each resolved IP and return the set of
    bucket keys that were created — proof that distinct clients don't collide."""
    for ip in resolved_ips:
        rate_limiting._check_in_memory(ip, now=1000.0)
    return set(rate_limiting._rate_buckets.keys())


# ===========================================================================
# (a) Trusted proxy configured -> per-client buckets
# ===========================================================================


class TestTrustedProxyHonorsForwardedFor:
    def test_distinct_forwarded_ips_resolve_distinctly(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")

        req_a = _make_request("10.0.0.5", {"x-forwarded-for": "1.1.1.1"})
        req_b = _make_request("10.0.0.5", {"x-forwarded-for": "2.2.2.2"})

        assert resolve_client_ip(req_a) == "1.1.1.1"
        assert resolve_client_ip(req_b) == "2.2.2.2"

    def test_distinct_forwarded_ips_get_separate_buckets(self, monkeypatch):
        """The whole point: two different real clients behind the proxy must
        NOT share one bucket, and the proxy's own IP must never become a key."""
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")

        ip_a = resolve_client_ip(_make_request("10.0.0.5", {"x-forwarded-for": "1.1.1.1"}))
        ip_b = resolve_client_ip(_make_request("10.0.0.5", {"x-forwarded-for": "2.2.2.2"}))

        keys = _distinct_bucket_keys_for(ip_a, ip_b)
        assert keys == {"1.1.1.1", "2.2.2.2"}
        # The shared proxy socket IP is never used as a bucket key.
        assert "10.0.0.5" not in keys

    def test_leftmost_hop_is_used_from_multi_hop_chain(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
        req = _make_request("10.0.0.5", {"x-forwarded-for": "3.3.3.3, 10.0.0.5"})
        assert resolve_client_ip(req) == "3.3.3.3"

    def test_x_real_ip_used_when_no_forwarded_for(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
        req = _make_request("10.0.0.5", {"x-real-ip": "4.4.4.4"})
        assert resolve_client_ip(req) == "4.4.4.4"

    def test_shared_env_var_used_when_specific_unset(self, monkeypatch):
        """SANDBOX_TRUSTED_PROXY_CIDRS unset -> shared TRUSTED_PROXY_CIDRS
        still gates trust."""
        monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.16.0.0/12")
        req = _make_request("172.16.5.9", {"x-forwarded-for": "5.5.5.5"})
        assert resolve_client_ip(req) == "5.5.5.5"

    def test_malformed_forwarded_hop_falls_back_to_peer(self, monkeypatch):
        """A trusted peer sending a garbage first hop must not poison the key."""
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
        req = _make_request("10.0.0.5", {"x-forwarded-for": "not-an-ip"})
        assert resolve_client_ip(req) == "10.0.0.5"


# ===========================================================================
# (b) No / untrusted proxy -> fall back to peer, ignore spoofed XFF
# ===========================================================================


class TestUntrustedPeerIgnoresForwardedFor:
    def test_no_trusted_proxy_ignores_spoofed_forwarded_for(self):
        """Both env vars unset (see fixture): the header is attacker-controlled
        and MUST be ignored in favor of the socket peer."""
        req = _make_request("203.0.113.9", {"x-forwarded-for": "1.1.1.1"})
        assert resolve_client_ip(req) == "203.0.113.9"

    def test_spoofed_forwarded_for_cannot_mint_new_buckets(self):
        """Two requests from the SAME peer with DIFFERENT spoofed XFF values
        must collapse to ONE bucket — otherwise the limiter is bypassable."""
        ip_1 = resolve_client_ip(_make_request("203.0.113.9", {"x-forwarded-for": "1.1.1.1"}))
        ip_2 = resolve_client_ip(_make_request("203.0.113.9", {"x-forwarded-for": "9.9.9.9"}))

        assert ip_1 == ip_2 == "203.0.113.9"
        keys = _distinct_bucket_keys_for(ip_1, ip_2)
        assert keys == {"203.0.113.9"}

    def test_peer_outside_trusted_cidr_ignores_forwarded_for(self, monkeypatch):
        """A trusted CIDR is configured but the peer is NOT inside it: the
        header is still untrusted and ignored."""
        monkeypatch.setenv("SANDBOX_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
        req = _make_request("203.0.113.9", {"x-forwarded-for": "1.1.1.1"})
        assert resolve_client_ip(req) == "203.0.113.9"

    def test_no_client_falls_back_to_unknown(self):
        req = _make_request(None, {"x-forwarded-for": "1.1.1.1"})
        assert resolve_client_ip(req) == "unknown"
