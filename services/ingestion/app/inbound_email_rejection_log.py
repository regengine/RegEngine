"""Inbound-email ingestion dead-letter log.

When a Postmark inbound-parse webhook delivery cannot be turned into FSMA
204 CTE events — unknown recipient address, missing/unparseable attachment,
or a CSV with no valid rows — it MUST NOT crash the webhook and MUST NOT be
silently dropped. This module records the rejection so an operator can
review and reprocess it, following the same in-memory-ring-buffer pattern
as ``edi_ingestion/rejection_log.py`` (#1174).

Rejections whose tenant could not be resolved (e.g. the recipient address
matches no registered tenant) are recorded under ``_UNRESOLVED_TENANT_KEY``
since there is no tenant to scope them to yet.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("inbound-email-ingestion")

_INBOUND_EMAIL_REJECTION_CAP_PER_TENANT = int(os.getenv("INBOUND_EMAIL_REJECTION_CAP_PER_TENANT", "1000"))

# Sentinel bucket for rejections recorded before a tenant could be resolved
# (e.g. the recipient address doesn't match any registered tenant).
UNRESOLVED_TENANT_KEY = "__unresolved__"

# Tenant-scoped in-memory rejection store, same shape as the EDI rejection
# log. Outer dict is keyed by ``tenant_id`` (or ``UNRESOLVED_TENANT_KEY``);
# inner OrderedDict is FIFO-evicted once full.
_inbound_email_rejection_store: dict[str, "OrderedDict[str, dict]"] = {}


def _rejection_store_for(tenant_id: str) -> "OrderedDict[str, dict]":
    return _inbound_email_rejection_store.setdefault(tenant_id, OrderedDict())


def record_inbound_email_rejection(
    *,
    tenant_id: str | None,
    reason: str,
    detail: str,
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Record a rejected/quarantined inbound email.

    Returns the rejection record so the caller can surface a rejection_id
    without leaking internal storage details. Always writes a structured
    warning log — even if storage fails — so the audit trail survives.
    """
    bucket_key = tenant_id or UNRESOLVED_TENANT_KEY
    rejection_id = f"inbound-email-rej-{uuid4().hex[:16]}"
    recorded_at = datetime.now(timezone.utc).isoformat()

    record = {
        "rejection_id": rejection_id,
        "tenant_id": tenant_id,
        "reason": reason,
        "detail": detail,
        "sender": sender,
        "recipient": recipient,
        "subject": subject,
        "errors": errors or [],
        "recorded_at": recorded_at,
    }

    store = _rejection_store_for(bucket_key)
    store[rejection_id] = record
    while len(store) > _INBOUND_EMAIL_REJECTION_CAP_PER_TENANT:
        store.popitem(last=False)

    logger.warning(
        "inbound_email_rejection_recorded rejection_id=%s tenant=%s reason=%s recipient=%s sender=%s",
        rejection_id,
        bucket_key,
        reason,
        recipient,
        sender,
    )

    return record


def list_inbound_email_rejections(tenant_id: str) -> list[dict[str, Any]]:
    """Return recorded rejections for a tenant (most recent last)."""
    return list(_rejection_store_for(tenant_id).values())


def reset_inbound_email_rejections() -> None:
    """Test helper: clear the rejection store across tenants."""
    _inbound_email_rejection_store.clear()
