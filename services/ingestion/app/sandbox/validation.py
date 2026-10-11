"""
Sandbox validation — KDE validation, duplicate lot detection, entity
name normalization and mismatch detection.

Moved from sandbox_router.py.
"""

from __future__ import annotations

import math
import re
import string
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from ..webhook_models import (
    REQUIRED_KDES_BY_CTE,
    WebhookCTEType,
)

# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------


def _validate_kdes(event: Dict[str, Any]) -> List[str]:
    """Validate required KDEs for a raw event dict."""
    errors: List[str] = []
    cte_type_str = event.get("cte_type", "")

    try:
        cte_type = WebhookCTEType(cte_type_str)
    except ValueError:
        valid_types = [t.value for t in WebhookCTEType]
        return [f"Invalid CTE type '{cte_type_str}'. Valid types: {', '.join(valid_types)}"]

    required = REQUIRED_KDES_BY_CTE.get(cte_type, [])
    kdes = event.get("kdes", {})

    available = {
        "traceability_lot_code": event.get("traceability_lot_code"),
        "product_description": event.get("product_description"),
        "quantity": event.get("quantity"),
        "unit_of_measure": event.get("unit_of_measure"),
        "location_name": event.get("location_name"),
        "location_gln": event.get("location_gln"),
        **kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {cte_type_str} CTE")

    # A present-but-garbage quantity would otherwise be skipped silently by
    # mass balance and score a false pass. Flag it so the event cannot
    # come back compliant.
    qty = available.get("quantity")
    if qty is not None and not (isinstance(qty, str) and qty.strip() == ""):
        if isinstance(qty, bool):
            errors.append(f"Quantity '{qty}' is not a number, mass balance cannot be evaluated")
        else:
            try:
                qty_num = float(qty)
            except (TypeError, ValueError):
                qty_num = None
            if qty_num is None or not math.isfinite(qty_num):
                errors.append(f"Quantity '{qty}' is not a number, mass balance cannot be evaluated")

    # Same for timestamps: an unparseable value would be skipped silently
    # by the chronology check. Flag it instead of guessing an order.
    ts = event.get("timestamp")
    if isinstance(ts, str) and ts.strip():
        try:
            datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"Invalid ISO 8601 timestamp '{ts}', chronology cannot be evaluated")

    return errors


# ---------------------------------------------------------------------------
# Duplicate Lot Detection
# ---------------------------------------------------------------------------


def _detect_duplicate_lots(events: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """
    Detect duplicate traceability lot codes within the same CTE type.

    Uses (TLC, CTE type, reference_document) as the uniqueness key so that
    split shipments with different BOL/invoice numbers are NOT flagged as
    duplicates. Only flags when both TLC + CTE + ref_doc match exactly.

    Returns a mapping of event_index -> list of warning strings for the second
    and subsequent occurrences.
    """
    seen: Dict[tuple, int] = {}
    warnings: Dict[int, List[str]] = {}

    for i, event in enumerate(events):
        tlc = (event.get("traceability_lot_code") or "").strip().lower()
        cte = (event.get("cte_type") or "").strip().lower()
        if not tlc or not cte:
            continue

        # Include reference_document in key to allow split shipments
        kdes = event.get("kdes", {})
        ref_doc = (kdes.get("reference_document") or event.get("reference_document") or "").strip().lower()

        key = (tlc, cte, ref_doc)
        if key in seen:
            first_index = seen[key]
            original_tlc = (event.get("traceability_lot_code") or "").strip()
            original_cte = (event.get("cte_type") or "").strip()
            msg = f"Duplicate lot code '{original_tlc}' for CTE type '{original_cte}'"
            if ref_doc:
                msg += f" with same reference document"
            msg += f" \u2014 row may be redundant (see event {first_index})"
            warnings.setdefault(i, []).append(msg)
        else:
            seen[key] = i

    return warnings


# ---------------------------------------------------------------------------
# Entity Resolution Warnings
# ---------------------------------------------------------------------------

# Suffixes to strip during normalization (longer/more specific first)
_ENTITY_SUFFIXES = [
    "incorporated",
    "corporation",
    "limited",
    "company",
    "l.l.c.",
    "l.l.p.",
    "l.p.",
    "corp.",
    "inc.",
    "ltd.",
    "co.",
    "llc",
    "llp",
    "corp",
    "inc",
    "ltd",
    "co",
    "lp",
]

# Compiled pattern: match any suffix at end of string (preceded by whitespace or comma)
_SUFFIX_PATTERN = re.compile(
    r"[,\s]+(?:" + "|".join(re.escape(s) for s in _ENTITY_SUFFIXES) + r")\s*$",
    re.IGNORECASE,
)

# Fields to inspect explicitly
_ENTITY_FIELDS_EXPLICIT = {
    "location_name",
    "ship_from_location",
    "ship_to_location",
    "receiving_location",
    "from_entity_reference",
    "immediate_previous_source",
}

# Substrings that mark a field as entity-like
_ENTITY_FIELD_MARKERS = {"location", "entity", "source", "facility"}

# Maximum pairwise mismatch warnings per evaluation. Pair counts grow
# quadratically with near-identical names, so the remainder is reported
# as a single overflow note.
_ENTITY_WARNING_CAP = 100


def _is_entity_field(field_name: str) -> bool:
    """Return True if *field_name* is an entity-like field."""
    lower = field_name.lower()
    if lower in _ENTITY_FIELDS_EXPLICIT:
        return True
    return any(marker in lower for marker in _ENTITY_FIELD_MARKERS)


def _normalize_entity_name(name: str) -> str:
    """Normalize an entity name for comparison."""
    norm = name.lower().strip()
    # Strip common business-entity suffixes
    norm = _SUFFIX_PATTERN.sub("", norm)
    # Strip punctuation
    norm = norm.translate(str.maketrans("", "", string.punctuation))
    # Collapse internal whitespace
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _detect_entity_mismatches(events: List[Dict[str, Any]]) -> List[str]:
    """
    Scan all events for entity-like field values that normalize to the same
    string but differ in their original form.  Returns a list of warning
    strings, one per mismatched pair.
    """
    # normalized_form -> set of original values
    groups: Dict[str, set] = defaultdict(set)

    for event in events:
        # Top-level fields
        for field, value in event.items():
            if _is_entity_field(field) and isinstance(value, str) and value.strip():
                groups[_normalize_entity_name(value)].add(value.strip())

        # Nested kdes dict
        kdes = event.get("kdes", {})
        if isinstance(kdes, dict):
            for field, value in kdes.items():
                if _is_entity_field(field) and isinstance(value, str) and value.strip():
                    groups[_normalize_entity_name(value)].add(value.strip())

    # Cap the output: near-identical names across hundreds of events would
    # otherwise produce a quadratic number of warnings and a megabyte-scale
    # response from a public endpoint. Report the first batch, then an
    # overflow note with the omitted count.
    match_groups = [(norm, sorted(originals)) for norm, originals in sorted(groups.items()) if len(originals) >= 2]
    total_pairs = sum(len(originals) * (len(originals) - 1) // 2 for _, originals in match_groups)

    warnings: List[str] = []
    for _norm, sorted_originals in match_groups:
        for i in range(len(sorted_originals)):
            for j in range(i + 1, len(sorted_originals)):
                if len(warnings) >= _ENTITY_WARNING_CAP:
                    break
                warnings.append(
                    f"Possible entity mismatch: '{sorted_originals[i]}' and "
                    f"'{sorted_originals[j]}' may refer to the same entity "
                    f"\u2014 consider standardizing"
                )
            if len(warnings) >= _ENTITY_WARNING_CAP:
                break
        if len(warnings) >= _ENTITY_WARNING_CAP:
            break
    if total_pairs > len(warnings):
        warnings.append(
            f"{total_pairs - len(warnings)} more possible entity matches omitted, "
            f"standardize entity names to review them all"
        )
    return warnings
