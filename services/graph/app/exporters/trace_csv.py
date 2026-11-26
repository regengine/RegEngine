"""FDA trace-CSV row builder (#2945).

``GET /fsma/compliance/export/trace/{tlc}`` advertises its output as the
sortable spreadsheet FSMA 204 describes, for submission to FDA during a
recall. It used to build rows like this::

    for lot in result.lots:
        # Find matching events for this lot
        for event in result.events:
            facility = next((f for f in result.facilities if f.get("gln")), {})

There is no join key between the two loops, so the writer emitted
``len(lots) * len(events)`` rows — each one asserting that this lot underwent
this event — and stamped every row with the *first* GLN-bearing facility in a
flat list regardless of where the event occurred. A trace of 6 lots and 20
events produced 120 rows all naming the same arbitrary facility. Handed to a
regulator that is worse than missing data: it asserts specific lots were
handled at specific locations on specific dates when the graph says otherwise,
and it inflates the apparent size of the affected population.

This module holds the row construction so it can be tested directly and shared
by every trace exporter. Two rules:

* **One row per observed association.** A row is emitted only for a (lot,
  event) pairing the graph actually records — ``TraceResult.trace_rows``.
* **Never borrow.** When an association or a facility is unknown, the cell is
  blank. An empty cell is a true statement about missing data; a neighbour's
  GLN is a false statement about a location.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from shared.fsma_validation import gln_for_export

from .safe_text import csv_safe

__all__ = ["TRACE_CSV_HEADER", "build_trace_csv_rows"]


TRACE_CSV_HEADER: List[str] = [
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Event Type",
    "Event Date",
    "Event Time",
    "Facility Name",
    "Facility GLN",
    "Facility Address",
    "Confidence Score",
]


def _row(
    lot: Optional[Dict[str, Any]],
    event: Optional[Dict[str, Any]],
    facility: Optional[Dict[str, Any]],
) -> List[str]:
    """Build one CSV row. Unknown cells are blank — never inherited."""
    lot = lot or {}
    event = event or {}
    facility = facility or {}
    return [
        csv_safe(lot.get("tlc", "")),
        csv_safe(lot.get("product_description", "")),
        csv_safe(lot.get("quantity", "")),
        csv_safe(lot.get("unit_of_measure", "")),
        csv_safe(event.get("type", "")),
        csv_safe(event.get("event_date", "")),
        csv_safe(event.get("event_time", "")),
        csv_safe(facility.get("name", "")),
        csv_safe(gln_for_export(facility.get("gln", ""))),
        csv_safe(facility.get("address", "")),
        csv_safe(event.get("confidence", "")),
    ]


def _dedup_lots(lots: Sequence[Any]) -> List[Dict[str, Any]]:
    seen: Dict[Any, Dict[str, Any]] = {}
    for lot in lots or []:
        if not isinstance(lot, dict):
            continue
        seen.setdefault(lot.get("tlc"), lot)
    return list(seen.values())


def build_trace_csv_rows(result: Any, tlc: str) -> List[List[str]]:
    """Return the CSV data rows (header excluded) for a trace result.

    Args:
        result: a ``TraceResult`` (or anything exposing ``lots``, ``events``,
            ``facilities`` and optionally ``trace_rows``).
        tlc: the traced lot code, used only when the trace returned events but
            no lot nodes at all.

    Returns:
        A list of rows aligned to :data:`TRACE_CSV_HEADER`. ``len()`` of the
        return value is the true row count — callers should log that rather
        than a computed estimate.
    """
    lots = _dedup_lots(getattr(result, "lots", None) or [])
    events = list(getattr(result, "events", None) or [])
    trace_rows = getattr(result, "trace_rows", None)

    rows: List[List[str]] = []

    associations = [row for row in (trace_rows or []) if isinstance(row, dict)]
    if trace_rows and associations:
        # Preferred path: the tracer preserved the real associations.
        # A non-dict entry is skipped. When every entry is unusable, fall
        # through to the degraded path instead of aborting the file.
        covered: set = set()
        for association in associations:
            lot = association.get("lot") or {}
            if not isinstance(lot, dict):
                lot = {}
            event = association.get("event")
            facility = association.get("facility")
            if not isinstance(event, dict):
                event = None
            if not isinstance(facility, dict):
                facility = None
            rows.append(_row(lot, event, facility))
            covered.add(lot.get("tlc"))
        # A lot the trace found but could not pair with an event still belongs
        # in the affected population. Emit it with the event cells blank.
        for lot in lots:
            if lot.get("tlc") not in covered:
                rows.append(_row(lot, None, None))
        return rows

    # Degraded path: the tracer supplied no associations (older contract, or
    # the association lookup failed). Emit one row per event, which is the
    # granularity FSMA 204's sortable spreadsheet is defined at, and leave the
    # lot and facility cells blank unless they are provably unambiguous.
    #
    # The lot is unambiguous only when the whole trace names exactly one lot;
    # otherwise every candidate is a guess, and #2945 is precisely the cost of
    # guessing. The facility is never resolvable from a flat list, so it is
    # always blank here.
    unambiguous_lot: Optional[Dict[str, Any]] = None
    if len(lots) == 1:
        unambiguous_lot = lots[0]
    elif not lots:
        unambiguous_lot = {"tlc": tlc}

    if events:
        return [_row(unambiguous_lot, event, None) for event in events]

    # No events at all: fall back to one row per lot so the affected lots are
    # still enumerated.
    return [_row(lot, None, None) for lot in lots]
