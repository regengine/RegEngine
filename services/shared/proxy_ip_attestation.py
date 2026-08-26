"""Verify short-lived client-IP attestations emitted by the Vercel BFF."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import time

from starlette.requests import Request

PROXY_CLIENT_IP_HEADER = "x-regengine-proxy-client-ip"
PROXY_IP_TIMESTAMP_HEADER = "x-regengine-proxy-timestamp"
PROXY_IP_SIGNATURE_HEADER = "x-regengine-proxy-signature"
PROXY_IP_HMAC_ENV = "REGENGINE_PROXY_IP_HMAC_KEY"
PROXY_IP_MAX_AGE_SECONDS = 60
PROXY_IP_MIN_KEY_BYTES = 32
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def canonical_ip(value: str | None) -> str | None:
    """Return the Node-compatible wire form for one IPv4/IPv6 literal."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate or "," in candidate or "%" in candidate:
        return None
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)

    # Python 3.13 renders IPv4-mapped IPv6 ``exploded`` values with a dotted
    # IPv4 tail, while Node's WHATWG URL serializer keeps eight hexadecimal
    # groups. Build those groups from the packed bytes so the signed wire form
    # is stable across Python versions and matches the Vercel BFF.
    packed = address.packed
    groups = [
        format(int.from_bytes(packed[offset : offset + 2], "big"), "x")
        for offset in range(0, len(packed), 2)
    ]
    best_start = -1
    best_length = 0
    current_start = -1
    for index, group in enumerate([*groups, "sentinel"]):
        if group == "0":
            if current_start < 0:
                current_start = index
            continue
        if current_start >= 0:
            length = index - current_start
            if length > best_length:
                best_start = current_start
                best_length = length
            current_start = -1

    if best_length < 2:
        return ":".join(groups)
    left = ":".join(groups[:best_start])
    right = ":".join(groups[best_start + best_length :])
    return f"{left}::{right}" if left or right else "::"


def _hmac_key() -> bytes | None:
    value = os.getenv(PROXY_IP_HMAC_ENV)
    if not value:
        return None
    encoded = value.encode("utf-8")
    return encoded if len(encoded) >= PROXY_IP_MIN_KEY_BYTES else None


def verified_proxy_client_ip(request: Request, *, now: int | None = None) -> str | None:
    """Return a fresh authenticated BFF client IP, or ``None`` on uncertainty."""
    client_ip = canonical_ip(request.headers.get(PROXY_CLIENT_IP_HEADER))
    timestamp_raw = request.headers.get(PROXY_IP_TIMESTAMP_HEADER)
    signature = request.headers.get(PROXY_IP_SIGNATURE_HEADER)
    request_id = request.headers.get("x-request-id")
    key = _hmac_key()
    if not client_ip or not timestamp_raw or not signature or not request_id or not key:
        return None
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        return None

    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        return None
    if timestamp_raw != str(timestamp):
        return None

    current_time = int(time.time()) if now is None else int(now)
    if abs(current_time - timestamp) > PROXY_IP_MAX_AGE_SECONDS:
        return None

    payload = f"v1\n{client_ip}\n{timestamp_raw}\n{request.method.upper()}\n{request_id}".encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    expected = "v1=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(signature, expected):
        return None
    return client_ip


__all__ = [
    "PROXY_CLIENT_IP_HEADER",
    "PROXY_IP_SIGNATURE_HEADER",
    "PROXY_IP_TIMESTAMP_HEADER",
    "canonical_ip",
    "verified_proxy_client_ip",
]
