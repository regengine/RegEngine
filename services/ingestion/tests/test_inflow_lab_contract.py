from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.webhook_models import IngestEvent
from app.webhook_router_v2 import _validate_event_kdes


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(cte_type: str, kdes: dict) -> IngestEvent:
    return IngestEvent(
        cte_type=cte_type,
        traceability_lot_code=f"TLC-LAB-{cte_type.upper()}",
        product_description="Romaine Lettuce",
        quantity=24,
        unit_of_measure="cases",
        location_name=kdes.get("location_name") or kdes.get("ship_from_location") or "Valley Fresh Farms",
        timestamp=_timestamp(),
        kdes=kdes,
    )


@pytest.mark.parametrize(
    ("cte_type", "kdes"),
    [
        (
            "harvesting",
            {
                "harvest_date": "2026-04-22",
                "farm_location": "Valley Fresh Farms",
                "location_name": "Valley Fresh Farms",
                "reference_document": "Harvest Log HAR-20260422-00001",
                "reference_document_type": "Harvest Log",
                "reference_document_number": "HAR-20260422-00001",
                "traceability_lot_code_source_reference": "SRC-20260422-00001",
            },
        ),
        (
            "initial_packing",
            {
                "packing_date": "2026-04-22",
                "pack_date": "2026-04-22",
                "packing_location": "FreshPack Central",
                "location_name": "FreshPack Central",
                "source_traceability_lot_code": "TLC-LAB-HARVESTING",
                "farm_location": "Valley Fresh Farms",
                "reference_document": "Packout Record PACK-20260422-00001",
                "reference_document_type": "Packout Record",
                "reference_document_number": "PACK-20260422-00001",
                "harvester_business_name": "Valley Fresh Farms",
                "traceability_lot_code_source_reference": "SRC-20260422-00002",
            },
        ),
        (
            "shipping",
            {
                "ship_date": "2026-04-22",
                "ship_from_location": "FreshPack Central",
                "ship_to_location": "Distribution Center #4",
                "carrier": "ColdRoute Freight",
                "reference_document": "Bill of Lading BOL-20260422-00001",
                "reference_document_type": "Bill of Lading",
                "reference_document_number": "BOL-20260422-00001",
                "tlc_source_reference": "SRC-20260422-00002",
                "traceability_lot_code_source_reference": "SRC-20260422-00002",
            },
        ),
    ],
)
def test_representative_inflow_lab_payloads_pass_webhook_kde_validation(cte_type: str, kdes: dict):
    assert _validate_event_kdes(_event(cte_type, kdes)) == []


@pytest.mark.parametrize(
    ("cte_type", "missing_kde", "kdes"),
    [
        (
            "harvesting",
            "reference_document",
            {
                "harvest_date": "2026-04-22",
                "location_name": "Valley Fresh Farms",
                "reference_document": "Harvest Log HAR-20260422-00001",
            },
        ),
        (
            "initial_packing",
            "packing_date",
            {
                "packing_date": "2026-04-22",
                "location_name": "FreshPack Central",
                "reference_document": "Packout Record PACK-20260422-00001",
                "harvester_business_name": "Valley Fresh Farms",
            },
        ),
        (
            "initial_packing",
            "harvester_business_name",
            {
                "packing_date": "2026-04-22",
                "location_name": "FreshPack Central",
                "reference_document": "Packout Record PACK-20260422-00001",
                "harvester_business_name": "Valley Fresh Farms",
            },
        ),
        (
            "shipping",
            "tlc_source_reference",
            {
                "ship_date": "2026-04-22",
                "ship_from_location": "FreshPack Central",
                "ship_to_location": "Distribution Center #4",
                "reference_document": "Bill of Lading BOL-20260422-00001",
                "tlc_source_reference": "SRC-20260422-00002",
            },
        ),
    ],
)
def test_inflow_lab_contract_still_rejects_missing_required_kdes(
    cte_type: str,
    missing_kde: str,
    kdes: dict,
):
    kdes.pop(missing_kde)

    errors = _validate_event_kdes(_event(cte_type, kdes))

    assert any(missing_kde in error for error in errors)
