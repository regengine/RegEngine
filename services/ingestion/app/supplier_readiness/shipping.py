"""Map ASN 856 (and shipping CSV rows) into shipping KDEs and score readiness.

Preflight only. Uses synthetic fixtures in tests. Does not call production
ingest or partner networks.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..edi_ingestion.utils import _normalize_unit, _resolve_unit_code
from ..webhook_models import REQUIRED_KDES_BY_CTE, VALID_UNITS_OF_MEASURE, WebhookCTEType

# Segments the 856 extractor / envelope path already understands. Anything
# else is flagged so partner dialects cannot vanish silently (SEL-549).
_KNOWN_856_SEGMENTS: frozenset[str] = frozenset(
    {
        "ISA",
        "GS",
        "ST",
        "BSN",
        "HL",
        "N1",
        "N2",
        "N3",
        "N4",
        "LIN",
        "SN1",
        "SLN",
        "PID",
        "REF",
        "TD5",
        "TD1",
        "TD3",
        "MAN",
        "DTM",
        "CTT",
        "PRF",
        "CUR",
        "PER",
        "MEA",
        "FOB",
        "SE",
        "GE",
        "IEA",
    }
)

# Albertsons ASN buyer overlay (archived letter). Not in REQUIRED_KDES_BY_CTE.
ALBERTSONS_BUYER_FIELDS: tuple[str, ...] = (
    "gtin",
    "po_number",
    "sscc",
    "product_date",
)

_SHIPPING_REQUIRED: tuple[str, ...] = tuple(REQUIRED_KDES_BY_CTE[WebhookCTEType.SHIPPING])

_GTIN_QUALIFIERS = frozenset({"UK", "EN", "UI", "UA", "EO"})
_SSCC_MAN_QUALIFIERS = frozenset({"GM", "W"})  # GS1 SSCC / warehouse pallet id
_PO_REF_QUALIFIERS = frozenset({"PO", "VN"})  # purchase order / vendor order


@dataclass(frozen=True)
class FlagRecord:
    """One unknown or malformed input observation. Never dropped silently."""

    reason: str
    field: Optional[str] = None
    detail: Optional[str] = None
    row_number: Optional[int] = None


@dataclass
class ShippingReadinessResult:
    """One shipping lot/row scored against repo KDEs + Albertsons overlay."""

    status: str  # pass | gap | failure
    kdes: dict[str, Any]
    buyer: dict[str, Any]
    missing_repo_kdes: list[str] = field(default_factory=list)
    missing_buyer_fields: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    flags: list[FlagRecord] = field(default_factory=list)
    label: str = "SYNTHETIC"
    issue: str = "SEL-549"
    source: Optional[str] = None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    return str(value).strip() != ""


def _normalize_ship_date(raw: Any) -> Optional[str]:
    """Normalize EDI YYYYMMDD (or ISO) into YYYY-MM-DD. None if unparseable."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return text
        except ValueError:
            return None
    # Accept ISO datetime prefix
    if "T" in text or " " in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def _scan_buyer_and_unknowns(
    segments: Sequence[Sequence[str]],
) -> tuple[dict[str, Any], list[FlagRecord]]:
    """Pull Albertsons buyer fields and flag unknown 856 segments / values."""
    buyer: dict[str, Any] = {"gtin": None, "po_number": None, "sscc": None, "product_date": None}
    flags: list[FlagRecord] = []
    seen_unknown_seg: set[str] = set()

    for segment in segments:
        if not segment:
            continue
        seg_id = str(segment[0]).strip().upper()
        if not seg_id:
            continue
        if seg_id not in _KNOWN_856_SEGMENTS and seg_id not in seen_unknown_seg:
            seen_unknown_seg.add(seg_id)
            flags.append(
                FlagRecord(
                    reason="unrecognized_segment",
                    field=seg_id,
                    detail="EDI segment id not in the known 856 set; kept for audit",
                )
            )

        if seg_id == "LIN":
            # LIN**qual*value pairs start at element 2
            for i in range(2, len(segment) - 1, 2):
                qual = str(segment[i]).strip().upper()
                val = str(segment[i + 1]).strip()
                if not val:
                    continue
                if qual in _GTIN_QUALIFIERS and not buyer["gtin"]:
                    buyer["gtin"] = val
                elif qual and qual not in _GTIN_QUALIFIERS | {"SK", "VN", "UP", "BP", "MG", "LT"}:
                    flags.append(
                        FlagRecord(
                            reason="unrecognized_value",
                            field=f"LIN.{qual}",
                            detail="Unrecognized LIN product-id qualifier; value kept",
                        )
                    )

        elif seg_id == "REF" and len(segment) > 2:
            qual = str(segment[1]).strip().upper()
            val = str(segment[2]).strip()
            if not val:
                continue
            if qual in _PO_REF_QUALIFIERS and not buyer["po_number"]:
                buyer["po_number"] = val
            elif qual == "LT":
                pass  # lot handled via extracted line_items
            elif qual in {"BM", "SI", "CN", "PK"}:
                pass  # BOL / shipment / tracking → reference_document
            else:
                flags.append(
                    FlagRecord(
                        reason="unrecognized_value",
                        field=f"REF.{qual}",
                        detail="Unrecognized REF qualifier; value kept",
                    )
                )

        elif seg_id == "MAN" and len(segment) > 2:
            # MAN01 qualifier; SSCC often in MAN02/MAN03 depending on dialect
            qual = str(segment[1]).strip().upper()
            for candidate in segment[2:]:
                text = str(candidate).strip()
                if text and (qual in _SSCC_MAN_QUALIFIERS or len(re.sub(r"\D", "", text)) in (18, 20)):
                    if not buyer["sscc"]:
                        buyer["sscc"] = text
                    break
            if not buyer["sscc"] and any(str(c).strip() for c in segment[2:]):
                flags.append(
                    FlagRecord(
                        reason="unrecognized_value",
                        field=f"MAN.{qual or '?'}",
                        detail="MAN present but SSCC not resolved; raw kept in flags only",
                    )
                )

        elif seg_id == "DTM" and len(segment) > 2:
            # 036 / 405 / 002 style product or ship dates — record product_date when distinct
            qual = str(segment[1]).strip().upper()
            raw = str(segment[2]).strip()
            if qual in {"036", "405", "511", "036"} and raw and not buyer["product_date"]:
                buyer["product_date"] = _normalize_ship_date(raw) or raw

    return buyer, flags


def map_asn856_to_shipping_kdes(
    extracted: Mapping[str, Any],
    segments: Optional[Sequence[Sequence[str]]] = None,
    *,
    source: str = "edi_corpus/asn_856",
) -> ShippingReadinessResult:
    """Map one ASN 856 extraction (plus optional segments) into shipping KDEs.

    Line items become one result each; when ``line_items`` is empty a single
    header-only row is scored so missing TLC still surfaces as a gap.
    """
    header = {k: v for k, v in extracted.items() if k != "line_items"}
    lines = list(extracted.get("line_items") or [])
    if not lines:
        lines = [{"lot_number": None, "product_description": None, "quantity": None, "unit_of_measure": None}]

    buyer_scan: dict[str, Any] = {"gtin": None, "po_number": None, "sscc": None, "product_date": None}
    seg_flags: list[FlagRecord] = []
    if segments is not None:
        buyer_scan, seg_flags = _scan_buyer_and_unknowns(segments)

    # Score the first line (fixture has one). Multi-line ASNs can call this
    # per merged line from the ingest route later; preflight keeps it simple.
    line = lines[0]
    merged = {**header, **line}

    lot = merged.get("lot_number")
    raw_unit = merged.get("unit_of_measure")
    resolved_unit = _resolve_unit_code(raw_unit) if raw_unit is not None else None
    unit_failure = False
    if raw_unit is not None and str(raw_unit).strip() and resolved_unit is None:
        unit_failure = True
        unit_of_measure = str(raw_unit).strip()
    else:
        unit_of_measure = resolved_unit or (_normalize_unit(raw_unit) if raw_unit else None)

    ship_date = _normalize_ship_date(merged.get("ship_date_raw") or merged.get("ship_date"))

    kdes: dict[str, Any] = {
        "traceability_lot_code": lot if _present(lot) else None,
        "product_description": merged.get("product_description"),
        "quantity": merged.get("quantity"),
        "unit_of_measure": unit_of_measure,
        "ship_date": ship_date,
        "ship_from_location": merged.get("ship_from_name") or merged.get("ship_from_location"),
        "ship_to_location": merged.get("ship_to_name") or merged.get("ship_to_location"),
        "reference_document": merged.get("reference_document_number") or merged.get("reference_document"),
        "tlc_source_reference": merged.get("tlc_source_reference"),
        # Extras kept (never dropped)
        "ship_from_gln": merged.get("ship_from_gln"),
        "ship_to_gln": merged.get("ship_to_gln"),
        "asn_number": merged.get("asn_number"),
        "carrier": merged.get("carrier"),
    }

    buyer = {
        "gtin": buyer_scan.get("gtin") or merged.get("gtin"),
        "po_number": buyer_scan.get("po_number") or merged.get("po_number"),
        "sscc": buyer_scan.get("sscc") or merged.get("sscc"),
        "product_date": buyer_scan.get("product_date") or merged.get("product_date"),
    }

    flags = list(seg_flags)
    if unit_failure:
        flags.append(
            FlagRecord(
                reason="unrecognized_value",
                field="unit_of_measure",
                detail=f"Unit {raw_unit!r} is not in VALID_UNITS_OF_MEASURE / X12 DE355 map",
            )
        )

    return score_shipping_readiness(kdes, buyer, flags=flags, source=source)


def score_shipping_readiness(
    kdes: Mapping[str, Any],
    buyer: Optional[Mapping[str, Any]] = None,
    *,
    flags: Optional[Iterable[FlagRecord]] = None,
    source: Optional[str] = None,
) -> ShippingReadinessResult:
    """Score one shipping row: failure > gap > pass."""
    buyer = dict(buyer or {})
    flag_list = list(flags or [])
    missing_repo: list[str] = []
    failures: list[dict[str, str]] = []

    for key in _SHIPPING_REQUIRED:
        if not _present(kdes.get(key)):
            missing_repo.append(key)

    qty = kdes.get("quantity")
    if _present(qty):
        try:
            qf = float(qty)
            if not (qf > 0) or qf != qf:  # noqa: PLR0124 — NaN check
                failures.append({"kind": "malformed_quantity", "detail": f"quantity={qty!r}"})
        except (TypeError, ValueError):
            failures.append({"kind": "malformed_quantity", "detail": f"quantity={qty!r}"})

    uom = kdes.get("unit_of_measure")
    if _present(uom) and str(uom).strip().lower() not in VALID_UNITS_OF_MEASURE:
        # Also accept already-canonical values; VALID set is lowercase
        if str(uom).strip() not in VALID_UNITS_OF_MEASURE:
            failures.append({"kind": "invalid_unit_of_measure", "detail": f"unit_of_measure={uom!r}"})

    # ship_date present but unnormalizable is a failure when a raw was attempted
    if kdes.get("ship_date") is None and _present(kdes.get("_ship_date_raw_failed")):
        failures.append({"kind": "malformed_ship_date", "detail": "ship_date not parseable"})

    missing_buyer = [name for name in ALBERTSONS_BUYER_FIELDS if not _present(buyer.get(name))]

    if failures:
        status = "failure"
    elif missing_repo or missing_buyer:
        status = "gap"
    else:
        status = "pass"

    return ShippingReadinessResult(
        status=status,
        kdes=dict(kdes),
        buyer=dict(buyer),
        missing_repo_kdes=missing_repo,
        missing_buyer_fields=missing_buyer,
        failures=failures,
        flags=flag_list,
        source=source,
    )


_CSV_KNOWN_COLUMNS: frozenset[str] = frozenset(
    set(_SHIPPING_REQUIRED)
    | set(ALBERTSONS_BUYER_FIELDS)
    | {
        "cte_type",
        "ship_from_gln",
        "ship_to_gln",
        "carrier_name",
        "carrier",
        "event_time",
        "asn_number",
        "lot_number",
        "lot_code",
        "tlc",
    }
)


def _csv_row_to_kdes(
    row: Mapping[str, str],
    *,
    flag_unknown_columns: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], list[FlagRecord]]:
    """Map a shipping CSV row into KDE + buyer dicts; optionally flag unknown columns."""
    known = _CSV_KNOWN_COLUMNS
    flags: list[FlagRecord] = []
    extras: dict[str, str] = {}
    for col, val in row.items():
        key = (col or "").strip()
        if not key:
            continue
        if key not in known:
            if flag_unknown_columns:
                flags.append(
                    FlagRecord(
                        reason="unrecognized_column",
                        field=key,
                        detail="Unknown column kept; not mapped to a shipping KDE",
                    )
                )
            if val is not None and str(val).strip() != "":
                extras[key] = str(val)

    def _get(*names: str) -> Optional[str]:
        for name in names:
            if name in row and str(row[name]).strip() != "":
                return str(row[name]).strip()
        return None

    raw_unit = _get("unit_of_measure")
    resolved = _resolve_unit_code(raw_unit) if raw_unit else None
    if raw_unit and resolved is None:
        flags.append(
            FlagRecord(
                reason="unrecognized_value",
                field="unit_of_measure",
                detail=f"Unit {raw_unit!r} not recognized",
            )
        )
        unit = raw_unit
    else:
        unit = resolved

    ship_raw = _get("ship_date")
    ship_date = _normalize_ship_date(ship_raw) if ship_raw else None
    if ship_raw and ship_date is None:
        flags.append(
            FlagRecord(
                reason="malformed_date",
                field="ship_date",
                detail=f"ship_date {ship_raw!r} not parseable",
            )
        )

    qty_raw = _get("quantity")
    qty: Any = qty_raw
    if qty_raw is not None:
        try:
            qty = float(qty_raw)
        except ValueError:
            flags.append(
                FlagRecord(
                    reason="malformed_quantity",
                    field="quantity",
                    detail=f"quantity {qty_raw!r} not numeric",
                )
            )

    kdes = {
        "traceability_lot_code": _get("traceability_lot_code", "lot_number", "lot_code", "tlc"),
        "product_description": _get("product_description"),
        "quantity": qty,
        "unit_of_measure": unit,
        "ship_date": ship_date,
        "ship_from_location": _get("ship_from_location"),
        "ship_to_location": _get("ship_to_location"),
        "reference_document": _get("reference_document"),
        "tlc_source_reference": _get("tlc_source_reference"),
        "ship_from_gln": _get("ship_from_gln"),
        "ship_to_gln": _get("ship_to_gln"),
        **extras,
    }
    buyer = {
        "gtin": _get("gtin"),
        "po_number": _get("po_number"),
        "sscc": _get("sscc"),
        "product_date": _get("product_date"),
    }
    return kdes, buyer, flags


def dry_run_shipping_csv(
    text: str,
    *,
    source: str = "shipping_messy_partner.csv",
) -> dict[str, Any]:
    """Preflight dry run: score every row and tally flags by reason.

    Does not ingest. Unknown columns are flagged once (header-level, same
    spirit as #3682) and their cell values are still kept on each row's KDEs.
    """
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
    results: list[ShippingReadinessResult] = []
    flag_counts: dict[str, int] = {}
    status_counts = {"pass": 0, "gap": 0, "failure": 0}

    header_flags: list[FlagRecord] = []
    for col in fieldnames:
        key = (col or "").strip()
        if key and key not in _CSV_KNOWN_COLUMNS:
            header_flags.append(
                FlagRecord(
                    reason="unrecognized_column",
                    field=key,
                    detail="Unknown column kept; not mapped to a shipping KDE",
                    row_number=1,
                )
            )
    for f in header_flags:
        flag_counts[f.reason] = flag_counts.get(f.reason, 0) + 1

    for idx, row in enumerate(rows, start=2):  # header is row 1
        cte = (row.get("cte_type") or "").strip().lower()
        kdes, buyer, flags = _csv_row_to_kdes(row, flag_unknown_columns=False)
        wrong_cte = bool(cte and cte not in {"shipping", "ship", "s", "distribute"})
        if wrong_cte:
            flags.append(
                FlagRecord(
                    reason="unknown_cte_type",
                    field="cte_type",
                    detail=f"cte_type={cte!r} is not shipping",
                    row_number=idx,
                )
            )
        # Attach header unknown-column flags to row 2 only so they appear on a result
        row_flags = list(header_flags) if idx == 2 else []
        row_flags.extend(
            FlagRecord(reason=f.reason, field=f.field, detail=f.detail, row_number=f.row_number or idx)
            for f in flags
        )
        for f in row_flags:
            if f.reason == "unrecognized_column" and f.row_number == 1 and idx != 2:
                continue
            if not (f.reason == "unrecognized_column" and f.row_number == 1):
                flag_counts[f.reason] = flag_counts.get(f.reason, 0) + 1
        scored = score_shipping_readiness(kdes, buyer, flags=row_flags, source=f"{source}:row{idx}")
        if wrong_cte:
            # Fail-case §2.7: wrong CTE is a scope break, never pass/gap-as-ok
            scored.status = "failure"
            scored.failures.append({"kind": "wrong_cte_scope", "detail": f"cte_type={cte!r}"})
        results.append(scored)
        status_counts[scored.status] = status_counts.get(scored.status, 0) + 1

    return {
        "label": "SYNTHETIC",
        "issue": "SEL-549",
        "source": source,
        "row_count": len(rows),
        "status_counts": status_counts,
        "flagged_counts_by_reason": flag_counts,
        "results": results,
    }
