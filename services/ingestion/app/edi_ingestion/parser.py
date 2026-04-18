from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import HTTPException

from .constants import _SUPPORTED_TRANSACTION_SETS

logger = logging.getLogger("edi-ingestion")


def _max_segments() -> int:
    """Upper bound on parsed X12 segments (#1171). Default 100k, env
    override via ``EDI_MAX_SEGMENTS``.

    ``MAX_EDI_FILE_SIZE_BYTES`` caps the raw upload but not the
    expansion after ``split()``; a crafted envelope with millions of
    tiny segments could OOM the process before any validation runs.
    """
    try:
        return int(os.getenv("EDI_MAX_SEGMENTS", "100000"))
    except ValueError:
        return 100000


def _parse_x12_segments(content: str) -> list[list[str]]:
    compact = content.replace("\n", "").replace("\r", "")
    element_sep = compact[3] if len(compact) > 3 and compact[3].strip() else "*"
    segment_term = compact[105] if len(compact) > 105 and compact[105].strip() else "~"
    raw_segments = compact.split(segment_term)

    cap = _max_segments()
    if len(raw_segments) > cap:
        logger.warning(
            "edi_segment_cap_exceeded count=%d cap=%d",
            len(raw_segments), cap,
        )
        raise HTTPException(
            status_code=413,
            detail={
                "error": "segment_count_exceeded",
                "count": len(raw_segments),
                "cap": cap,
                "message": (
                    "EDI envelope exceeds the maximum parseable segment "
                    "count. Raise EDI_MAX_SEGMENTS if a legitimate "
                    "partner produces unusually large interchanges, or "
                    "split the file."
                ),
            },
        )

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
