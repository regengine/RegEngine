"""Rule-based NL query planner for traceability graph lookups.

This module intentionally avoids LLM calls in v1:
- deterministic intent extraction
- bounded parser logic for filters
- predictable confidence + warning output
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

IntentName = Literal[
    "trace_forward",
    "trace_backward",
    "lot_timeline",
    "events_search",
    "compliance_gaps",
    "orphan_lots",
]


class QueryPlan(BaseModel):
    """Structured plan produced from a natural-language query."""

    intent: IntentName
    tlc: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    product_contains: Optional[str] = None
    facility_contains: Optional[str] = None
    cte_type: Optional[str] = None
    days_stagnant: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)
    starting_after: Optional[str] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


_ORPHAN_KEYWORDS = ("orphan", "unlinked", "disconnected")
_GAP_KEYWORDS = ("gaps", "missing", "incomplete", "compliance issues")
_TIMELINE_KEYWORDS = ("timeline", "history of", "events for lot")
_FORWARD_KEYWORDS = ("trace forward", "downstream", "where did", "recall")
_BACKWARD_KEYWORDS = (
    "trace back",
    "trace backward",
    "where did",
    "come from",
    "source",
    "origin",
    "supplier",
)

_CTE_KEYWORDS: list[tuple[str, str]] = [
    (r"\breceiv(?:e|ing)\b", "RECEIVING"),
    (r"\bshipp?(?:ing|ed)?\b", "SHIPPING"),
    (r"\btransform(?:ation|ing|ed)?\b", "TRANSFORMATION"),
    (r"\bcreation\b", "CREATION"),
    (r"\binitial\s+packing\b", "INITIAL_PACKING"),
]


def parse_query(
    query: str,
    *,
    limit: int = 50,
    starting_after: Optional[str] = None,
    today: Optional[date] = None,
) -> QueryPlan:
    """Convert natural language into a deterministic query plan."""

    normalized = _normalize(query)
    lowered = normalized.lower()
    effective_today = today or datetime.now(timezone.utc).date()

    warnings: list[str] = []
    intent = _detect_intent(lowered)

    tlc = _extract_lot_code(normalized)
    start_date, end_date = _extract_date_window(lowered, effective_today)
    cte_type = _extract_cte_type(lowered)
    product_contains: Optional[str] = None
    facility_contains: Optional[str] = None
    days_stagnant: Optional[int] = None

    if intent in {"trace_forward", "trace_backward", "lot_timeline"} and not tlc:
        warnings.append(
            "No traceability lot code found; running a filtered event search instead."
        )
        intent = "events_search"

    if intent == "events_search":
        if not start_date or not end_date:
            default_start = effective_today - timedelta(days=30)
            start_date = default_start.isoformat()
            end_date = effective_today.isoformat()
            warnings.append("No explicit date range found; defaulted to last 30 days.")
        product_contains = _extract_product_phrase(normalized)
        facility_contains = _extract_facility_phrase(normalized)
    elif intent == "orphan_lots":
        days_stagnant = _extract_last_n_days(lowered) or 30

    confidence = _estimate_confidence(
        intent=intent,
        tlc=tlc,
        start_date=start_date,
        end_date=end_date,
        product_contains=product_contains,
        facility_contains=facility_contains,
        warnings=warnings,
    )

    return QueryPlan(
        intent=intent,
        tlc=tlc,
        start_date=start_date,
        end_date=end_date,
        product_contains=product_contains,
        facility_contains=facility_contains,
        cte_type=cte_type,
        days_stagnant=days_stagnant,
        limit=limit,
        starting_after=starting_after,
        confidence=confidence,
        warnings=warnings,
    )


def _normalize(query: str) -> str:
    return " ".join(query.strip().split())


def _detect_intent(lowered_query: str) -> IntentName:
    if _contains_any(lowered_query, _ORPHAN_KEYWORDS):
        return "orphan_lots"
    if _contains_any(lowered_query, _GAP_KEYWORDS):
        return "compliance_gaps"
    if _contains_any(lowered_query, _TIMELINE_KEYWORDS):
        return "lot_timeline"

    has_forward = _contains_any(lowered_query, _FORWARD_KEYWORDS) or (
        "where did" in lowered_query and " go" in lowered_query
    )
    has_backward = _contains_any(lowered_query, _BACKWARD_KEYWORDS) or (
        "where did" in lowered_query and "come from" in lowered_query
    )

    if has_forward and not has_backward:
        return "trace_forward"
    if has_backward and not has_forward:
        return "trace_backward"
    if has_backward and has_forward:
        # Prefer backward when both appear because source-of-origin queries
        # are a common compliance ask.
        return "trace_backward"

    return "events_search"


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_lot_code(query: str) -> Optional[str]:
    lot_patterns = [
        r"\btlc[:\s]+(?P<lot>[A-Za-z0-9][A-Za-z0-9\-_.:/]{2,})",
        r"\blot(?:\s+code)?[:\s]+(?P<lot>[A-Za-z0-9][A-Za-z0-9\-_.:/]{2,})",
        r"\blot\s+#?(?P<lot>[A-Za-z0-9][A-Za-z0-9\-_.:/]{2,})",
    ]
    for pattern in lot_patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return _clean_capture(match.group("lot"))
    return None


def _extract_last_n_days(lowered_query: str) -> Optional[int]:
    match = re.search(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", lowered_query)
    if not match:
        return None
    value = int(match.group(1))
    return max(1, min(365, value))


def _extract_date_window(lowered_query: str, today: date) -> tuple[Optional[str], Optional[str]]:
    relative_days = _extract_last_n_days(lowered_query)
    if relative_days:
        return (today - timedelta(days=relative_days)).isoformat(), today.isoformat()

    explicit_since = re.search(r"\bsince\s+([A-Za-z0-9,\-\s]+)", lowered_query)
    if explicit_since:
        raw_token = _clean_capture(explicit_since.group(1))
        parsed = _parse_human_date(raw_token, today)
        if parsed:
            return parsed.isoformat(), today.isoformat()

    between = re.search(
        r"\bbetween\s+([A-Za-z0-9,\-\s]+)\s+and\s+([A-Za-z0-9,\-\s]+)",
        lowered_query,
    )
    if between:
        start_raw = _clean_capture(between.group(1))
        end_raw = _clean_capture(between.group(2))
        start_dt = _parse_human_date(start_raw, today)
        end_dt = _parse_human_date(end_raw, today)
        if start_dt and end_dt:
            if start_dt > end_dt:
                start_dt, end_dt = end_dt, start_dt
            return start_dt.isoformat(), end_dt.isoformat()

    return None, None


def _parse_human_date(raw_value: str, today: date) -> Optional[date]:
    value = raw_value.strip().lower().rstrip(".")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    patterns = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%B %d", "%b %d")
    for pattern in patterns:
        try:
            parsed = datetime.strptime(value, pattern).date()
            if "%Y" not in pattern:
                parsed = parsed.replace(year=today.year)
                if parsed > today:
                    parsed = parsed.replace(year=today.year - 1)
            return parsed
        except ValueError:
            continue
    return None


def _extract_cte_type(lowered_query: str) -> Optional[str]:
    for pattern, cte_type in _CTE_KEYWORDS:
        if re.search(pattern, lowered_query):
            return cte_type
    return None


def _extract_product_phrase(query: str) -> Optional[str]:
    trace_pattern = re.search(
        r"\btrace\s+(?:back|backward|forward)\s+(?P<product>[A-Za-z0-9][A-Za-z0-9\s&\-\./]{1,90})\s+from\b",
        query,
        flags=re.IGNORECASE,
    )
    if trace_pattern:
        candidate = _clean_capture(trace_pattern.group("product"))
        # "trace back lot LOT-..." should not be treated as product text.
        if not candidate.lower().startswith("lot "):
            return candidate

    quoted = re.search(
        r'\b(?:all|show me all|find|events for|for)\s+"(?P<product>[^"]{2,80})"',
        query,
        flags=re.IGNORECASE,
    )
    if quoted:
        return _clean_capture(quoted.group("product"))

    plain = re.search(
        r"\b(?:all|show me all|find|events for|for)\s+(?P<product>[A-Za-z0-9][A-Za-z0-9\s&\-\./]{1,90})",
        query,
        flags=re.IGNORECASE,
    )
    if not plain:
        return None

    return _truncate_at_stops(
        plain.group("product"),
        stop_tokens=(" from ", " at ", " since ", " last ", " in the last ", " between ", ","),
    )


def _extract_facility_phrase(query: str) -> Optional[str]:
    quoted = re.search(r'\bfrom\s+"(?P<facility>[^"]{2,80})"', query, flags=re.IGNORECASE)
    if quoted:
        return _clean_capture(quoted.group("facility"))

    plain = re.search(
        r"\bfrom\s+(?P<facility>[A-Za-z0-9][A-Za-z0-9\s&\-\./]{1,90})",
        query,
        flags=re.IGNORECASE,
    )
    if not plain:
        return None

    return _truncate_at_stops(
        plain.group("facility"),
        stop_tokens=(" in the last ", " last ", " since ", " between ", " with ", ","),
    )


def _truncate_at_stops(raw_value: str, *, stop_tokens: tuple[str, ...]) -> Optional[str]:
    lowered = raw_value.lower()
    cut_idx = len(raw_value)
    for token in stop_tokens:
        idx = lowered.find(token)
        if idx >= 0:
            cut_idx = min(cut_idx, idx)
    cleaned = _clean_capture(raw_value[:cut_idx])
    return cleaned or None


def _clean_capture(value: str) -> str:
    return value.strip().strip(",.;:()[]{}")


def _estimate_confidence(
    *,
    intent: IntentName,
    tlc: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    product_contains: Optional[str],
    facility_contains: Optional[str],
    warnings: list[str],
) -> float:
    base = {
        "trace_forward": 0.88,
        "trace_backward": 0.88,
        "lot_timeline": 0.9,
        "events_search": 0.72,
        "compliance_gaps": 0.84,
        "orphan_lots": 0.84,
    }[intent]

    if tlc:
        base += 0.04
    if start_date and end_date:
        base += 0.03
    if product_contains:
        base += 0.03
    if facility_contains:
        base += 0.03

    base -= 0.08 * len(warnings)
    return max(0.2, min(0.99, round(base, 2)))
