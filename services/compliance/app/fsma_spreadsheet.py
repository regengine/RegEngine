"""
FSMA 204 FDA Sortable Spreadsheet Generator.

Produces a CSV matching the FDA 24-hour recall response format with all
mandatory Key Data Elements (KDEs) and Critical Tracking Event (CTE) columns
per FSMA Section 204 requirements.

Columns include: TLC, Product Description, Quantity, Unit of Measure,
Event Type (CTE), Event Date/Time, Origin/Destination GLN + Name + Address,
TLC Source GLN, TLC Source FDA Registration, Reference Document Type/Number,
named KDE date fields, Temperature, Carrier, Immediate Previous Source,
and overflow Additional KDEs as JSON.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from .csv_safety import sanitize_cell, sanitize_sequence

# Mandatory FDA 204 spreadsheet columns in required sort order
FDA_COLUMNS = [
    "event_type",
    "event_date",
    "event_time",
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "origin_gln",
    "origin_name",
    "origin_address",
    "destination_gln",
    "destination_name",
    "destination_address",
    "tlc_source_gln",
    "tlc_source_fda_reg",
    "reference_document_type",
    "reference_document_number",
    "harvest_date",
    "cooling_date",
    "pack_date",
    "ship_date",
    "receive_date",
    "transformation_date",
    "landing_date",
    "temperature",
    "carrier",
    "immediate_previous_source",
    "additional_kdes_json",
    "risk_flag",
]

# Friendly header labels for the CSV (1:1 with FDA_COLUMNS)
FDA_HEADERS = [
    "Event Type (CTE)",
    "Event Date",
    "Event Time",
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Origin GLN",
    "Origin Facility Name",
    "Origin Address",
    "Destination GLN",
    "Destination Facility Name",
    "Destination Address",
    "TLC Source GLN",
    "TLC Source FDA Registration",
    "Reference Document Type",
    "Reference Document Number",
    "Harvest Date",
    "Cooling Date",
    "Pack Date",
    "Ship Date",
    "Receive Date",
    "Transformation Date",
    "Landing Date",
    "Temperature",
    "Carrier",
    "Immediate Previous Source",
    "Additional KDEs (JSON)",
    "Risk Flag",
]

# Named KDE keys that get their own dedicated columns
_NAMED_KDE_KEYS = {
    "harvest_date",
    "cooling_date",
    "pack_date",
    "ship_date",
    "receive_date",
    "transformation_date",
    "landing_date",
    "temperature",
    "carrier",
    "immediate_previous_source",
}

# Keys already mapped into top-level columns (skip when building extra KDE JSON)
_SKIP_KDE_KEYS = _NAMED_KDE_KEYS | {
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "event_date",
    "event_time",
    "cte_type",
    "ship_from_gln",
    "ship_to_gln",
    "ship_from_location",
    "ship_to_location",
    "tlc_source_gln",
    "tlc_source_fda_reg",
    "reference_document_number",
    "reference_document_type",
    "location_identifier",
}


class FSMATimestampError(ValueError):
    """Raised when a required FSMA 204 timestamp is unparseable.

    An FDA Sortable Spreadsheet cannot use a truncated string as a
    substitute for a real date — the auditor-facing export must either
    carry a valid ISO-8601 date or fail loudly at export time. This is
    the regulator's contractual requirement, not a soft preference
    (issue #1108).
    """


class FSMAEventError(ValueError):
    """Raised when an event record has a shape the exporter cannot use.

    A single malformed record (a non-object event, or non-object
    ``kdes`` such as a stored string, number or list) must abort the
    export with a structured 400, never slip into an ``AttributeError``
    500 and never silently drop the record from an FDA submission.
    """


def _pick(*values: Any) -> str:
    """Return the first present value, coerced to ``str``.

    Only ``None`` and ``""`` count as missing. Falsy-but-real values
    such as ``0`` or ``False`` are kept: a zero quantity is a fact
    about the shipment, and exporting it as a blank cell rewrites that
    fact. Plain ``or``-chains cannot tell the two apart, which is why
    this helper exists.
    """
    for value in values:
        if value is None or value == "":
            continue
        return str(value)
    return ""


def _parse_timestamp(raw: str, *, strict: bool = False) -> tuple[str, str]:
    """Split an ISO timestamp into ``(date, time)``.

    Parameters
    ----------
    raw:
        An ISO-8601 string, possibly with a trailing ``Z``.
    strict:
        When ``True`` (the FDA-export path), a malformed ``raw`` raises
        :class:`FSMATimestampError` so the caller can return a 400
        rather than silently truncating to ``raw[:10]`` (issue #1108).
        When ``False`` (default, for non-regulatory code paths), the
        legacy graceful fallback is preserved so existing callers do
        not regress.
    """
    if raw is None or raw == "":
        return ("", "")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"))
    except (ValueError, AttributeError) as exc:
        if strict:
            raise FSMATimestampError(
                f"event_date {raw!r} is not ISO-8601; refusing to truncate into an FDA submission"
            ) from exc
        # Legacy, non-strict behavior: return raw[:10] for non-FDA
        # callers that only need a best-effort display value.
        return (str(raw)[:10], "")


def _is_recorded(value: Any) -> bool:
    """A KDE counts as recorded unless it is missing (None) or blank.

    A bare truthiness check drops legitimate zero measurements: a
    ``quantity`` of 0 and a ``temperature`` of 0 are routine real-world
    readings that must not render as blank on a regulator-facing export.
    """
    return value is not None and value != ""


def _first_recorded(*values: Any, default: str = "") -> Any:
    """Return the first recorded value, falling back to ``default``."""
    for value in values:
        if _is_recorded(value):
            return value
    return default


def _normalise_event(
    event: dict[str, Any],
    *,
    strict_dates: bool = False,
) -> dict[str, str]:
    """Map a graph-service event dict to FDA column values.

    Every returned string passes through :func:`sanitize_cell` so a
    tenant-controlled free-text KDE cannot carry a spreadsheet formula
    into the FDA auditor's CSV (issue #1272). This mirrors the
    ingestion-side fix (issue #1081).

    When ``strict_dates`` is True, a malformed ``event_date`` raises
    :class:`FSMATimestampError` rather than silently truncating into
    the CSV (issue #1108). FDA-export call paths must pass ``True``.

    A non-object ``event`` or non-object ``kdes`` raises
    :class:`FSMAEventError` so the export aborts loudly instead of
    crashing on ``AttributeError`` or dropping the record.
    """

    if not isinstance(event, dict):
        raise FSMAEventError(
            f"event record must be an object, got {type(event).__name__}; refusing to render it into an FDA submission"
        )
    kdes = event.get("kdes") or {}
    if not isinstance(kdes, dict):
        raise FSMAEventError(
            f"kdes must be an object, got {type(kdes).__name__}; refusing to render it into an FDA submission"
        )
    event_date_raw = _pick(kdes.get("event_date"), event.get("event_date"), event.get("event_timestamp"))
    event_date, event_time = _parse_timestamp(event_date_raw, strict=strict_dates)
    if _is_recorded(kdes.get("event_time")):
        event_time = str(kdes["event_time"])

    # Collect named KDE values. A present-but-falsy value (``0``,
    # ``False``) is still data, so presence means "not None and not
    # empty string", matching :func:`_pick`.
    kde_vals = {k: str(kdes.get(k, "")) for k in _NAMED_KDE_KEYS if kdes.get(k) is not None and kdes.get(k) != ""}

    # Extra KDEs -> JSON. Even a JSON-encoded string can begin with ``=``
    # once a spreadsheet renders it, so sanitize the serialized blob too.
    extra = {k: v for k, v in kdes.items() if k not in _SKIP_KDE_KEYS and v is not None and v != ""}
    extra_json = json.dumps(extra, default=str) if extra else ""

    row = {
        "event_type": _pick(event.get("type"), event.get("event_type")).upper(),
        "event_date": event_date,
        "event_time": event_time,
        "traceability_lot_code": _pick(event.get("tlc"), event.get("traceability_lot_code")),
        "product_description": _pick(event.get("product_description"), kdes.get("product_description")),
        "quantity": _pick(event.get("quantity"), kdes.get("quantity")),
        "unit_of_measure": _pick(event.get("uom"), event.get("unit_of_measure"), kdes.get("unit_of_measure")),
        "origin_gln": _pick(
            event.get("facility_gln"),
            event.get("location_gln"),
            kdes.get("ship_from_gln"),
        ),
        "origin_name": _pick(
            event.get("facility_name"),
            event.get("location_name"),
            kdes.get("ship_from_location"),
        ),
        "origin_address": _pick(event.get("facility_address"), event.get("ship_from_address")),
        "destination_gln": _pick(event.get("dest_gln"), kdes.get("ship_to_gln")),
        "destination_name": _pick(event.get("dest_name"), kdes.get("ship_to_location")),
        "destination_address": _pick(event.get("dest_address"), event.get("ship_to_address")),
        "tlc_source_gln": _pick(kdes.get("tlc_source_gln")),
        "tlc_source_fda_reg": _pick(kdes.get("tlc_source_fda_reg")),
        "reference_document_type": _pick(kdes.get("reference_document_type"), event.get("document_type")),
        "reference_document_number": _pick(kdes.get("reference_document_number"), event.get("ref_doc")),
        "harvest_date": kde_vals.get("harvest_date", ""),
        "cooling_date": kde_vals.get("cooling_date", ""),
        "pack_date": kde_vals.get("pack_date", ""),
        "ship_date": kde_vals.get("ship_date", ""),
        "receive_date": kde_vals.get("receive_date", ""),
        "transformation_date": kde_vals.get("transformation_date", ""),
        "landing_date": kde_vals.get("landing_date", ""),
        "temperature": kde_vals.get("temperature", ""),
        "carrier": kde_vals.get("carrier", ""),
        "immediate_previous_source": kde_vals.get("immediate_previous_source", ""),
        "additional_kdes_json": extra_json,
        "risk_flag": _pick(event.get("risk_flag")),
    }
    # Apply CSV-injection sanitization across the board.
    return {k: sanitize_cell(v) for k, v in row.items()}


def generate_fda_csv(
    events: list[dict[str, Any]],
    *,
    start_date: str = "",
    end_date: str = "",
    requesting_entity: str = "",
) -> str:
    """Generate a complete FDA 204 Sortable Spreadsheet as a CSV string.

    Parameters
    ----------
    events:
        List of event dicts (matching ``query_events_by_range()`` output).
    start_date:
        Start of the reporting window (ISO date).
    end_date:
        End of the reporting window (ISO date).
    requesting_entity:
        Name of the requesting entity (e.g. "FDA District Office").

    Returns
    -------
    str
        Complete CSV content ready for streaming to the client.
    """
    buf = io.StringIO()
    # QUOTE_ALL wraps every cell in double quotes. Combined with the
    # :func:`sanitize_cell` pass inside :func:`_normalise_event`, this
    # is a defense-in-depth posture against formula injection and
    # quoting-heuristic bypass (issue #1272).
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)

    # --- Metadata header rows ---
    # ``requesting_entity`` is a user-supplied URL query parameter and
    # ``start_date`` / ``end_date`` are also user-supplied; sanitize
    # each value before it lands in a spreadsheet cell.
    writer.writerow(sanitize_sequence(["FSMA Section 204 - Sortable Spreadsheet"]))
    writer.writerow(
        sanitize_sequence(
            [
                "Generated",
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            ]
        )
    )
    if start_date or end_date:
        writer.writerow(
            sanitize_sequence(
                [
                    "Date Range",
                    f"{start_date} to {end_date}",
                ]
            )
        )
    if requesting_entity:
        writer.writerow(
            sanitize_sequence(
                [
                    "Requesting Entity",
                    requesting_entity,
                ]
            )
        )
    writer.writerow(sanitize_sequence(["Record Count", str(len(events))]))
    writer.writerow([])  # blank separator

    # --- Column headers --- (static strings, but sanitize for symmetry)
    writer.writerow(sanitize_sequence(FDA_HEADERS))

    # --- Data rows (sorted by event_date then event_time) ---
    # ``_normalise_event`` already applies :func:`sanitize_cell` to every
    # value. We still re-wrap in :func:`sanitize_sequence` at the
    # ``writer.writerow`` boundary so the EPIC-L Semgrep rule (see
    # ``.semgrep.yml``) can statically verify the contract without
    # tracing into ``_normalise_event``.
    # ``strict_dates=True`` refuses to truncate malformed event_dates
    # into the FDA submission (issue #1108).
    normalised = [_normalise_event(e, strict_dates=True) for e in events]
    normalised.sort(key=lambda r: (r.get("event_date") or "", r.get("event_time") or ""))

    for row in normalised:
        writer.writerow(sanitize_sequence([row[col] for col in FDA_COLUMNS]))

    return buf.getvalue()
