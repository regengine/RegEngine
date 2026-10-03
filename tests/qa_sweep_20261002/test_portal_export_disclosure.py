"""QA BE-011: exported evidence must not disclose a portal bearer capability.

Uses an invalid synthetic identifier only. No portal link is created and no
storage, provider, or network operation is called.
"""

import csv
import io

import pytest

_SYNTHETIC_CAPABILITY = "qa-only-invalid-portal-capability"


def _exported_portal_event_csv():
    from services.ingestion.app.fda_export_service import _generate_csv
    from services.ingestion.app.supplier_portal import SupplierSubmission, _submission_event_dict

    submission = SupplierSubmission(
        traceability_lot_code="QA-LOT-001",
        product_description="QA lettuce",
        quantity=2,
        unit_of_measure="cases",
        ship_date="2026-10-02",
        ship_from_location="QA origin",
        ship_to_location="QA destination",
    )
    event = _submission_event_dict(_SYNTHETIC_CAPABILITY, {"supplier_name": "QA supplier"}, submission)
    # Match the persisted event field names consumed by the FDA formatter.
    event["event_type"] = event["cte_type"]
    event["event_timestamp"] = event["timestamp"]
    return _generate_csv([event], include_pii=False)


def test_portal_export_keeps_lot_and_redacts_location():
    """Positive control: the sample is an otherwise valid redacted FDA row."""
    row = next(csv.DictReader(io.StringIO(_exported_portal_event_csv())))
    assert row["Traceability Lot Code (TLC)"] == "QA-LOT-001"
    assert row["Location Name"] == "[REDACTED]"
    assert "QA origin" not in row["Additional KDEs (JSON)"]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BE-011: supplier portal bearer capability is disclosed in exported KDEs",
)
def test_redacted_fda_export_does_not_disclose_portal_capability():
    exported = _exported_portal_event_csv()
    assert _SYNTHETIC_CAPABILITY not in exported
