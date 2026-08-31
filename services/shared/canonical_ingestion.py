"""Shared canonical ingestion orchestration.

This module is the narrow service boundary around ``CanonicalEventStore``:
persist canonical evidence, persist rule evaluations, and create exception
queue entries without each ingestion route reimplementing the same sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from shared.canonical_event import TraceabilityEvent
    from shared.rules.types import EvaluationSummary
else:
    TraceabilityEvent = Any
    EvaluationSummary = Any


@dataclass(frozen=True)
class CanonicalIngestionResult:
    event_id: str
    sha256_hash: Optional[str]
    chain_hash: Optional[str]
    idempotent: bool
    legacy_event_id: Optional[str]
    rule_summary: Optional[EvaluationSummary]


def _anchor_event_id(event: TraceabilityEvent, event_id: Optional[str]) -> None:
    if event_id is None:
        return
    event.event_id = UUID(str(event_id))
    event.prepare_for_persistence()


def _event_data(event: TraceabilityEvent, event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event.event_type.value,
        "traceability_lot_code": event.traceability_lot_code,
        "product_reference": event.product_reference,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "from_facility_reference": event.from_facility_reference,
        "to_facility_reference": event.to_facility_reference,
        "from_entity_reference": event.from_entity_reference,
        "to_entity_reference": event.to_entity_reference,
        "kdes": event.kdes,
    }


def persist_canonical_evidence(
    session: Session,
    event: TraceabilityEvent,
    *,
    precomputed_summary: Optional[EvaluationSummary] = None,
    canonical_event_id: Optional[str] = None,
    dual_write: bool = False,
    skip_chain_write: bool = True,
    create_exceptions: bool = True,
) -> CanonicalIngestionResult:
    """Persist a canonical event and its rule-evaluation evidence."""
    from shared.canonical_persistence import CanonicalEventStore  # noqa: PLC0415
    from shared.rules_engine import RulesEngine  # noqa: PLC0415

    _anchor_event_id(event, canonical_event_id)
    store = CanonicalEventStore(
        session,
        dual_write=dual_write,
        skip_chain_write=skip_chain_write,
    )
    store_result: Any = store.persist_event(event)
    persisted_event_id = str(getattr(store_result, "event_id", None) or event.event_id)

    engine = RulesEngine(session)
    if precomputed_summary is not None and precomputed_summary.results:
        engine.persist_summary(
            precomputed_summary,
            tenant_id=str(event.tenant_id),
            event_id=persisted_event_id,
        )
        summary = precomputed_summary
    else:
        summary = engine.evaluate_event(
            _event_data(event, persisted_event_id),
            persist=True,
            tenant_id=str(event.tenant_id),
        )

    if summary is not None:
        summary.event_id = persisted_event_id
        if create_exceptions and not summary.compliant:
            from shared.exception_queue import ExceptionQueueService  # noqa: PLC0415

            ExceptionQueueService(session).create_exceptions_from_evaluation(
                str(event.tenant_id),
                summary,
            )

    return CanonicalIngestionResult(
        event_id=persisted_event_id,
        sha256_hash=getattr(store_result, "sha256_hash", None),
        chain_hash=getattr(store_result, "chain_hash", None),
        idempotent=bool(getattr(store_result, "idempotent", False)),
        legacy_event_id=getattr(store_result, "legacy_event_id", None),
        rule_summary=summary,
    )
