"""A-2190: FSMA 204 KDE coverage fixes (contract v3) + FTL ingest gate.

Synthetic fixtures only. SEL-549/590 holds unchanged.
Food Safety Lens answers (2026-10-31) refine packing cooled flag, human-readable
field/growing-area names, and farm location description completeness.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.ingestion.app.webhook_models import INFLOW_CONTRACT_VERSION, REQUIRED_KDES_BY_CTE, WebhookCTEType
from services.ingestion.app.webhook_router_v2.validation import _validate_event_kdes


def _event(cte: WebhookCTEType, kdes: dict, **top) -> SimpleNamespace:
    base = {
        "cte_type": cte,
        "traceability_lot_code": "TLC-A2190-001",
        "product_description": "Roma Tomatoes",
        "quantity": 10,
        "unit_of_measure": "cases",
        "location_name": "Valley Fresh Farms",
        "location_gln": None,
        "kdes": kdes,
    }
    base.update(top)
    return SimpleNamespace(**base)


def _fill_required(cte: WebhookCTEType, **overrides) -> dict:
    kdes = {key: "provided" for key in REQUIRED_KDES_BY_CTE[cte]}
    if cte == WebhookCTEType.INITIAL_PACKING:
        # Lens conditionals (not all listed in REQUIRED_KDES_BY_CTE).
        kdes.setdefault("harvest_location_phone", "+1-831-555-0147")
        kdes.setdefault("harvest_location_address", "100 Farm Rd, Salinas CA")
        kdes.setdefault("growing_area_name", "North Field Block A")
        kdes.setdefault("cooled", "no")
    kdes.update(overrides)
    return kdes


def test_contract_version_is_v3():
    assert str(INFLOW_CONTRACT_VERSION) == "3"


def test_harvesting_requires_immediate_subsequent_recipient():
    kdes = _fill_required(WebhookCTEType.HARVESTING)
    kdes.pop("immediate_subsequent_recipient")
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("immediate_subsequent_recipient" in e for e in errors)


def test_cooling_requires_recipient_and_harvest_location():
    kdes = _fill_required(WebhookCTEType.COOLING)
    kdes.pop("immediate_subsequent_recipient")
    kdes.pop("harvest_location_name")
    errors = _validate_event_kdes(_event(WebhookCTEType.COOLING, kdes))
    assert any("immediate_subsequent_recipient" in e for e in errors)
    assert any("harvest_location_name" in e for e in errors)


def test_initial_packing_requires_harvest_and_received_kdes():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING)
    for key in ("harvest_date", "harvest_location_name", "received_date", "received_quantity"):
        kdes.pop(key)
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    for key in ("harvest_date", "harvest_location_name", "received_date", "received_quantity"):
        assert any(key in e for e in errors), errors


def test_initial_packing_requires_farm_location_phone_and_address():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING)
    kdes.pop("harvest_location_phone")
    kdes.pop("harvest_location_address")
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("harvest_location_phone" in e for e in errors)
    assert any("harvest_location_address" in e for e in errors)


def test_initial_packing_requires_human_readable_growing_area_or_field_name():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING)
    kdes.pop("growing_area_name", None)
    kdes.pop("field_name", None)
    kdes.pop("field_id", None)
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("growing area" in e.lower() or "field name" in e.lower() for e in errors)

    # Opaque internal id alone is not enough.
    kdes["field_id"] = "FIELD-A7"
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("growing area" in e.lower() or "field name" in e.lower() for e in errors)

    # Internal id + readable name is OK (export can map the id).
    kdes["growing_area_name"] = "North Field Block A"
    assert _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes)) == []


def test_initial_packing_requires_explicit_cooled_flag():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING)
    kdes.pop("cooled", None)
    # Presence of cooling fields must NOT satisfy the cooled flag.
    kdes["cooling_location_name"] = "Cooler #2"
    kdes["cooling_date"] = "2026-02-26"
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("cooled" in e for e in errors)


def test_initial_packing_cooling_required_when_cooled_yes():
    kdes = _fill_required(
        WebhookCTEType.INITIAL_PACKING,
        cooled="yes",
    )
    kdes.pop("cooling_location_name", None)
    kdes.pop("cooling_date", None)
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("cooling_location_name" in e for e in errors)
    assert any("cooling_date" in e for e in errors)

    kdes["cooling_location_name"] = "Cooler #2"
    kdes["cooling_date"] = "2026-02-26"
    assert _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes)) == []


def test_initial_packing_cooling_not_required_when_cooled_no():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING, cooled="no")
    kdes.pop("cooling_location_name", None)
    kdes.pop("cooling_date", None)
    assert _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes)) == []


def test_transformation_requires_input_lots_qty_desc():
    kdes = _fill_required(WebhookCTEType.TRANSFORMATION)
    for key in (
        "input_lot_codes",
        "input_quantities",
        "input_units_of_measure",
        "input_product_descriptions",
    ):
        kdes.pop(key)
    errors = _validate_event_kdes(_event(WebhookCTEType.TRANSFORMATION, kdes))
    for key in (
        "input_lot_codes",
        "input_quantities",
        "input_units_of_measure",
        "input_product_descriptions",
    ):
        assert any(key in e for e in errors), errors


def test_transformation_accepts_list_valued_input_lots():
    kdes = _fill_required(
        WebhookCTEType.TRANSFORMATION,
        input_lot_codes=["LOT-A", "LOT-B"],
        input_quantities=["10", "5"],
        input_units_of_measure=["cases", "cases"],
        input_product_descriptions=["Tomatoes", "Lettuce"],
    )
    assert _validate_event_kdes(_event(WebhookCTEType.TRANSFORMATION, kdes)) == []


def test_ftl_false_skips_required_kde_gate():
    # Missing everything that would fail — but explicit non-FTL skips the gate.
    kdes = {"ftl_covered": False}
    assert _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes)) == []


def test_ftl_known_non_ftl_category_skips_required_kde_gate():
    # Category supplied and not on the FTL catalog → is_ftl_food False → skip.
    kdes = {"ftl_category": "Shelf-Stable Bread"}
    assert _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes)) == []


def test_ftl_missing_unknown_still_enforces():
    # No ftl_covered / ftl_category → unknown → enforce required KDEs.
    kdes = _fill_required(WebhookCTEType.HARVESTING)
    kdes.pop("immediate_subsequent_recipient")
    kdes.pop("ftl_covered", None)
    kdes.pop("ftl_category", None)
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("immediate_subsequent_recipient" in e for e in errors)


def test_ftl_true_enforces():
    kdes = _fill_required(WebhookCTEType.HARVESTING, ftl_covered=True)
    kdes.pop("reference_document")
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("reference_document" in e for e in errors)


def test_ftl_known_ftl_category_enforces():
    kdes = _fill_required(WebhookCTEType.HARVESTING, ftl_category="Fresh Tomatoes")
    kdes.pop("immediate_subsequent_recipient")
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("immediate_subsequent_recipient" in e for e in errors)
