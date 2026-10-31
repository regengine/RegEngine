"""A-2190: FSMA 204 KDE coverage fixes (contract v3) + FTL ingest gate.

Synthetic fixtures only. SEL-549/590 holds unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING, field_id="FIELD-A7")
    for key in ("harvest_date", "harvest_location_name", "received_date", "received_quantity"):
        kdes.pop(key)
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    for key in ("harvest_date", "harvest_location_name", "received_date", "received_quantity"):
        assert any(key in e for e in errors), errors


def test_initial_packing_requires_field_or_growing_area():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING)
    # no field_id / growing_area_name
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("growing_area_name" in e or "field_id" in e for e in errors)


def test_initial_packing_cooling_required_when_cooled():
    kdes = _fill_required(
        WebhookCTEType.INITIAL_PACKING,
        field_id="FIELD-A7",
        cooled=True,
    )
    errors = _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes))
    assert any("cooling_location_name" in e for e in errors)
    assert any("cooling_date" in e for e in errors)

    kdes["cooling_location_name"] = "Cooler #2"
    kdes["cooling_date"] = "2026-02-26"
    assert _validate_event_kdes(_event(WebhookCTEType.INITIAL_PACKING, kdes)) == []


def test_initial_packing_cooling_optional_when_not_cooled():
    kdes = _fill_required(WebhookCTEType.INITIAL_PACKING, field_id="FIELD-A7")
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


def test_ftl_unknown_still_enforces():
    kdes = _fill_required(WebhookCTEType.HARVESTING)
    kdes.pop("immediate_subsequent_recipient")
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("immediate_subsequent_recipient" in e for e in errors)


def test_ftl_true_enforces():
    kdes = _fill_required(WebhookCTEType.HARVESTING, ftl_covered=True)
    kdes.pop("reference_document")
    errors = _validate_event_kdes(_event(WebhookCTEType.HARVESTING, kdes))
    assert any("reference_document" in e for e in errors)
