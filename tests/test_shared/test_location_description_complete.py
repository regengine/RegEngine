"""Data-free location completeness checks using only non-blank markers."""

from datetime import datetime, timezone
from itertools import product

import pytest
from shared.fsma_validation import is_location_description_complete
from shared.schemas import FSMALocation, Location

from services.ingestion.app.webhook_models import VALID_UNITS_OF_MEASURE, IngestEvent, WebhookCTEType

VALUES = (None, "", " ", "x")


@pytest.mark.parametrize("name,phone,address,gln", product(VALUES, repeat=4))
def test_completeness_presence_permutations(name, phone, address, gln):
    expected = gln == "x" or all(value == "x" for value in (name, phone, address))
    assert is_location_description_complete(name=name, phone=phone, address=address, gln=gln) is expected


def event_kwargs():
    return dict(
        cte_type=next(iter(WebhookCTEType)),
        traceability_lot_code="x" * 3,
        product_description="x",
        quantity=float(True),
        unit_of_measure=sorted(VALID_UNITS_OF_MEASURE)[0],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.parametrize("name,phone,address", product(VALUES, repeat=3))
@pytest.mark.parametrize("prefix", ("top_level", "location", "ship_from", "ship_to", "receiving"))
def test_webhook_description_presence(name, phone, address, prefix):
    kdes = {f"{prefix}_{field}": value for field, value in zip(("name", "phone", "address"), (name, phone, address))}
    kwargs = event_kwargs() | {"kdes": kdes, "location_gln": " "}
    if prefix == "top_level":
        kwargs.update(
            {f"location_{field}": value for field, value in zip(("name", "phone", "address"), (name, phone, address))}
        )
        kwargs["kdes"] = {}
    if all(value == "x" for value in (name, phone, address)):
        IngestEvent(**kwargs)
    else:
        with pytest.raises(ValueError, match=r"21 CFR 1\.1310"):
            IngestEvent(**kwargs)


@pytest.mark.parametrize("key", ("location_gln", "ship_from_gln", "ship_to_gln", "receiving_gln"))
@pytest.mark.parametrize("value", VALUES)
def test_webhook_kde_gln_presence(key, value):
    kwargs = event_kwargs() | {"kdes": {key: value}}
    if value == "x":
        IngestEvent(**kwargs)
    else:
        with pytest.raises(ValueError, match=r"21 CFR 1\.1310"):
            IngestEvent(**kwargs)


def test_webhook_top_level_and_kde_description():
    IngestEvent(**(event_kwargs() | {"location_name": "x", "location_phone": "x", "kdes": {"location_address": "x"}}))


@pytest.mark.parametrize("prefix", ("ship_from", "ship_to", "receiving"))
def test_legacy_location_name_requires_matching_phone_and_address(prefix):
    kwargs = event_kwargs() | {"kdes": {f"{prefix}_location": "x"}}
    with pytest.raises(ValueError, match=r"21 CFR 1\.1310"):
        IngestEvent(**kwargs)
    kwargs["kdes"].update({f"{prefix}_phone": "x", f"{prefix}_address": "x"})
    IngestEvent(**kwargs)


def test_cannot_combine_different_locations():
    with pytest.raises(ValueError, match=r"21 CFR 1\.1310"):
        IngestEvent(
            **(event_kwargs() | {"kdes": {"ship_from_name": "x", "ship_to_phone": "x", "ship_to_address": "x"}})
        )


@pytest.mark.parametrize("model", (Location, FSMALocation))
def test_location_schema_phone_is_optional(model):
    assert not model.model_fields["phone"].is_required()
    assert model(phone="x").phone == "x"
