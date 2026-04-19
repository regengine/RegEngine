"""Stripe SDK helpers and auth utilities."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import stripe
from fastapi import HTTPException

from app.authz import IngestionPrincipal
from shared.permissions import has_permission

logger = logging.getLogger("stripe-billing.helpers")


def _configure_stripe() -> None:
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
    stripe.api_key = secret_key


# ── Open-redirect defense for Stripe URLs (#1186) ──────────────────────────
# Checkout and portal sessions accept ``success_url``/``cancel_url``/``return_url``
# that the browser navigates to AFTER Stripe. Without an allowlist an attacker
# can chain the Stripe-branded trust anchor into a phishing redirect. The fix
# is a hard allowlist validated at request-admission time: if the URL is
# outside the allowlist we return 400 rather than silently replacing it
# (silent replacement would hide misconfiguration).

_DEFAULT_ALLOWED_HOSTS = (
    "regengine.co",
    "app.regengine.co",
    "www.regengine.co",
)

# Suffixes (after a leading dot-prefix check) that match preview deployments.
# ``vercel.app`` preview URLs are subdomains under ``*.vercel.app``.
_DEFAULT_ALLOWED_HOST_SUFFIXES = (
    ".vercel.app",
    ".regengine.co",  # any subdomain of the prod apex
)


def _allowed_redirect_hosts() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (exact_hosts, suffix_matches).

    Operators can extend the allowlist via:
    - ``STRIPE_REDIRECT_ALLOWED_HOSTS`` = comma-separated exact hostnames
    - ``STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES`` = comma-separated suffixes
      (each MUST start with a dot to avoid ``regengine.co.attacker.com``
      bypasses — we enforce this on read).
    """
    exact = list(_DEFAULT_ALLOWED_HOSTS)
    suffixes = list(_DEFAULT_ALLOWED_HOST_SUFFIXES)

    extra_exact = os.getenv("STRIPE_REDIRECT_ALLOWED_HOSTS", "").strip()
    if extra_exact:
        for host in extra_exact.split(","):
            host = host.strip().lower()
            if host:
                exact.append(host)

    extra_suffixes = os.getenv("STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES", "").strip()
    if extra_suffixes:
        for suf in extra_suffixes.split(","):
            suf = suf.strip().lower()
            if not suf:
                continue
            if not suf.startswith("."):
                # Reject un-dotted suffixes — ``regengine.co`` as a suffix
                # would match ``evil-regengine.co``. Operators must include
                # the leading dot.
                logger.warning(
                    "stripe_allowlist_suffix_missing_dot suffix=%s",
                    suf,
                )
                continue
            suffixes.append(suf)

    return tuple(exact), tuple(suffixes)


def _is_host_allowed(host: str) -> bool:
    """True if ``host`` (lowercased, no port) is in the exact allowlist or
    ends with one of the dotted suffixes."""
    if not host:
        return False
    host = host.lower().strip()
    exact, suffixes = _allowed_redirect_hosts()
    if host in exact:
        return True
    for suf in suffixes:
        # ``suf`` always starts with a dot (validated on read).
        if host.endswith(suf) and len(host) > len(suf):
            return True
    return False


def _validate_redirect_url(
    url: Optional[str],
    *,
    field: str,
    allow_none: bool = False,
) -> Optional[str]:
    """#1186: Validate a Stripe redirect URL against the allowlist.

    Returns the cleaned URL on success; raises HTTP 400 on any violation.
    When ``allow_none`` is True and ``url`` is falsy, returns ``None``
    (callers that fall back to a server-configured default).

    Rejects:
    - ``None``/empty (unless ``allow_none``)
    - Non-``https`` schemes (``http``, ``javascript``, ``data``, etc.)
    - Protocol-relative URLs (``//evil.com/...``)
    - Missing hostname
    - Hostnames outside the allowlist
    - Userinfo-in-URL (``https://evil@regengine.co/...`` can mislead
      downstream log parsers)
    """
    if not url:
        if allow_none:
            return None
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_redirect_url",
                "field": field,
                "message": f"{field} is required",
            },
        )

    if not isinstance(url, str):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_redirect_url", "field": field},
        )

    # Protocol-relative (e.g. ``//evil.com/x``) — ``urlparse`` on a bare
    # ``//host/path`` produces netloc=host, scheme=''. Catch that before
    # the scheme check so the error is specific.
    if url.startswith("//"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "protocol_relative_redirect_rejected",
                "field": field,
                "message": (
                    "Protocol-relative URLs are not allowed; provide a "
                    "full https:// URL within the configured allowlist."
                ),
            },
        )

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unparseable_redirect_url",
                "field": field,
                "message": str(exc),
            },
        )

    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "redirect_scheme_not_https",
                "field": field,
                "scheme": scheme or "(empty)",
                "message": (
                    "Only https:// redirect URLs are allowed for Stripe "
                    "checkout/portal flows."
                ),
            },
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "redirect_userinfo_rejected",
                "field": field,
                "message": (
                    "URLs with embedded user:pass@ are not allowed; "
                    "they confuse downstream log parsers and enable "
                    "spoofed-origin displays."
                ),
            },
        )

    # ``parsed.hostname`` is already lowercased and strips port.
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "redirect_missing_host",
                "field": field,
                "message": "Redirect URL must include a hostname.",
            },
        )

    if not _is_host_allowed(host):
        logger.warning(
            "stripe_redirect_rejected field=%s host=%s",
            field, host,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "redirect_host_not_allowlisted",
                "field": field,
                "host": host,
                "message": (
                    "Redirect URL host is not in the Stripe redirect "
                    "allowlist. Configure STRIPE_REDIRECT_ALLOWED_HOSTS "
                    "or use a first-party domain."
                ),
            },
        )

    # Reconstruct with the lowercased host to normalize; keep path/query
    # untouched so Stripe's own `{CHECKOUT_SESSION_ID}` template tokens
    # survive round-tripping.
    cleaned = urlunparse((
        scheme,
        host if not parsed.port else f"{host}:{parsed.port}",
        parsed.path or "",
        parsed.params or "",
        parsed.query or "",
        parsed.fragment or "",
    ))
    return cleaned


def _format_period_end(epoch_seconds: Optional[int]) -> Optional[str]:
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def _stripe_get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_invoice_period_end(invoice_payload: dict[str, Any]) -> Optional[str]:
    # Stripe invoice payloads can surface period end in several places depending on event type/version.
    direct_period_end = _coerce_optional_int(invoice_payload.get("period_end"))
    if direct_period_end:
        return _format_period_end(direct_period_end)

    lines = invoice_payload.get("lines") or {}
    data = lines.get("data") if isinstance(lines, dict) else None
    if isinstance(data, list):
        for line in data:
            if not isinstance(line, dict):
                continue
            line_period = line.get("period") or {}
            period_end = _coerce_optional_int(line_period.get("end"))
            if period_end:
                return _format_period_end(period_end)

    return None


def _extract_paid_at(invoice_payload: dict[str, Any]) -> Optional[str]:
    status_transitions = invoice_payload.get("status_transitions") or {}
    paid_at = _coerce_optional_int(status_transitions.get("paid_at"))
    if paid_at:
        return _format_period_end(paid_at)

    created = _coerce_optional_int(invoice_payload.get("created"))
    if created:
        return _format_period_end(created)

    return None


def _normalize_scope(scope: str) -> str:
    return scope.strip().lower().replace(":", ".")


def _principal_role(principal: IngestionPrincipal) -> str:
    normalized_scopes = [_normalize_scope(scope) for scope in principal.scopes]
    if has_permission(normalized_scopes, "*") or any(scope.startswith("admin") for scope in normalized_scopes):
        return "admin"
    if any(scope.endswith((".write", ".ingest", ".export", ".verify")) for scope in normalized_scopes):
        return "operator"
    return "viewer"


def _enforce_admin_or_operator(principal: IngestionPrincipal, required_permission: str) -> None:
    if _principal_role(principal) == "viewer":
        raise HTTPException(
            status_code=403,
            detail=(
                "Insufficient role for invoice access: "
                f"requires admin/operator role with '{required_permission}'"
            ),
        )


def _resolve_tenant_context(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    principal: Optional[IngestionPrincipal] = None,
) -> str:
    resolved = (explicit_tenant_id or x_tenant_id or (principal.tenant_id if principal else None) or "").strip()
    if not resolved:
        raise HTTPException(status_code=400, detail="Tenant context required")
    return resolved
