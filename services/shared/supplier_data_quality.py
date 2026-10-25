"""Per supplier data quality over a rolling window.

A *supplier* is a supplier facility (``supplier_facilities.id``), the same
``supplier_key`` that ``public.data_gap_events`` uses. Four metrics are kept
separate on purpose; there is no combined score.

1. ``missing_kde``: share of CTE records (``supplier_cte_events``) received in
   the window that lack at least one required KDE. The required list is the
   ingest webhook's ``REQUIRED_KDES_BY_CTE``, minus the KDEs a supplier record
   carries as columns: the lot code (``lot_id``), the event date
   (``event_time``) and the recording facility's own location
   (``facility_id``).
2. ``unlinked_lot``: share of lot codes active in the window that cannot be
   linked back through the chain. A lot is linked when it is the output of a
   ``fsma.transformation_links`` row, when one of its records carries a lot
   linkage KDE (the same fields the rules engine checks in
   ``shared.rules.seeds``), or when it starts at this facility (harvesting or
   first land based receiving).
3. ``late_cte``: share of CTE records received in the window that arrived
   more than ``supplier_facilities.agreed_sending_hours`` after their
   ``event_time`` (received is ``created_at``). The denominator is the records
   in the window with both times. Our measure against the agreed sending time,
   not an FDA rule. With no agreed hours set, the status is not enough data.
4. ``epcis_failed``: share of EPCIS documents received in the window that were
   rejected (``fsma.epcis_document_receipts``, written by the EPCIS ingest
   routes). Receipts are tenant scoped: an EPCIS upload carries no supplier
   facility, so this cannot be mapped per facility. The tenant wide share is
   computed once and shown on every facility, with
   ``EPCIS_TENANT_SCOPE_REASON`` saying so. It is unavailable only when the
   receipts table cannot be read.

Read only. The record and lot queries filter on tenant, on the calling
supplier user and on that user's facility ids. The EPCIS receipt count
filters on tenant only (see above).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Sequence

from shared.epcis_receipts import fetch_receipt_counts
from sqlalchemy import text

MIN_RECORDS = 20
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365

METRIC_MISSING_KDE = "missing_kde"
METRIC_UNLINKED_LOT = "unlinked_lot"
METRIC_LATE_CTE = "late_cte"
METRIC_EPCIS_FAILED = "epcis_failed"
DRILLDOWN_METRICS = (METRIC_MISSING_KDE, METRIC_UNLINKED_LOT, METRIC_LATE_CTE)

LATE_CTE_LABEL = "Our measure, based on the agreed sending time with this supplier; not a regulatory requirement"
LATE_CTE_NO_HOURS_REASON = "No agreed sending time is set for this supplier, so late records cannot be measured."
EPCIS_TENANT_SCOPE_REASON = (
    "Counted for your whole account, not for this facility: an EPCIS upload is not linked "
    "to a facility, so every facility shows the same count."
)
EPCIS_UNAVAILABLE_REASON = "EPCIS document receipts could not be read."

# Copy of services/ingestion/app/webhook_models.py REQUIRED_KDES_BY_CTE, keyed
# by supplier CTE name. The admin service cannot import the ingestion package
# (both are named ``app``); services/shared/tests/test_supplier_data_quality.py fails if
# the two tables drift.
WEBHOOK_REQUIRED_KDES: dict[str, tuple[str, ...]] = {
    "harvesting": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "harvest_date",
        "location_name",
        "reference_document",
    ),
    "cooling": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "cooling_date",
        "location_name",
        "reference_document",
    ),
    "initial_packing": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "packing_date",
        "location_name",
        "reference_document",
        "harvester_business_name",
        "harvester_business_phone",
    ),
    "first_receiver": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "landing_date",
        "receiving_location",
        "reference_document",
    ),
    "shipping": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "ship_date",
        "ship_from_location",
        "ship_to_location",
        "reference_document",
        "tlc_source_reference",
    ),
    "receiving": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "receive_date",
        "receiving_location",
        "immediate_previous_source",
        "reference_document",
        "tlc_source_reference",
    ),
    "transforming": (
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "transformation_date",
        "location_name",
        "reference_document",
    ),
}

# Supplied by supplier_cte_events columns, not kde_data: lot_id, event_time,
# and facility_id (the recording facility's own location).
COLUMN_BACKED_KDES = frozenset(
    {
        "traceability_lot_code",
        "harvest_date",
        "cooling_date",
        "packing_date",
        "landing_date",
        "ship_date",
        "receive_date",
        "transformation_date",
        "location_name",
        "receiving_location",
        "ship_from_location",
    }
)

# Lot linkage fields from shared.rules.seeds (receiving, shipping and
# transformation lot_linkage / kde_presence rules), plus the harvester the
# initial packer must record (21 CFR 1.1330(a)(7)).
LINKAGE_KDES = (
    "tlc_source_reference",
    "tlc_source_gln",
    "immediate_previous_source",
    "input_lot_codes",
    "input_traceability_lot_codes",
    "input_tlcs",
    "harvester_business_name",
)
# The chain starts at these CTEs; there is nothing upstream to link to.
ORIGIN_CTES = frozenset({"harvesting", "first_receiver"})

_CTE_ALIASES = {
    "transformation": "transforming",
    "first_land_based_receiving": "first_receiver",
}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def normalize_cte(cte_type: Optional[str]) -> str:
    value = (cte_type or "").strip().lower()
    return _CTE_ALIASES.get(value, value)


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def required_record_kdes(cte_type: Optional[str]) -> tuple[str, ...]:
    """KDEs a supplier record must carry in ``kde_data`` for its CTE."""
    required = WEBHOOK_REQUIRED_KDES.get(normalize_cte(cte_type), ())
    return tuple(name for name in required if name not in COLUMN_BACKED_KDES)


def missing_kdes(cte_type: Optional[str], kde_data: Optional[Mapping[str, Any]]) -> list[str]:
    data = kde_data if isinstance(kde_data, Mapping) else {}
    return [name for name in required_record_kdes(cte_type) if not _present(data.get(name))]


def lot_is_linked(
    records: Sequence[tuple[Optional[str], Optional[Mapping[str, Any]]]],
    is_transformation_output: bool,
) -> bool:
    """True when a lot links back: transformation output, linkage KDE, or origin CTE.

    ``records`` is every (cte_type, kde_data) recorded for the lot.
    """
    if is_transformation_output:
        return True
    for cte_type, kde_data in records:
        if normalize_cte(cte_type) in ORIGIN_CTES:
            return True
        data = kde_data if isinstance(kde_data, Mapping) else {}
        if any(_present(data.get(name)) for name in LINKAGE_KDES):
            return True
    return False


def share_metric(key: str, numerator: int, denominator: int, min_records: int = MIN_RECORDS) -> dict[str, Any]:
    """Numerator and denominator always; a share only from ``min_records`` up."""
    enough = denominator >= min_records
    return {
        "key": key,
        "status": "ok" if enough else "not_enough_data",
        "numerator": numerator,
        "denominator": denominator,
        "share": (numerator / denominator) if enough else None,
        "reason": None,
    }


def timed_records(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Records with both an event time and a received time: the late denominator."""
    return [row for row in rows if row.get("event_time") is not None and row.get("created_at") is not None]


def late_records(rows: Sequence[Mapping[str, Any]], agreed_sending_hours: int) -> list[Mapping[str, Any]]:
    """Records received (``created_at``) more than ``agreed_sending_hours`` after ``event_time``."""
    allowed = timedelta(hours=agreed_sending_hours)
    return [row for row in timed_records(rows) if row["created_at"] - row["event_time"] > allowed]


def late_metric(rows: Sequence[Mapping[str, Any]], agreed_sending_hours: Optional[int]) -> dict[str, Any]:
    if agreed_sending_hours is None:
        return {
            "key": METRIC_LATE_CTE,
            "status": "not_enough_data",
            "numerator": None,
            "denominator": None,
            "share": None,
            "reason": LATE_CTE_NO_HOURS_REASON,
        }
    return share_metric(METRIC_LATE_CTE, len(late_records(rows, agreed_sending_hours)), len(timed_records(rows)))


def unavailable_metric(key: str, reason: str) -> dict[str, Any]:
    return {
        "key": key,
        "status": "unavailable",
        "numerator": None,
        "denominator": None,
        "share": None,
        "reason": reason,
    }


def epcis_failed_metric(counts: Optional[tuple[int, int]]) -> dict[str, Any]:
    """Tenant wide rejected share from (rejected, total) receipt counts."""
    if counts is None:
        return unavailable_metric(METRIC_EPCIS_FAILED, EPCIS_UNAVAILABLE_REASON)
    rejected, total = counts
    return {**share_metric(METRIC_EPCIS_FAILED, rejected, total), "reason": EPCIS_TENANT_SCOPE_REASON}


def window_start(now: datetime, window_days: int) -> datetime:
    return now - timedelta(days=window_days)


def flag_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Records missing at least one required KDE, with the missing names."""
    flagged: list[dict[str, Any]] = []
    for row in rows:
        missing = missing_kdes(row["cte_type"], row["kde_data"])
        if missing:
            flagged.append({**row, "missing_kdes": missing})
    return flagged


def group_lots(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collapse one row per (lot, record) into one entry per lot id."""
    lots: dict[str, dict[str, Any]] = {}
    for row in rows:
        lot_id = str(row["lot_id"])
        lot = lots.setdefault(
            lot_id,
            {
                "lot_id": lot_id,
                "lot_code": row["lot_code"],
                "facility_id": str(row["facility_id"]),
                "is_transformation_output": bool(row["is_transformation_output"]),
                "records": [],
            },
        )
        if row.get("cte_type") is not None:
            lot["records"].append((row["cte_type"], row["kde_data"]))
    return lots


def unlinked_lots(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"lot_id": lot["lot_id"], "lot_code": lot["lot_code"], "facility_id": lot["facility_id"]}
        for lot in group_lots(rows).values()
        if not lot_is_linked(lot["records"], lot["is_transformation_output"])
    ]


def summarize_facility(
    record_rows: Sequence[Mapping[str, Any]],
    lot_rows: Sequence[Mapping[str, Any]],
    agreed_sending_hours: Optional[int] = None,
    epcis_counts: Optional[tuple[int, int]] = None,
) -> dict[str, dict[str, Any]]:
    """The four metrics for one facility, keyed by metric.

    ``epcis_counts`` is the tenant wide (rejected, total), not per facility.
    """
    lot_count = len(group_lots(lot_rows))
    return {
        METRIC_MISSING_KDE: share_metric(METRIC_MISSING_KDE, len(flag_records(record_rows)), len(record_rows)),
        METRIC_UNLINKED_LOT: share_metric(METRIC_UNLINKED_LOT, len(unlinked_lots(lot_rows)), lot_count),
        METRIC_LATE_CTE: late_metric(record_rows, agreed_sending_hours),
        METRIC_EPCIS_FAILED: epcis_failed_metric(epcis_counts),
    }


# ---------------------------------------------------------------------------
# Database (SELECT only)
# ---------------------------------------------------------------------------

_RECORD_ROWS_SQL = text(
    """
    SELECT e.id AS record_id,
           e.facility_id,
           e.cte_type,
           e.kde_data,
           e.event_time,
           e.created_at,
           l.tlc_code AS lot_code
      FROM supplier_cte_events e
      JOIN supplier_traceability_lots l
        ON l.id = e.lot_id
       AND l.tenant_id = e.tenant_id
     WHERE e.tenant_id = CAST(:tid AS uuid)
       AND e.supplier_user_id = CAST(:uid AS uuid)
       AND e.facility_id = ANY(CAST(:fids AS uuid[]))
       AND e.created_at >= :since
     ORDER BY e.created_at DESC, e.id
    """
)

# One row per (active lot, record of that lot). A lot is active when the
# caller sent a record for it, at one of the requested facilities, in the
# window: the same record scope as _RECORD_ROWS_SQL, so another supplier's
# record on a shared lot cannot make it active. Linkage looks at all of the
# caller's records for it, any age.
_LOT_ROWS_SQL = text(
    """
    WITH active AS (
        SELECT DISTINCT l.id, l.tlc_code, l.facility_id
          FROM supplier_traceability_lots l
          JOIN supplier_cte_events w
            ON w.lot_id = l.id
           AND w.tenant_id = l.tenant_id
         WHERE l.tenant_id = CAST(:tid AS uuid)
           AND l.supplier_user_id = CAST(:uid AS uuid)
           AND l.facility_id = ANY(CAST(:fids AS uuid[]))
           AND w.supplier_user_id = CAST(:uid AS uuid)
           AND w.facility_id = ANY(CAST(:fids AS uuid[]))
           AND w.created_at >= :since
    )
    SELECT a.id AS lot_id,
           a.tlc_code AS lot_code,
           a.facility_id,
           e.cte_type,
           e.kde_data,
           EXISTS (
               SELECT 1
                 FROM fsma.transformation_links t
                WHERE t.tenant_id = CAST(:tid AS uuid)
                  AND t.output_tlc = a.tlc_code
           ) AS is_transformation_output
      FROM active a
      JOIN supplier_cte_events e
        ON e.lot_id = a.id
       AND e.tenant_id = CAST(:tid AS uuid)
       AND e.supplier_user_id = CAST(:uid AS uuid)
     ORDER BY a.tlc_code, a.id
    """
)


_SENDING_HOURS_SQL = text(
    """
    SELECT f.id AS facility_id,
           f.agreed_sending_hours
      FROM supplier_facilities f
     WHERE f.tenant_id = CAST(:tid AS uuid)
       AND f.supplier_user_id = CAST(:uid AS uuid)
       AND f.id = ANY(CAST(:fids AS uuid[]))
    """
)


def _params(tenant_id: str, supplier_user_id: str, facility_ids: Sequence[str], since: datetime) -> dict[str, Any]:
    return {"tid": tenant_id, "uid": supplier_user_id, "fids": list(facility_ids), "since": since}


def fetch_record_rows(
    db_session: Any, tenant_id: str, supplier_user_id: str, facility_ids: Sequence[str], since: datetime
) -> list[dict[str, Any]]:
    if not facility_ids:
        return []
    result = db_session.execute(_RECORD_ROWS_SQL, _params(tenant_id, supplier_user_id, facility_ids, since))
    return [dict(row) for row in result.mappings().all()]


def fetch_lot_rows(
    db_session: Any, tenant_id: str, supplier_user_id: str, facility_ids: Sequence[str], since: datetime
) -> list[dict[str, Any]]:
    if not facility_ids:
        return []
    result = db_session.execute(_LOT_ROWS_SQL, _params(tenant_id, supplier_user_id, facility_ids, since))
    return [dict(row) for row in result.mappings().all()]


def fetch_sending_hours(
    db_session: Any, tenant_id: str, supplier_user_id: str, facility_ids: Sequence[str]
) -> dict[str, Optional[int]]:
    """Agreed sending hours per facility id; None where none is set."""
    if not facility_ids:
        return {}
    result = db_session.execute(
        _SENDING_HOURS_SQL, {"tid": tenant_id, "uid": supplier_user_id, "fids": list(facility_ids)}
    )
    return {str(row["facility_id"]): row["agreed_sending_hours"] for row in result.mappings().all()}


def _by_facility(rows: Sequence[Mapping[str, Any]], facility_ids: Sequence[str]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {key: [] for key in facility_ids}
    for row in rows:
        grouped.setdefault(str(row["facility_id"]), []).append(row)
    return grouped


def fetch_supplier_quality(
    db_session: Any,
    tenant_id: str,
    supplier_user_id: str,
    facility_ids: Sequence[str],
    since: datetime,
    sending_hours: Optional[Mapping[str, Optional[int]]] = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Per facility metrics for ``facility_ids`` (every id is present).

    ``sending_hours`` is fetched when the caller has not already done so.
    """
    if not facility_ids:
        return {}
    records = _by_facility(
        fetch_record_rows(db_session, tenant_id, supplier_user_id, facility_ids, since), facility_ids
    )
    lots = _by_facility(fetch_lot_rows(db_session, tenant_id, supplier_user_id, facility_ids, since), facility_ids)
    epcis_counts = fetch_receipt_counts(db_session, tenant_id, since)
    hours = (
        sending_hours
        if sending_hours is not None
        else fetch_sending_hours(db_session, tenant_id, supplier_user_id, facility_ids)
    )
    return {
        key: summarize_facility(records[key], lots[key], hours.get(key), epcis_counts)
        for key in facility_ids
    }
