"""Factory functions and shared data for golden-path tests."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services"))

from shared.canonical_event import (
    CTEType,
    EventStatus,
    IngestionSource,
    ProvenanceMetadata,
    TraceabilityEvent,
)
from shared.rules.types import RuleDefinition


def make_receiving_event(
    tenant_id: str = "00000000-0000-0000-0000-000000000099",
    tlc: str = "TLC-2026-GOLDEN-001",
    product: str = "Romaine Lettuce",
    quantity: float = 500.0,
    uom: str = "cases",
    from_facility: str = "0061414100001",
    to_facility: str = "0061414100002",
    kdes: Optional[Dict[str, Any]] = None,
    **overrides,
) -> TraceabilityEvent:
    """Build a well-formed receiving event for testing."""
    default_kdes = {
        "receive_date": "2026-04-14",
        "reference_document": "BOL-GOLDEN-001",
        "tlc_source_reference": "0061414100003",
        "immediate_previous_source": "Fresh Farms LLC",
    }
    if kdes is not None:
        default_kdes = kdes

    params = dict(
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
        traceability_lot_code=tlc,
        product_reference=product,
        quantity=quantity,
        unit_of_measure=uom,
        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        from_entity_reference="Fresh Farms LLC",
        kdes=default_kdes,
        raw_payload={"source": "test"},
        provenance_metadata=ProvenanceMetadata(
            mapper_name="test-harness",
            mapper_version="1.0.0",
            original_format="json",
        ),
    )
    params.update(overrides)
    return TraceabilityEvent(**params)


def make_shipping_event(
    tenant_id: str = "00000000-0000-0000-0000-000000000099",
    tlc: str = "TLC-2026-GOLDEN-001",
    product: str = "Romaine Lettuce",
    quantity: float = 500.0,
    from_facility: str = "0061414100002",
    to_facility: str = "0061414100004",
    kdes: Optional[Dict[str, Any]] = None,
    **overrides,
) -> TraceabilityEvent:
    """Build a well-formed shipping event for testing."""
    default_kdes = {
        "ship_date": "2026-04-15",
        "reference_document": "BOL-GOLDEN-002",
        "ship_from_location": from_facility,
    }
    if kdes is not None:
        default_kdes = kdes

    params = dict(
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc),
        traceability_lot_code=tlc,
        product_reference=product,
        quantity=quantity,
        unit_of_measure="cases",
        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        kdes=default_kdes,
        raw_payload={"source": "test"},
    )
    params.update(overrides)
    return TraceabilityEvent(**params)


def make_transformation_event(
    tenant_id: str = "00000000-0000-0000-0000-000000000099",
    input_tlc: str = "TLC-2026-GOLDEN-001",
    output_tlc: str = "TLC-2026-GOLDEN-002",
    input_qty: float = 500.0,
    output_qty: float = 480.0,
    **overrides,
) -> TraceabilityEvent:
    """Build a transformation event (input -> output product)."""
    params = dict(
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.TRANSFORMATION,
        event_timestamp=datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc),
        traceability_lot_code=output_tlc,
        product_reference="Bagged Romaine Salad",
        quantity=output_qty,
        unit_of_measure="cases",
        from_facility_reference="0061414100002",
        to_facility_reference="0061414100002",
        kdes={
            "transformation_date": "2026-04-15",
            "input_traceability_lot_codes": [input_tlc],
            "input_quantities": [input_qty],
            "new_traceability_lot_code": output_tlc,
        },
        raw_payload={"source": "test"},
    )
    params.update(overrides)
    return TraceabilityEvent(**params)


GOLDEN_RULE_SEEDS: List[RuleDefinition] = [
    RuleDefinition(
        rule_id="fsma-golden-001",
        rule_version=1,
        title="Receiving: TLC Source Reference Required",
        description="Receiving events must include the TLC source reference",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR \u00a71.1345(b)(7)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={
            "type": "multi_field_presence",
            "field": "kdes.tlc_source_reference",
            "params": {"fields": ["kdes.tlc_source_reference", "kdes.tlc_source_gln", "from_entity_reference"]},
        },
        failure_reason_template="Receiving event missing {field_name} required by {citation}",
        remediation_suggestion="Request TLC source reference from supplier",
    ),
    RuleDefinition(
        rule_id="fsma-golden-002",
        rule_version=1,
        title="Receiving: Immediate Previous Source Required",
        description="Receiving events must identify the immediate previous source",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR \u00a71.1345(b)(5)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={
            "type": "multi_field_presence",
            "field": "from_entity_reference",
            "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source", "kdes.ship_from_location"]},
        },
        failure_reason_template="Receiving event missing {field_name} \u2014 cannot identify immediate previous source ({citation})",
        remediation_suggestion="Record the business name and location of the shipping entity",
    ),
    RuleDefinition(
        rule_id="fsma-golden-003",
        rule_version=1,
        title="Receiving: Reference Document Required",
        description="Receiving events must include a reference document number",
        severity="warning",
        category="source_reference",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR \u00a71.1345(b)(6)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "kdes.reference_document"},
        failure_reason_template="Receiving event missing {field_name} required by {citation}",
        remediation_suggestion="Record the reference document type and number",
    ),
    RuleDefinition(
        rule_id="fsma-golden-004",
        rule_version=1,
        title="All CTEs: TLC Required",
        description="Every CTE must have a traceability lot code",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": []},
        citation_reference="21 CFR \u00a71.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"},
        failure_reason_template="Event missing {field_name} required by {citation}",
        remediation_suggestion="Every CTE must have a traceability lot code",
    ),
    RuleDefinition(
        rule_id="fsma-golden-005",
        rule_version=1,
        title="Shipping: Ship-From Location Required",
        description="Shipping events must identify the ship-from location",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["shipping"]},
        citation_reference="21 CFR \u00a71.1340(b)(3)",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={
            "type": "multi_field_presence",
            "field": "from_facility_reference",
            "params": {"fields": ["from_facility_reference", "kdes.ship_from_location"]},
        },
        failure_reason_template="Shipping event missing {field_name} required by {citation}",
        remediation_suggestion="Record the GLN or business name of the shipping location",
    ),
]
