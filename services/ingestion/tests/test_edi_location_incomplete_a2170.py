"""A-2170 accept-and-flag checks using structural markers only."""

from datetime import datetime, timezone

import pytest
from app.edi_ingestion import routes
from app.epcis_export import _gln_csv_cell
from app.webhook_models import VALID_UNITS_OF_MEASURE, IngestEvent
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.fixture
def build(monkeypatch):
    # Isolate location checks from X12 date syntax without fabricating a date.
    monkeypatch.setattr(routes, "_ship_timestamp_and_date", lambda *args: (datetime.now(timezone.utc).isoformat(), ""))

    def event(transaction_set="856", **changes):
        extracted = {
            "ship_from_name": " x ",
            "seller_name": " x ",
            "receiving_location_name": " x ",
            "quantity": float(True),
        }
        extracted.update(changes.pop("extracted", {}))
        kwargs = dict(
            transaction_set=transaction_set,
            extracted=extracted,
            traceability_lot_code="xxx",
            product_description_override="x",
            quantity_override=None,
            unit_override=sorted(VALID_UNITS_OF_MEASURE)[0],
            location_override=None,
        )
        kwargs.update(changes)
        return routes._build_ingest_event_for_set(**kwargs)

    return event


@pytest.mark.parametrize(
    "transaction_set,key",
    [
        ("856", "ship_from_gln"),
        ("850", "ship_from_gln"),
        ("810", "seller_gln"),
        ("861", "receiving_location_gln"),
        ("944", "receiving_location_gln"),
        ("945", "ship_from_gln"),
    ],
)
@pytest.mark.parametrize("raw", [None, "", " ", "x", "1", " x "])
def test_incomplete_edi_is_accepted_with_raw_evidence(build, transaction_set, key, raw, caplog):
    event = build(transaction_set, extracted={key: raw})
    assert event.kdes["location_incomplete"] is True
    assert event.kdes[key] == raw
    assert event.location_gln is None
    assert event.location_name == " x "
    assert "location_incomplete accepted=true" in caplog.text


@pytest.mark.parametrize("raw", [None, "", " ", "x", "1", " x ", "x" * 13])
def test_csv_omits_invalid_gln(raw):
    assert _gln_csv_cell(raw) == ""


def test_unflagged_location_still_rejected(build):
    event = build()
    payload = event.model_dump()
    payload["kdes"] = {}
    with pytest.raises(ValidationError, match="21 CFR"):
        IngestEvent(**payload)
    payload["kdes"]["location_incomplete"] = True
    with pytest.raises(ValidationError, match="21 CFR"):
        IngestEvent(**payload)


@pytest.mark.parametrize("lot", ["", "x"])
def test_missing_or_short_lot_still_rejected(build, lot):
    with pytest.raises(ValidationError):
        build(traceability_lot_code=lot)


@pytest.mark.parametrize("quantity", [0, -float(True), float("nan"), float("inf")])
def test_bad_quantity_still_rejected(build, quantity):
    with pytest.raises(ValidationError):
        build(quantity_override=quantity)


@pytest.mark.parametrize("date", [None, "", " ", "x"])
def test_missing_bad_date_still_rejected(date):
    with pytest.raises(HTTPException) as error:
        routes._build_ingest_event_for_set("856", {"ship_date_raw": date}, "xxx", "x", float(True), None, None)
    assert error.value.status_code == 400


@pytest.mark.parametrize("raw", [None, "", " ", "x", "1", "x" * 13])
def test_fda_service_omits_invalid_gln(raw):
    from app.fda_export_service import _event_to_fda_row

    row = _event_to_fda_row(
        {"location_gln": raw, "kdes": {"ship_from_gln": raw, "ship_to_gln": raw, "tlc_source_gln": raw}}
    )
    for column in ("Location GLN", "Ship From GLN", "Ship To GLN", "TLC Source GLN"):
        assert row[column] == ""


@pytest.mark.parametrize("raw", [None, "", " ", " x "])
def test_raw_name_preserved(build, raw):
    event = build("810", extracted={"seller_name": raw, "seller_gln": "x"})
    assert event.location_name == raw
    assert event.kdes["seller_name"] == raw


def test_quantity_element_cannot_be_replaced_with_default(build):
    with pytest.raises(HTTPException) as error:
        build(extracted={"quantity": None}, segments=[["SN1", "", "x"]])
    assert error.value.status_code == 422


@pytest.mark.parametrize("source", ["csv", "portal", "sensitech", "webhook"])
@pytest.mark.parametrize("private_spoof", [False, True])
def test_non_edi_cannot_spoof_bypass(build, source, private_spoof):
    payload = build().model_dump()
    payload["kdes"]["source"] = source
    if private_spoof:
        payload["_edi_allow_incomplete_location"] = True
    with pytest.raises(ValidationError, match="21 CFR"):
        IngestEvent.model_validate(payload)


def test_edi_private_flag_survives_nested_validation(build):
    from app.webhook_models import WebhookPayload

    event = build()
    assert WebhookPayload(source="x", events=[event]).events[0].kdes["location_incomplete"]
    assert "_edi_allow_incomplete_location" not in event.model_dump()
