"""Recall contact-list CSV row builder.

``GET /fsma/compliance/export/recall-contacts/{tlc}`` lists every downstream
facility that took custody of the traced lot, for notification during a
recall. It used to write ``""`` for Date Received, ``""`` for Quantity
Received and the literal ``PENDING`` for Contact Status on every row, so the
file asserted a notification status nothing in the system tracks and left the
two columns a recall coordinator most needs permanently blank.

The receiving record exists: ``TraceResult.trace_rows`` (see
:mod:`services.graph.app.fsma.tracer`) carries one ``{lot, event, facility}``
entry per lot–event edge the graph records, with the event's own
``OCCURRED_AT`` facility. Two rules, the same as :mod:`trace_csv`:

* **One row per observed receipt.** A facility with a RECEIVING (or first
  land-based receiving) event on a traced lot gets one row per such receipt,
  carrying that lot, that event's date, and the lot's quantity and unit.
* **Never borrow.** A facility the trace reached without a receiving event
  (for example only via a ``SHIPPED_TO`` edge) still belongs on the list, with
  the lot, date, quantity and unit cells blank. When the tracer supplied no
  associations at all, every facility row is blank; nothing is inferred from
  the flat ``events`` and ``lots`` lists.

Contact Status is always blank. RegEngine records no notification outcomes,
so the column is the recall coordinator's to fill in, not the system's to
assert.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.fsma_validation import gln_for_export

from .safe_text import csv_safe

__all__ = ["RECALL_CONTACTS_HEADER", "RECEIVING_EVENT_TYPES", "build_recall_contacts_rows"]


RECALL_CONTACTS_HEADER: List[str] = [
    "Facility Name",
    "Global Location Number (GLN)",
    "Address",
    "Facility Type",
    "Traceability Lot Code",
    "Date Received",
    "Quantity Received",
    "Unit of Measure",
    "Contact Status",
]

# Event types that record a facility taking custody of a lot.
RECEIVING_EVENT_TYPES = frozenset({"RECEIVING", "FIRST_LAND_BASED_RECEIVING"})


def _facility_key(facility: Dict[str, Any]) -> Any:
    gln = facility.get("gln")
    if gln:
        return ("gln", str(gln))
    return ("name", facility.get("name"), facility.get("address"))


def _row(
    facility: Dict[str, Any],
    lot: Optional[Dict[str, Any]],
    event: Optional[Dict[str, Any]],
) -> List[str]:
    """Build one CSV row. Unknown cells are blank — never inherited."""
    lot = lot or {}
    event = event or {}
    return [
        csv_safe(facility.get("name") or ""),
        csv_safe(gln_for_export(facility.get("gln"))),
        csv_safe(facility.get("address") or ""),
        csv_safe(facility.get("facility_type") or ""),
        csv_safe(lot.get("tlc") or ""),
        csv_safe(event.get("event_date") or ""),
        csv_safe(lot.get("quantity") if lot.get("quantity") is not None else ""),
        csv_safe(lot.get("unit_of_measure") or ""),
        "",  # Contact Status: no notification outcome is recorded anywhere.
    ]


def build_recall_contacts_rows(result: Any) -> List[List[str]]:
    """Return the CSV data rows (header excluded) for a forward trace.

    Args:
        result: a ``TraceResult`` (or anything exposing ``facilities`` and
            optionally ``trace_rows``).

    Returns:
        A list of rows aligned to :data:`RECALL_CONTACTS_HEADER`.
    """
    facilities: List[Dict[str, Any]] = list(getattr(result, "facilities", None) or [])
    trace_rows = getattr(result, "trace_rows", None)

    # ``facility_type`` lives on the traversal's facility nodes, not on the
    # association's facility dict; look it up by GLN, never guess it.
    by_key: Dict[Any, Dict[str, Any]] = {}
    for facility in facilities:
        if not isinstance(facility, dict):
            continue
        by_key.setdefault(_facility_key(facility), facility)

    rows: List[List[str]] = []
    received_at: set = set()

    for association in trace_rows or []:
        if not isinstance(association, dict):
            continue
        event = association.get("event") or {}
        if not isinstance(event, dict):
            event = {}
        facility = association.get("facility")
        if not isinstance(facility, dict) or not facility:
            continue
        if str(event.get("type") or "").upper() not in RECEIVING_EVENT_TYPES:
            continue
        key = _facility_key(facility)
        known = by_key.get(key)
        merged = dict(facility)
        if known is not None:
            for field in ("name", "address", "facility_type"):
                if not merged.get(field) and known.get(field):
                    merged[field] = known[field]
        lot = association.get("lot")
        if not isinstance(lot, dict):
            lot = None
        rows.append(_row(merged, lot, event))
        received_at.add(key)

    # Facilities the trace reached without a receiving event on record stay
    # on the notification list with the receipt cells blank.
    for facility in facilities:
        if not isinstance(facility, dict):
            continue
        if _facility_key(facility) not in received_at:
            rows.append(_row(facility, None, None))

    return rows
