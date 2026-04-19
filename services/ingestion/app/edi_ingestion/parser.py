from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import HTTPException

from .constants import _SUPPORTED_TRANSACTION_SETS

logger = logging.getLogger("edi-ingestion")


# ── Prometheus metrics (#1171) ─────────────────────────────────────────────
# The cap itself blocks the OOM vector; the metrics make it observable in
# prod. Without a histogram, an SRE can't tell whether a cap bump is driven
# by hostile payloads or legitimate partner growth.
try:  # pragma: no cover - metrics are best-effort; never break parse on registry error
    from prometheus_client import REGISTRY, Counter, Histogram

    def _matches_registered_name(collector_name: str, requested: str) -> bool:
        """Prometheus strips ``_total`` from Counter names internally, so
        a Counter requested as ``foo_total`` ends up with ``_name='foo'``.
        Compare both forms so the fallback-lookup works regardless of
        which suffix is present in either string."""
        if not collector_name:
            return False
        a = collector_name[:-6] if collector_name.endswith("_total") else collector_name
        b = requested[:-6] if requested.endswith("_total") else requested
        return a == b

    def _get_or_create_counter(name, documentation, labelnames):
        try:
            return Counter(name, documentation, labelnames)
        except ValueError:
            # Already registered (common during pytest re-imports or
            # multi-path imports — e.g. app.edi_ingestion.parser vs
            # edi_ingestion.parser).
            for collector in list(REGISTRY._collector_to_names):
                if _matches_registered_name(
                    getattr(collector, "_name", None), name
                ):
                    return collector
            raise

    def _get_or_create_histogram(name, documentation, labelnames, buckets):
        try:
            return Histogram(name, documentation, labelnames, buckets=buckets)
        except ValueError:
            for collector in list(REGISTRY._collector_to_names):
                if _matches_registered_name(
                    getattr(collector, "_name", None), name
                ):
                    return collector
            raise

    EDI_SEGMENT_COUNT = _get_or_create_histogram(
        "edi_segment_count",
        "Number of X12 segments in a parsed EDI envelope",
        ["transaction_set"],
        # Buckets chosen to span typical partner volumes (tens/hundreds) up
        # through the cap (100k default). If most buckets stay empty, shrink.
        buckets=(10, 50, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000),
    )
    EDI_SEGMENT_CAP_REJECTED = _get_or_create_counter(
        "edi_segment_cap_rejected_total",
        "Parses rejected because segment count exceeded EDI_MAX_SEGMENTS (DoS guard #1171)",
        ["transaction_set"],
    )
    _METRICS_ENABLED = True
except Exception as _metrics_exc:  # pragma: no cover
    logger.debug("edi_metrics_init_failed: %s", _metrics_exc)
    EDI_SEGMENT_COUNT = None
    EDI_SEGMENT_CAP_REJECTED = None
    _METRICS_ENABLED = False


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


def _peek_transaction_set(compact: str, element_sep: str, segment_term: str) -> str:
    """Best-effort peek at the ST01 transaction set BEFORE the full
    split runs. Used for metric labelling on cap-rejection (where we
    never produce a parsed segment list).

    Returns "unknown" on any failure — a metric label must never
    propagate an exception.
    """
    try:
        # Walk up to the first segment boundary after ISA/GS/ST — we
        # don't need to parse the whole envelope. In practice ST
        # appears in the first ~200 chars.
        head = compact[:2048]
        for chunk in head.split(segment_term):
            parts = chunk.strip().split(element_sep)
            if parts and parts[0].upper() == "ST" and len(parts) > 1:
                ts = parts[1].strip()
                if ts in _SUPPORTED_TRANSACTION_SETS:
                    return ts
                # Unknown ST value — still useful for alerting, but
                # bound the label cardinality.
                return "unsupported"
        return "unknown"
    except Exception:
        return "unknown"


def _parse_x12_segments(content: str) -> list[list[str]]:
    compact = content.replace("\n", "").replace("\r", "")
    element_sep = compact[3] if len(compact) > 3 and compact[3].strip() else "*"
    segment_term = compact[105] if len(compact) > 105 and compact[105].strip() else "~"
    raw_segments = compact.split(segment_term)

    cap = _max_segments()
    if len(raw_segments) > cap:
        ts_label = _peek_transaction_set(compact, element_sep, segment_term)
        logger.warning(
            "edi_segment_cap_exceeded count=%d cap=%d transaction_set=%s",
            len(raw_segments), cap, ts_label,
        )
        if _METRICS_ENABLED and EDI_SEGMENT_CAP_REJECTED is not None:
            try:
                EDI_SEGMENT_CAP_REJECTED.labels(transaction_set=ts_label).inc()
            except Exception:  # pragma: no cover
                pass
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

    # Emit segment-count metric on successful parse. Labelled by the
    # detected transaction set so SRE can see which partners drive
    # volume and tune the cap per transaction_set if needed.
    if _METRICS_ENABLED and EDI_SEGMENT_COUNT is not None:
        try:
            detected_ts = _detect_transaction_set(segments) or "unknown"
            EDI_SEGMENT_COUNT.labels(transaction_set=detected_ts).observe(len(segments))
        except Exception:  # pragma: no cover
            pass

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
