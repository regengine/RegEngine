"""Contract v2 never substitutes an entity reference for the harvester phone."""

from types import SimpleNamespace

import pytest

from services.ingestion.app.webhook_models import INFLOW_CONTRACT_VERSION, REQUIRED_KDES_BY_CTE, WebhookCTEType
from services.ingestion.app.webhook_router_v2.validation import _validate_event_kdes

def _packing_kdes(**overrides):
    kdes = {key: "provided" for key in REQUIRED_KDES_BY_CTE[WebhookCTEType.INITIAL_PACKING]}
    kdes.update(
        harvest_location_phone="+1-831-555-0147",
        harvest_location_address="100 Farm Rd, Salinas CA",
        growing_area_name="North Field Block A",
        cooled="no",
    )
    kdes.update(overrides)
    return kdes



@pytest.mark.parametrize("phone", [None, "", "  ", 123, {"phone": "555"}])
def test_initial_packing_requires_explicit_string_phone(phone):
    kdes = _packing_kdes(
        harvester_business_phone=phone,
        from_entity_reference="entity-1",
        field_id="FIELD-A7",
    )
    event = SimpleNamespace(
        cte_type=WebhookCTEType.INITIAL_PACKING,
        traceability_lot_code="L1",
        product_description="Lettuce",
        quantity=1,
        unit_of_measure="kg",
        location_name="Farm",
        location_gln=None,
        kdes=kdes,
    )
    assert any("phone" in error.lower() for error in _validate_event_kdes(event))


def test_v2_accepts_supplied_phone():
    kdes = _packing_kdes(
        harvester_business_phone="+1-202-555-0100",
        field_id="FIELD-A7",
    )
    event = SimpleNamespace(
        cte_type=WebhookCTEType.INITIAL_PACKING,
        traceability_lot_code="L1",
        product_description="Lettuce",
        quantity=1,
        unit_of_measure="kg",
        location_name="Farm",
        location_gln=None,
        kdes=kdes,
    )
    assert str(INFLOW_CONTRACT_VERSION) == "3"
    assert _validate_event_kdes(event) == []
