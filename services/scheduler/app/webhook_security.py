"""Webhook security helpers — SSRF guard + response body cap (#1084).

Before this module landed, ``WebhookNotifier`` would:

  1. POST to any URL the operator configured, without validating the
     scheme or resolving the target host. That's a Server-Side Request
     Forgery (SSRF) vector: an attacker with permission to set a
     webhook URL could point it at cloud metadata endpoints
     (169.254.169.254), internal Kubernetes services (10.0.0.0/8), or
     loopback (127.0.0.1) to probe or exfiltrate from the scheduler's
     network namespace.

  2. Read the response body in full (``response.content`` /
     ``response.text``) with no byte cap — a malicious endpoint could
     stream GB of data back to the scheduler and OOM it.

This module provides two primitives used by the notifier:

  * ``validate_webhook_url(url)`` — URL scheme + SSRF check. Raises
    ``WebhookURLBlocked`` if the URL is disallowed. Returns the
    resolved IP on success (callers may pin the connect to that IP to
    defeat DNS-rebinding, but the httpx client does not expose the
    primitive cleanly; the validation is best-effort + we also set a
    short timeout).

  * ``read_response_capped(response, limit)`` — stream-read the
    response body up to ``limit`` bytes. Returns the accumulated
    bytes and a ``truncated`` flag.

Configuration via env:
  * ``WEBHOOK_ALLOW_PRIVATE`` — set to ``true`` (case-insensitive) to
    bypass the SSRF guard. Default: ``false``. This is an escape hatch
    for dev/staging where webhooks legitimately target localhost
    callbacks. NEVER set this in production.
  * ``WEBHOOK_ALLOW_HTTP`` — set to ``true`` to allow ``http://`` URLs
    (default only allows ``https://``). Default: ``false``. Same as
    above — dev escape hatch.
  * ``WEBHOOK_MAX_RESPONSE_BYTES`` — cap for response body read.
    Default: 1_048_576 (1 MiB).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger("webhook_security")


# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw == "":
        return default
    return raw in {"1", "true", "yes", "on"}


def get_max_response_bytes() -> int:
    """Return the configured response body cap.

    Honors ``WEBHOOK_MAX_RESPONSE_BYTES`` env. Invalid / non-positive
    values fall back to the default.
    """
    raw = os.getenv("WEBHOOK_MAX_RESPONSE_BYTES", "").strip()
    if not raw:
        return DEFAULT_MAX_RESPONSE_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "webhook_max_response_bytes_invalid_falling_back",
            raw_value=raw,
            default=DEFAULT_MAX_RESPONSE_BYTES,
        )
        return DEFAULT_MAX_RESPONSE_BYTES
    if value <= 0:
        return DEFAULT_MAX_RESPONSE_BYTES
    return value


def allow_private() -> bool:
    """Whether to bypass the SSRF guard (private IPs allowed)."""
    return _env_bool("WEBHOOK_ALLOW_PRIVATE", default=False)


def allow_http() -> bool:
    """Whether to allow ``http://`` URLs (otherwise ``https://`` only)."""
    return _env_bool("WEBHOOK_ALLOW_HTTP", default=False)


# ── Exceptions ──────────────────────────────────────────────────────────────


class WebhookURLBlocked(Exception):
    """Raised when a webhook URL fails the SSRF / scheme check."""


# ── URL validation ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidatedTarget:
    """Result of a successful ``validate_webhook_url`` call."""

    url: str
    scheme: str
    host: str
    # The resolved IPv4/IPv6 addresses. Useful for logging only — the
    # httpx client will re-resolve when it connects. We validate every
    # resolved address for safety (no mixed public/private).
    resolved_ips: Tuple[str, ...]


def _is_disallowed_ip(addr: ipaddress._BaseAddress) -> Optional[str]:
    """Return a human reason if ``addr`` is a blocked range, else None.

    Uses stdlib classification rather than hand-rolled CIDRs where
    possible. Covers: loopback, link-local (incl. 169.254/16),
    private (RFC1918), multicast, reserved, unspecified (0.0.0.0),
    and IPv6 unique-local / site-local.
    """
    # Unspecified: 0.0.0.0 / ::
    if addr.is_unspecified:
        return "unspecified"
    # Loopback: 127/8, ::1
    if addr.is_loopback:
        return "loopback"
    # Link-local: 169.254/16 (covers cloud metadata), fe80::/10
    if addr.is_link_local:
        return "link_local"
    # RFC1918: 10/8, 172.16/12, 192.168/16; IPv6 ULA fc00::/7
    if addr.is_private:
        return "private"
    # Multicast: 224/4, ff00::/8
    if addr.is_multicast:
        return "multicast"
    # Reserved: 240/4 etc.
    if addr.is_reserved:
        return "reserved"
    return None


def _resolve_host(host: str) -> Tuple[ipaddress._BaseAddress, ...]:
    """Resolve a hostname to all IP addresses. Raises ``WebhookURLBlocked``
    on resolution failure (unknown hosts are blocked by default — we
    can't validate what we can't see).

    If ``host`` is already an IP literal, return it wrapped without
    hitting DNS.
    """
    # Literal IP (strip the brackets IPv6 URLs use).
    stripped = host.strip("[]")
    try:
        return (ipaddress.ip_address(stripped),)
    except ValueError:
        pass  # not a literal — fall through to DNS

    try:
        # getaddrinfo returns tuples (family, type, proto, canonname, sockaddr).
        # sockaddr[0] is the address string for both IPv4 and IPv6.
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as err:
        raise WebhookURLBlocked(
            f"DNS resolution failed for host {host!r}: {err}"
        ) from err

    addrs: list[ipaddress._BaseAddress] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        addr_str = sockaddr[0]
        # Strip scope-id from IPv6 (e.g. "fe80::1%eth0").
        addr_str = addr_str.split("%", 1)[0]
        if addr_str in seen:
            continue
        seen.add(addr_str)
        try:
            addrs.append(ipaddress.ip_address(addr_str))
        except ValueError:
            # Shouldn't happen; skip defensively.
            continue
    if not addrs:
        raise WebhookURLBlocked(
            f"DNS resolution returned no addresses for {host!r}"
        )
    return tuple(addrs)


def validate_webhook_url(url: str) -> ValidatedTarget:
    """Validate a webhook URL against the SSRF policy.

    Checks, in order:
      1. URL is well-formed and has a host.
      2. Scheme is ``https`` (``http`` allowed only with
         ``WEBHOOK_ALLOW_HTTP=true``). Other schemes (``file``,
         ``ftp``, ``gopher``, …) always blocked.
      3. Host resolves. Unresolvable hosts are blocked (can't validate
         what we can't see).
      4. EVERY resolved IP is a public unicast address. If any
         resolved IP is loopback / private / link-local / multicast /
         reserved / unspecified, the URL is blocked — unless
         ``WEBHOOK_ALLOW_PRIVATE=true`` (dev escape hatch).

    Returns a ``ValidatedTarget`` on success. Raises
    ``WebhookURLBlocked`` otherwise.
    """
    if not url or not isinstance(url, str):
        raise WebhookURLBlocked("webhook URL is empty")

    try:
        parsed = urlparse(url)
    except Exception as err:  # pragma: no cover — urlparse rarely raises
        raise WebhookURLBlocked(f"malformed URL: {err}") from err

    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""

    if not host:
        raise WebhookURLBlocked(f"URL has no host: {url!r}")

    # ── Scheme gate ─────────────────────────────────────────────────
    if scheme == "https":
        pass
    elif scheme == "http":
        if not allow_http():
            raise WebhookURLBlocked(
                f"http:// URLs are blocked; set WEBHOOK_ALLOW_HTTP=true "
                f"in dev/test to allow (got {url!r})"
            )
    else:
        raise WebhookURLBlocked(
            f"unsupported URL scheme {scheme!r}; only https is allowed "
            f"(http with WEBHOOK_ALLOW_HTTP=true)"
        )

    # ── SSRF gate ───────────────────────────────────────────────────
    addrs = _resolve_host(host)

    if not allow_private():
        for addr in addrs:
            reason = _is_disallowed_ip(addr)
            if reason is not None:
                logger.warning(
                    "webhook_url_blocked_ssrf",
                    url=url,
                    host=host,
                    resolved_ip=str(addr),
                    reason=reason,
                )
                raise WebhookURLBlocked(
                    f"webhook host {host!r} resolves to {addr} "
                    f"({reason}); set WEBHOOK_ALLOW_PRIVATE=true to "
                    f"bypass in dev/test"
                )

    return ValidatedTarget(
        url=url,
        scheme=scheme,
        host=host,
        resolved_ips=tuple(str(a) for a in addrs),
    )


# ── Response body cap ───────────────────────────────────────────────────────


@dataclass
class CappedBody:
    """A truncation-aware snapshot of a response body."""

    data: bytes
    truncated: bool
    byte_count: int

    def as_text_preview(self, max_chars: int = 200) -> str:
        """Decode (lossy) and truncate for logging."""
        try:
            text = self.data.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover — decode never raises with replace
            text = repr(self.data[:max_chars])
        if self.truncated and len(text) <= max_chars:
            return text + " …[truncated]"
        if len(text) > max_chars:
            return text[:max_chars] + "…"
        return text


def read_response_capped(
    response_or_iter,
    limit: Optional[int] = None,
) -> CappedBody:
    """Read a response body up to ``limit`` bytes.

    Accepts either:
      * an httpx.Response that was opened with ``client.stream(...)``
        (i.e. has ``.iter_bytes()`` / ``.iter_raw()`` available)
      * or a raw iterable of byte chunks (useful in tests).

    When the cap is hit, iteration stops early — we do not drain the
    remaining bytes. The connection will be closed by the outer
    ``with`` block in the caller.
    """
    cap = limit if (limit is not None and limit > 0) else get_max_response_bytes()

    # Prefer iter_bytes if it's an httpx Response.
    if isinstance(response_or_iter, httpx.Response):
        chunk_iter: Iterable[bytes] = response_or_iter.iter_bytes()
    elif hasattr(response_or_iter, "iter_bytes"):
        chunk_iter = response_or_iter.iter_bytes()
    else:
        chunk_iter = response_or_iter  # assume already an iterable of bytes

    buf = bytearray()
    truncated = False
    total = 0
    for chunk in chunk_iter:
        if chunk is None:
            continue
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            # Be forgiving with mocks that yield strings.
            chunk = bytes(str(chunk), "utf-8")
        total += len(chunk)
        remaining = cap - len(buf)
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            buf.extend(chunk[:remaining])
            truncated = True
            break
        buf.extend(chunk)

    if truncated:
        logger.warning(
            "webhook_response_body_truncated",
            cap_bytes=cap,
            bytes_read=len(buf),
            total_seen=total,
        )

    return CappedBody(data=bytes(buf), truncated=truncated, byte_count=len(buf))
