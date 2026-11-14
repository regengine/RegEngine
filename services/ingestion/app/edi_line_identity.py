"""Stable identity for EDI line events, kept beside the event stores (ADR-007).

Event idempotency keys hash every KDE. For an EDI line that includes its
position and the envelope control numbers, and leaves out quantity. So a
resend under a new ISA13, or with a line removed, gets new keys and is stored
again, and a corrected quantity gets the old key and is dropped.

This module names a line by what the sender's document says it is, and
records that name with the stored event in ``fsma.edi_line_identities``.
Neither key formula changes: the registry is read before the stores write.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from shared.tenant_context import set_tenant_guc
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from .webhook_models import IngestEvent

LINE_CONFLICT_ERROR = "edi_line_content_conflict"

# The sender's own number for the document, per transaction set, first present
# wins. The KDE name is hashed with the value, so a shipment id and an order
# number that happen to be equal stay apart.
_DOCUMENT_NUMBER_KDES: dict[str, tuple[str, ...]] = {
    "856": ("asn_number",),
    "861": ("receiving_advice_number",),
    "944": ("warehouse_receipt_number", "shipment_id", "depositor_order_number"),
    "945": ("shipment_id", "depositor_order_number"),
    "850": ("po_number",),
    "810": ("invoice_number",),
}

# Envelope, position and request metadata. They change when the same line is
# sent again, so they are neither identity nor content.
_ENVELOPE_KDES = frozenset(
    {
        "edi_isa13",
        "edi_gs_control_number",
        "edi_control_number",
        "edi_line_index",
        "edi_isa_sender_id",
        "edi_gs_sender_id",
        "edi_isa_receiver_id",
        "edi_gs_receiver_id",
        "partner_id",
    }
)


@dataclass(frozen=True)
class EDILine:
    """One line's identity and the digest of everything else it says."""

    identity_key: str
    content_digest: str


@dataclass(frozen=True)
class StoredLine:
    """The stored event a known identity points to."""

    content_digest: str
    event_id: str
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _folded(value: Any) -> str:
    """Product text compared without case or spacing differences."""
    return " ".join(_text(value).split()).casefold()


def _event_date(timestamp: str) -> str:
    """The event's calendar date. Time of day is content, not identity."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return timestamp[:10]


def _sha256(value: Any) -> str:
    # EDI KDEs are JSON primitives; ``default=str`` only guards a stray type.
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _identity_fields(event: IngestEvent) -> Optional[list[str]]:
    """The allowlisted identity of a line, or None when the document cannot name it."""
    kdes = event.kdes or {}
    transaction_set = _text(kdes.get("edi_transaction_set"))
    sender = _text(kdes.get("edi_sender_id"))
    if not sender:
        return None
    for name in _DOCUMENT_NUMBER_KDES.get(transaction_set, ()):
        number = _text(kdes.get(name))
        if number:
            break
    else:
        return None
    return [
        "edi-line-v1",
        transaction_set,
        sender,
        _text(kdes.get("edi_receiver_id")),
        name,
        number,
        event.cte_type.value,
        _event_date(event.timestamp),
        _text(event.traceability_lot_code),
        _folded(kdes.get("gtin") or kdes.get("upc") or event.product_description),
    ]


def _content_digest(event: IngestEvent) -> str:
    return _sha256(
        {
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "product_description": event.product_description,
            "timestamp": event.timestamp,
            "location_gln": event.location_gln,
            "location_name": event.location_name,
            "kdes": {key: value for key, value in (event.kdes or {}).items() if key not in _ENVELOPE_KDES},
        }
    )


def identify_lines(events: Sequence[IngestEvent]) -> list[Optional[EDILine]]:
    """Name each event of one interchange, in order.

    Lines that match on every identity field are numbered 1, 2, 3 in document
    order, so two lines for the same lot and product both persist. The number
    depends only on lines equal to this one, not on its position in the file.

    An event with no sender or no document number gets None and keeps the
    behaviour it had before the registry.
    """
    seen: dict[str, int] = {}
    lines: list[Optional[EDILine]] = []
    for event in events:
        fields = _identity_fields(event)
        if fields is None:
            lines.append(None)
            continue
        base = _sha256(fields)
        seen[base] = seen.get(base, 0) + 1
        lines.append(EDILine(_sha256([*fields, seen[base]]), _content_digest(event)))
    return lines


def changed_line_error(conflicts: list[dict[str, Any]]) -> HTTPException:
    """409 for lines whose identity is stored with different content.

    The response names the stored event and never its values: the caller may
    hold a write-only key.
    """
    return HTTPException(
        status_code=409,
        detail={
            "error": LINE_CONFLICT_ERROR,
            "message": (
                "A line of this document is already stored with different content. "
                "Nothing from the interchange was stored. A resend does not change a "
                "stored record, so the line needs review."
            ),
            "needs_review": True,
            "conflicts": conflicts,
        },
    )


class EDILineRegistry:
    """Reads and writes ``fsma.edi_line_identities`` in the ingest transaction."""

    def lookup(self, session: Session, tenant_id: str, lines: Sequence[Optional[EDILine]]) -> dict[str, StoredLine]:
        """Return the stored line for each known identity, keyed by identity.

        Takes the tenant's chain lock first. Both stores take it on their
        first write, so holding it from this read to the commit makes read,
        compare and write one serial step per tenant. Two envelopes carrying
        the same line cannot both find it missing.

        The join hides an identity whose event no longer exists, so a purged
        event is stored again rather than reported as already stored.
        """
        keys = sorted({line.identity_key for line in lines if line is not None})
        if not keys:
            return {}
        tenant = str(UUID(tenant_id))
        set_tenant_guc(session, tenant)
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:tid))"), {"tid": tenant})
        select = text(
            """
            SELECT r.identity_key, r.content_digest, e.id, e.sha256_hash, e.chain_hash
            FROM fsma.edi_line_identities r
            JOIN fsma.cte_events e ON e.id = r.event_id AND e.tenant_id = r.tenant_id
            WHERE r.tenant_id = :tid AND r.identity_key IN :keys
            """
        ).bindparams(bindparam("keys", expanding=True))
        stored: dict[str, StoredLine] = {}
        for start in range(0, len(keys), 500):
            for row in session.execute(select, {"tid": tenant, "keys": keys[start : start + 500]}):
                stored[row[0]] = StoredLine(row[1], str(row[2]), row[3], row[4])
        return stored

    def record(self, session: Session, tenant_id: str, line: EDILine, event_id: str) -> None:
        """Register a line with the event just stored for it; never fail open.

        An existing row is replaced only when its event is gone. Any other
        conflict means two writers stored the same line, which the lock in
        ``lookup`` rules out, so it stops the commit.
        """
        result = session.execute(
            text(
                """
                INSERT INTO fsma.edi_line_identities
                    (tenant_id, identity_key, content_digest, event_id, stored_at)
                VALUES (:tenant_id, :identity_key, :content_digest, CAST(:event_id AS uuid), clock_timestamp())
                ON CONFLICT (tenant_id, identity_key) DO UPDATE
                    SET content_digest = EXCLUDED.content_digest,
                        event_id = EXCLUDED.event_id,
                        stored_at = EXCLUDED.stored_at
                    WHERE NOT EXISTS (
                        SELECT 1 FROM fsma.cte_events e
                        WHERE e.id = edi_line_identities.event_id
                          AND e.tenant_id = edi_line_identities.tenant_id
                    )
                """
            ),
            {
                "tenant_id": str(UUID(tenant_id)),
                "identity_key": line.identity_key,
                "content_digest": line.content_digest,
                "event_id": event_id,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("EDI line identity is already registered; refusing event commit")
