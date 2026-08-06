"""
Sandbox client-IP resolution for per-IP rate limiting.

Mirrors the trusted-proxy precedent in
``services/ingestion/app/stripe_billing/rate_limiting.py`` and
``services/admin/app/audit_middleware.py``: ``X-Forwarded-For`` (then
``X-Real-IP``) is honored ONLY when the immediate connection peer is a
configured trusted proxy. Without that gate an attacker rotates the header
to mint a fresh per-IP rate-limit bucket on every request — a full bypass
that is strictly WORSE than the single-global-bucket bug this resolver
exists to fix.

Behind the Vercel BFF -> Railway topology ``request.client.host`` is always
the proxy's socket address, so every public user is lumped into one bucket.
With a trusted-proxy CIDR configured, we instead key the bucket on the real
client IP the BFF forwards in ``X-Forwarded-For``.

This logic is extracted rather than imported from ``stripe_billing`` because
that module's ``_client_ip`` is private and keyed on the service-specific
``STRIPE_TRUSTED_PROXY_CIDRS`` override; the sandbox needs its own
``SANDBOX_TRUSTED_PROXY_CIDRS`` override (falling back to the shared
``TRUSTED_PROXY_CIDRS``). When neither env var is set, ``X-Forwarded-For``
is ignored and we fall back to ``request.client.host`` — i.e. we fail closed
to the current single-bucket behavior, never to a spoofable header.
"""

from __future__ import annotations

import ipaddress
import logging
import os

logger = logging.getLogger("sandbox.client_ip")


def _trusted_proxy_cidrs() -> list:
    """Parse trusted-proxy CIDRs from env.

    Two env vars accepted (in order): ``SANDBOX_TRUSTED_PROXY_CIDRS``
    (service-specific) wins over the shared ``TRUSTED_PROXY_CIDRS``. Unset =
    ``X-Forwarded-For`` ignored; the raw socket address is used.
    """
    raw = (
        os.getenv("SANDBOX_TRUSTED_PROXY_CIDRS", "").strip()
        or os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
    )
    if not raw:
        return []
    cidrs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("sandbox_trusted_proxy_cidr_invalid value=%s", item)
    return cidrs


def _is_trusted_proxy(client_host: str | None) -> bool:
    if not client_host:
        return False
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for cidr in _trusted_proxy_cidrs():
        if client_ip in cidr:
            return True
    return False


def _looks_like_ip(value: str) -> bool:
    """Lightweight IPv4/IPv6 validity check. Prevents a malformed forwarded
    hop (a hostname, empty string, ``'unknown'``) from landing in the
    rate-limit key where an IP is assumed."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def resolve_client_ip(request) -> str:
    """Resolve the real client IP for per-IP rate limiting.

    Honors ``X-Forwarded-For`` (left-most hop), then ``X-Real-IP``, ONLY when
    the immediate peer is a trusted proxy. Otherwise — and when the forwarded
    value is malformed — falls back to ``request.client.host`` so a spoofed
    header can never open a fresh bucket.
    """
    client_host = request.client.host if request.client else None

    if _is_trusted_proxy(client_host):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Left-most hop is the originator when the chain is trusted.
            first_hop = forwarded.split(",")[0].strip()
            if first_hop and _looks_like_ip(first_hop):
                return first_hop
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            candidate = real_ip.strip()
            if candidate and _looks_like_ip(candidate):
                return candidate

    return client_host or "unknown"
