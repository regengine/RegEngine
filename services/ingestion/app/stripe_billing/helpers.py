"""Stripe SDK helpers and auth utilities."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe
from fastapi import HTTPException

from app.authz import IngestionPrincipal
from shared.permissions import has_permission


def _configure_stripe() -> None:
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
    stripe.api_key = secret_key


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
