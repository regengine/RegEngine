from __future__ import annotations

from typing import Optional

from .constants import _SUPPORTED_TRANSACTION_SETS


def _parse_x12_segments(content: str) -> list[list[str]]:
    compact = content.replace("\n", "").replace("\r", "")
    element_sep = compact[3] if len(compact) > 3 and compact[3].strip() else "*"
    segment_term = compact[105] if len(compact) > 105 and compact[105].strip() else "~"
    raw_segments = compact.split(segment_term)

    segments: list[list[str]] = []
    for segment in raw_segments:
        cleaned = segment.strip()
        if not cleaned:
            continue
        parts = [part.strip() for part in cleaned.split(element_sep)]
        if parts and parts[0]:
            segments.append(parts)
    return segments


def _segment_id_set(segments: list[list[str]]) -> set[str]:
    return {segment[0].upper() for segment in segments if segment}


def _first_segment(segments: list[list[str]], segment_id: str) -> Optional[list[str]]:
    wanted = segment_id.upper()
    for segment in segments:
        if segment and segment[0].upper() == wanted:
            return segment
    return None


def _detect_transaction_set(segments: list[list[str]]) -> str | None:
    """Detect the X12 transaction set from parsed segments."""
    st = _first_segment(segments, "ST")
    if st and len(st) > 1:
        ts = st[1].strip()
        if ts in _SUPPORTED_TRANSACTION_SETS:
            return ts
    return None
