"""Data-free checks for the webhook event schema and GLN format."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

from app import webhook_models as models  # noqa: E402


def _format_probe() -> str:
    """All-zero GS1 check-digit probe; this does not identify a location."""
    body = "0" * 12
    return body + str(models.calculate_gs1_check_digit(body))


class TestValidateGln:
    def test_valid_gln(self):
        assert models.validate_gln(_format_probe()) == (True, None)

    def test_wrong_check_digit(self):
        probe = _format_probe()
        wrong_digit = str((int(probe[-1]) + 1) % 10)
        valid, error = models.validate_gln(probe[:-1] + wrong_digit)
        assert valid is False
        assert "check digit" in error.lower()

    def test_wrong_length_short(self):
        valid, error = models.validate_gln("")
        assert valid is False
        assert "13 digits" in error

    def test_wrong_length_long(self):
        valid, error = models.validate_gln(_format_probe() + "0")
        assert valid is False
        assert "13 digits" in error

    def test_strips_non_digit_characters(self):
        probe = _format_probe()
        assert models.validate_gln(probe[:1] + "-" + probe[1:]) == (True, None)


class TestWebhookCTEType:
    def test_has_all_cte_types(self):
        assert len(models.WebhookCTEType) == 8

    def test_expected_members(self):
        assert {member.value for member in models.WebhookCTEType} == {
            "growing",
            "harvesting",
            "cooling",
            "initial_packing",
            "first_land_based_receiving",
            "shipping",
            "receiving",
            "transformation",
        }


class TestIngestEvent:
    def test_requires_schema_fields(self):
        with pytest.raises(ValidationError) as exc:
            models.IngestEvent.model_validate({})
        missing = {tuple(error["loc"]) for error in exc.value.errors() if error["type"] == "missing"}
        assert missing == {
            ("cte_type",),
            ("traceability_lot_code",),
            ("product_description",),
            ("quantity",),
            ("unit_of_measure",),
            ("timestamp",),
        }

    @pytest.mark.parametrize("quantity", [float("inf"), float("-inf"), float("nan"), "Infinity", "1e309"])
    def test_rejects_nonfinite_quantity(self, quantity):
        with pytest.raises(ValidationError) as exc:
            models.IngestEvent.model_validate({"quantity": quantity})
        assert any(error["loc"] == ("quantity",) and error["type"] == "finite_number" for error in exc.value.errors())

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_still_rejects_nonpositive_quantity(self, quantity):
        with pytest.raises(ValidationError) as exc:
            models.IngestEvent.model_validate({"quantity": quantity})
        assert any(error["loc"] == ("quantity",) and error["type"] == "greater_than" for error in exc.value.errors())

    def test_rejects_invalid_iso_timestamp(self):
        with pytest.raises(ValidationError) as exc:
            models.IngestEvent.model_validate({"timestamp": ""})
        assert any(error["loc"] == ("timestamp",) for error in exc.value.errors())

    def test_requires_location_gln_or_name(self):
        empty_event = models.IngestEvent.model_construct(kdes={})
        with pytest.raises(ValueError, match="location identifier"):
            empty_event.require_location()
