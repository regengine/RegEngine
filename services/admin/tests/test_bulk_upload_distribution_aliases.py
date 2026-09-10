"""Legacy distribution aliases must retain shipping semantics through validation."""

import pytest
from app.bulk_upload.validators import normalize_cte_type, validate_and_normalize_payload
from app.supplier_cte_service import SUPPORTED_CTE_TYPES


@pytest.mark.parametrize("alias", ["D", "d", " depletion ", "distribution", "distribute", "di"])
def test_distribution_alias_remains_shipping_after_payload_validation(alias):
    assert normalize_cte_type(alias) == "shipping"
    normalized, issues = validate_and_normalize_payload(
        {
            "events": [
                {
                    "facility_name": "Test Facility",
                    "tlc_code": "LOT-100",
                    "cte_type": alias,
                    "event_time": "2026-09-10T12:00:00Z",
                }
            ]
        },
        supported_cte_types=SUPPORTED_CTE_TYPES,
        valid_ftl_category_ids=set(),
    )
    assert normalized["events"][0]["cte_type"] == "shipping"
    assert issues == []


def test_unknown_alias_still_warns_instead_of_becoming_shipping():
    normalized, issues = validate_and_normalize_payload(
        {"events": [{"facility_name": "Test Facility", "tlc_code": "LOT-100", "cte_type": "unknown_event"}]},
        supported_cte_types=SUPPORTED_CTE_TYPES,
        valid_ftl_category_ids=set(),
    )
    assert normalized["events"][0]["cte_type"] == "receiving"
    assert any("Auto-filled" in issue["message"] for issue in issues)
