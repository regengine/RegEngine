"""EPCIS event validation utilities.

Handles FSMA event validation, GLN check-digit verification, TLC format
checks, and audit logging for validation failures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.ingestion.app.epcis.extraction import _extract_lot_data

logger = logging.getLogger("epcis-ingestion")


def _audit_log_validation_failure(
    errors: list[dict],
    tenant_id: str | None,
    normalized: dict,
) -> None:
    """Fire-and-forget audit log for FSMA validation failures."""
    try:
        import asyncio
        from shared.audit_logging import (
            AuditLogger,
            AuditActor,
            AuditResource,
            AuditEventType,
            AuditEventCategory,
            AuditSeverity,
        )

        failed_fields = [e.get("loc", ["unknown"])[-1] for e in errors]
        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id="epcis-ingestion",
            actor_type="service",
            tenant_id=tenant_id,
        )
        resource = AuditResource(
            resource_type="fsma_event",
            resource_id=normalized.get("idempotency_key") or "unknown",
            tenant_id=tenant_id,
            attributes={"tlc": normalized.get("tlc"), "event_time": normalized.get("event_time")},
        )

        coro = audit.log(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.WARNING,
            actor=actor,
            action="fsma_event_validation",
            outcome="failure",
            resource=resource,
            message=f"FSMAEvent validation rejected: failed KDEs {failed_fields}",
            details={"validation_errors": errors, "tenant_id": tenant_id},
            tags=["fsma", "validation", "kde_rejection"],
        )
        # Best-effort: schedule on running loop or skip
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            logger.warning("audit_log_no_event_loop",
                           outcome="degraded",
                           detail="No running event loop — async audit skipped")
    except Exception:
        logger.warning("audit_log_validation_failure",
                       outcome="degraded",
                       detail="Could not emit audit event for validation failure",
                       exc_info=True)


def _default_product_description(normalized: dict) -> str:
    product_id = normalized.get("product_id")
    if product_id:
        return f"EPCIS Product {product_id}"
    return "EPCIS Traceability Event"


def _validate_as_fsma_event(normalized: dict, tenant_id: str | None = None) -> dict | None:
    """Validate a normalized CTE dict against the FSMAEvent Pydantic model.

    Returns the validated model dict on success, or None if validation fails
    (errors are logged and audit-trailed but do not block ingestion).
    """
    try:
        from shared.schemas import FSMAEvent, FSMAEventType
        from pydantic import ValidationError

        # Map internal event_type strings to FSMAEventType enum
        event_type_map = {
            "shipping": FSMAEventType.SHIPPING,
            "receiving": FSMAEventType.RECEIVING,
            "transformation": FSMAEventType.TRANSFORMATION,
            "initial_packing": FSMAEventType.CREATION,
            "creation": FSMAEventType.CREATION,
        }
        raw_type = (normalized.get("event_type") or "receiving").lower()
        fsma_type = event_type_map.get(raw_type, FSMAEventType.RECEIVING)

        fsma_event = FSMAEvent(
            event_type=fsma_type,
            tlc=normalized.get("tlc") or "UNKNOWN",
            product_description=normalized.get("product_description") or _default_product_description(normalized),
            quantity=normalized.get("quantity"),
            unit_of_measure=normalized.get("unit_of_measure"),
            location_gln=normalized.get("location_id"),
            event_time=normalized.get("event_time") or datetime.now(timezone.utc).isoformat(),
            source_gln=normalized.get("source_location_id"),
            destination_gln=normalized.get("dest_location_id"),
            reference_document_type="EPCIS",
            reference_document_number=None,
            tenant_id=tenant_id,
        )
        return fsma_event.model_dump()
    except ValidationError as exc:
        logger.warning("fsma_event_validation_failed tenant=%s errors=%s", tenant_id, exc.errors())
        _audit_log_validation_failure(exc.errors(), tenant_id, normalized)
        return None
    except ImportError:
        logger.debug("shared.schemas not available for FSMAEvent validation")
        return None


def _validate_gln_format(gln: str) -> bool:
    """Validate a GLN using GS1 check digit algorithm."""
    if not gln or not gln.isdigit() or len(gln) != 13:
        return False
    total = sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(reversed(gln[:-1]))
    )
    expected = (10 - (total % 10)) % 10
    return int(gln[-1]) == expected


def _validate_tlc_format(tlc: str) -> bool:
    """Validate TLC has minimum required length (3+ chars)."""
    return bool(tlc) and len(tlc.strip()) >= 3


def _validate_epcis(event: dict) -> list[str]:
    errors: list[str] = []
    required = ["type", "eventTime", "action", "bizStep"]
    for field in required:
        if not event.get(field):
            errors.append(f"Missing required EPCIS field '{field}'")

    if event.get("type") not in {"ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent"}:
        errors.append("Unsupported EPCIS event type")

    lot_code, tlc = _extract_lot_data(event.get("ilmd") or event.get("extension", {}).get("ilmd"))
    if not tlc and not lot_code:
        errors.append("Missing traceability lot code (fsma:traceabilityLotCode or cbvmda:lotNumber)")
    elif tlc and not _validate_tlc_format(tlc):
        errors.append(f"TLC '{tlc}' is too short (minimum 3 characters)")

    return errors


def _validate_epcis_glns(normalized: dict) -> list[str]:
    """Validate GLN format on location fields, returning warnings."""
    warnings: list[str] = []
    gln_fields = ["location_id", "source_location_id", "dest_location_id"]
    for field in gln_fields:
        value = normalized.get(field)
        if value and value.isdigit() and len(value) == 13 and not _validate_gln_format(value):
            warnings.append(f"Invalid GLN check digit in {field}: {value}")
    return warnings
