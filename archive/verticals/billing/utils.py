"""
Billing Service — Shared Utilities

Centralised helpers used across all routers and engines:
 - Money formatting
 - Tenant-ID extraction
 - List pagination
 - Standard error responses
"""

from __future__ import annotations

from typing import Optional, Sequence
from fastapi import Header


# ── Money Formatting ──────────────────────────────────────────────

def format_cents(amount_cents: int) -> str:
    """Convert cents to a display string like ``$1,234.56``."""
    sign = "-" if amount_cents < 0 else ""
    abs_cents = abs(amount_cents)
    return f"{sign}${abs_cents / 100:,.2f}"


# ── Tenant Extraction ────────────────────────────────────────────

def get_tenant_id(x_tenant_id: Optional[str] = Header(None)) -> str:
    """Extract tenant ID from the ``X-Tenant-Id`` header.

    Falls back to ``sandbox_tenant`` when no header is present,
    which is the expected behaviour in sandbox / dev mode.
    """
    return x_tenant_id or "sandbox_tenant"


# ── Pagination ────────────────────────────────────────────────────

def paginate(
    items: Sequence,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Apply offset pagination to an in-memory list.

    Returns a dict with ``items``, ``total``, ``page``, ``page_size``,
    ``total_pages``, ``has_next``, and ``has_prev``.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 200))  # cap at 200

    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)

    start = (page - 1) * page_size
    end = start + page_size
    page_items = list(items[start:end])

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
