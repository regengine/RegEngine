"""Supplier data quality: pure logic only.

No database. Row dicts stand in for the SELECT results.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from shared.supplier_data_quality import (
    COLUMN_BACKED_KDES,
    DEFAULT_WINDOW_DAYS,
    METRIC_EPCIS_FAILED,
    METRIC_LATE_CTE,
    METRIC_MISSING_KDE,
    METRIC_UNLINKED_LOT,
    MIN_RECORDS,
    WEBHOOK_REQUIRED_KDES,
    fetch_supplier_quality,
    flag_records,
    group_lots,
    lot_is_linked,
    missing_kdes,
    required_record_kdes,
    share_metric,
    summarize_facility,
    unavailable_metric,
    unlinked_lots,
    window_start,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WEBHOOK_MODELS = REPO_ROOT / "services" / "ingestion" / "app" / "webhook_models.py"

COMPLETE_SHIPPING = {
    "product_description": str(uuid.uuid4()),
    # Any positive count; derived rather than picked.
    "quantity": MIN_RECORDS,
    "unit_of_measure": str(uuid.uuid4()),
    "ship_to_location": str(uuid.uuid4()),
    "reference_document": str(uuid.uuid4()),
    "tlc_source_reference": str(uuid.uuid4()),
}


FACILITY_ID = str(uuid.uuid4())
# One generated lot code per generated lot id.
LOT_CODES: dict[str, str] = {}


def _record(cte_type: str, kde_data: dict, lot_code: str | None = None) -> dict:
    return {
        "record_id": uuid.uuid4(),
        "facility_id": FACILITY_ID,
        "cte_type": cte_type,
        "kde_data": kde_data,
        "event_time": None,
        "created_at": None,
        "lot_code": lot_code if lot_code is not None else str(uuid.uuid4()),
    }


def _lot_row(lot_id: str, cte_type: str | None, kde_data: dict | None, output: bool = False) -> dict:
    return {
        "lot_id": lot_id,
        "lot_code": LOT_CODES.setdefault(lot_id, str(uuid.uuid4())),
        "facility_id": FACILITY_ID,
        "cte_type": cte_type,
        "kde_data": kde_data,
        "is_transformation_output": output,
    }


# --- required KDEs -----------------------------------------------------------


def test_required_kdes_match_ingest_webhook_table():
    """The copied table must equal REQUIRED_KDES_BY_CTE, CTE for CTE."""
    spec = importlib.util.spec_from_file_location("_ingestion_webhook_models", WEBHOOK_MODELS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    aliases = {"transformation": "transforming", "first_land_based_receiving": "first_receiver"}
    webhook = {aliases.get(cte.value, cte.value): tuple(kdes) for cte, kdes in module.REQUIRED_KDES_BY_CTE.items()}
    assert webhook == WEBHOOK_REQUIRED_KDES


def test_column_backed_kdes_are_never_required_in_kde_data():
    for cte in WEBHOOK_REQUIRED_KDES:
        assert not set(required_record_kdes(cte)) & COLUMN_BACKED_KDES


def test_receiving_keeps_source_kdes_and_drops_column_kdes():
    assert required_record_kdes("receiving") == (
        "product_description",
        "quantity",
        "unit_of_measure",
        "immediate_previous_source",
        "reference_document",
        "tlc_source_reference",
    )


def test_cte_aliases_resolve():
    assert required_record_kdes("transformation") == required_record_kdes("transforming")
    assert required_record_kdes(" First_Land_Based_Receiving ") == required_record_kdes("first_receiver")


def test_unknown_cte_requires_nothing():
    assert required_record_kdes("growing") == ()
    assert missing_kdes(None, {}) == []


# --- missing KDE -------------------------------------------------------------


def test_complete_shipping_record_has_no_missing_kdes():
    assert missing_kdes("shipping", COMPLETE_SHIPPING) == []


@pytest.mark.parametrize("blank", [None, "", "   ", [], {}])
def test_blank_values_count_as_missing(blank):
    data = {**COMPLETE_SHIPPING, "reference_document": blank}
    assert missing_kdes("shipping", data) == ["reference_document"]


def test_zero_quantity_is_present():
    assert "quantity" not in missing_kdes("shipping", {**COMPLETE_SHIPPING, "quantity": 0})


def test_non_mapping_kde_data_misses_everything():
    assert missing_kdes("cooling", None) == list(required_record_kdes("cooling"))
    assert missing_kdes("cooling", "not a dict") == list(required_record_kdes("cooling"))


def test_flag_records_keeps_only_failing_rows_with_names():
    rows = [_record("shipping", COMPLETE_SHIPPING), _record("shipping", {"quantity": COMPLETE_SHIPPING["quantity"]})]
    flagged = flag_records(rows)
    assert len(flagged) == 1
    assert flagged[0]["record_id"] == rows[1]["record_id"]
    assert "product_description" in flagged[0]["missing_kdes"]


# --- lot linkage -------------------------------------------------------------


def test_lot_linked_by_transformation_output():
    assert lot_is_linked([("shipping", {})], is_transformation_output=True)


@pytest.mark.parametrize(
    "field", ["tlc_source_reference", "tlc_source_gln", "immediate_previous_source", "input_lot_codes"]
)
def test_lot_linked_by_linkage_kde(field):
    assert lot_is_linked([("shipping", {}), ("receiving", {field: str(uuid.uuid4())})], False)


@pytest.mark.parametrize("cte", ["harvesting", "first_receiver", "first_land_based_receiving"])
def test_origin_cte_links_lot(cte):
    assert lot_is_linked([(cte, {})], False)


def test_lot_without_any_link_is_unlinked():
    assert not lot_is_linked([("shipping", {"tlc_source_reference": " "}), ("cooling", {})], False)
    assert not lot_is_linked([], False)


def test_group_lots_collapses_records_per_lot():
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [_lot_row(first, "shipping", {}), _lot_row(first, "receiving", {}), _lot_row(second, "cooling", {})]
    lots = group_lots(rows)
    assert set(lots) == {first, second}
    assert len(lots[first]["records"]) == sum(1 for row in rows if row["lot_id"] == first)


def test_unlinked_lots_returns_ids_and_codes():
    rows = [
        _lot_row(str(uuid.uuid4()), "shipping", {}),
        _lot_row(str(uuid.uuid4()), "receiving", {"tlc_source_reference": str(uuid.uuid4())}),
        _lot_row(str(uuid.uuid4()), "shipping", {}, output=True),
    ]
    unlinked = rows[0]
    assert unlinked_lots(rows) == [
        {"lot_id": unlinked["lot_id"], "lot_code": unlinked["lot_code"], "facility_id": unlinked["facility_id"]}
    ]


# --- share and thresholds ----------------------------------------------------


def test_share_below_min_records_is_not_enough_data_but_keeps_counts():
    records = [_record("shipping", {}) for _ in range(MIN_RECORDS - 1)]
    flagged = records[::2]
    metric = share_metric(METRIC_MISSING_KDE, len(flagged), len(records))
    assert metric["status"] == "not_enough_data"
    assert metric["share"] is None
    assert (metric["numerator"], metric["denominator"]) == (len(flagged), len(records))


def test_share_at_min_records_is_computed():
    records = [_record("shipping", {}) for _ in range(MIN_RECORDS)]
    flagged = records[::2]
    metric = share_metric(METRIC_MISSING_KDE, len(flagged), len(records))
    assert metric["status"] == "ok"
    assert metric["share"] == len(flagged) / len(records)


def test_zero_denominator_is_not_enough_data():
    assert share_metric(METRIC_UNLINKED_LOT, 0, 0)["status"] == "not_enough_data"


def test_min_records_is_twenty():
    assert MIN_RECORDS == 20


def test_unavailable_metric_has_reason_and_no_counts():
    reason = str(uuid.uuid4())
    metric = unavailable_metric(METRIC_LATE_CTE, reason)
    assert metric == {
        "key": METRIC_LATE_CTE,
        "status": "unavailable",
        "numerator": None,
        "denominator": None,
        "share": None,
        "reason": reason,
    }


def test_window_start():
    now = datetime.now(timezone.utc)
    assert window_start(now, DEFAULT_WINDOW_DAYS) == now - timedelta(days=DEFAULT_WINDOW_DAYS)


# --- facility summary --------------------------------------------------------


def test_summarize_facility_keeps_four_separate_metrics():
    complete = [_record("shipping", COMPLETE_SHIPPING) for _ in range(MIN_RECORDS // 2)]
    incomplete = [_record("shipping", {}) for _ in range(MIN_RECORDS - len(complete))]
    records = complete + incomplete
    lots = [_lot_row(str(uuid.uuid4()), "shipping", {}) for _ in range(MIN_RECORDS // 2)]
    summary = summarize_facility(records, lots)

    assert set(summary) == {METRIC_MISSING_KDE, METRIC_UNLINKED_LOT, METRIC_LATE_CTE, METRIC_EPCIS_FAILED}
    assert summary[METRIC_MISSING_KDE]["share"] == len(incomplete) / len(records)
    assert summary[METRIC_UNLINKED_LOT]["status"] == "not_enough_data"
    assert (summary[METRIC_UNLINKED_LOT]["numerator"], summary[METRIC_UNLINKED_LOT]["denominator"]) == (
        len(lots),
        len(lots),
    )
    assert summary[METRIC_LATE_CTE]["status"] == "unavailable"
    assert summary[METRIC_EPCIS_FAILED]["status"] == "unavailable"


def test_fetch_supplier_quality_without_facilities_runs_no_query():
    class NoQuery:
        def execute(self, *args, **kwargs):  # pragma: no cover (must not run)
            raise AssertionError("no query expected")

    assert fetch_supplier_quality(NoQuery(), str(uuid.uuid4()), str(uuid.uuid4()), [], datetime.now(timezone.utc)) == {}
