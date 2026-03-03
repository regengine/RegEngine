from __future__ import annotations

from app.bulk_upload.validators import (
    compute_payload_sha256,
    next_merkle_hash,
    normalize_cte_type,
    validate_and_normalize_payload,
)
from app.supplier_cte_service import _next_merkle_hash, _sha256_json


def test_cte_alias_normalization():
    assert normalize_cte_type("transformation") == "transforming"
    assert normalize_cte_type("first_land_based_receiving") == "first_receiver"
    assert normalize_cte_type("shipping") == "shipping"


def test_hash_and_merkle_functions_match_supplier_path():
    payload = {
        "facility_id": "abc",
        "cte_type": "shipping",
        "tlc_code": "TLC-100",
        "event_time": "2026-03-03T12:00:00+00:00",
        "kde_data": {"quantity": 100, "unit_of_measure": "cases"},
    }
    payload_hash = compute_payload_sha256(payload)
    assert payload_hash == _sha256_json(payload)

    chain_hash = next_merkle_hash(None, payload_hash)
    assert chain_hash == _next_merkle_hash(None, payload_hash)


def test_validate_and_normalize_payload_rejects_unknown_cte_type():
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [
                {
                    "name": "Salinas Packhouse",
                    "street": "1200 Abbott St",
                    "city": "Salinas",
                    "state": "CA",
                    "postal_code": "93901",
                    "roles": ["Packer"],
                }
            ],
            "ftl_scopes": [{"facility_name": "Salinas Packhouse", "category_id": "2"}],
            "tlcs": [{"facility_name": "Salinas Packhouse", "tlc_code": "TLC-2026-SAL-1001"}],
            "events": [
                {
                    "facility_name": "Salinas Packhouse",
                    "tlc_code": "TLC-2026-SAL-1001",
                    "cte_type": "unknown_event",
                    "event_time": "2026-03-03T12:00:00Z",
                    "kde_data": {"quantity": 10},
                }
            ],
        },
        supported_cte_types={
            "shipping",
            "receiving",
            "transforming",
            "harvesting",
            "cooling",
            "initial_packing",
            "first_receiver",
        },
        valid_ftl_category_ids={"1", "2"},
    )

    assert len(normalized["facilities"]) == 1
    assert len(normalized["events"]) == 0
    assert errors
    assert "Unsupported cte_type" in errors[0]["message"]
