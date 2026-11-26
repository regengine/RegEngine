"""FSMA-event detection for extraction payloads.

Split out of the retired ``dlq`` module (WI-05, 2026-11-04): the dead-letter
producers were Kafka-only, but the FTL-flag walk below is pure and still
decides whether an event is in FSMA 204 scope.
"""

from __future__ import annotations


def _is_fsma_event(evt: dict) -> bool:
    """Does this event relate to FSMA traceability?

    Three-layer signal (#1116):

    1. **Explicit FTL classification** — if the extractor stamped
       ``is_ftl_covered`` on any KDE (set by ``_classify_ftl`` against
       the shared FTL catalog), trust that directly. ``True`` means
       the product is on the FTL and the event is in scope; ``False``
       means a verified non-FTL food. This is the reliable signal.
    2. **URL / doc-id substring** — legacy heuristic kept as a
       fallback for events where extraction failed or the extractor
       couldn't classify (``is_ftl_covered`` is ``None``).
    3. Otherwise default to non-FSMA.
    """
    ftl_flags = _collect_ftl_flags(evt)
    if True in ftl_flags:
        return True
    # Everything we found was explicitly False — trust that.
    if ftl_flags and False in ftl_flags and True not in ftl_flags:
        return False

    source = str(evt.get("source_url", ""))
    doc_id = str(evt.get("document_id", ""))
    return (
        "fsma" in source.lower()
        or "fsma" in doc_id.lower()
        or "204" in source
    )


def _collect_ftl_flags(evt: dict) -> list:
    """Walk an event payload and collect every ``is_ftl_covered`` flag
    the extractor may have set on KDEs / CTEs. Returns a list of the
    values seen (``True`` / ``False``) — ``None`` entries are skipped
    so they don't tip the caller's tri-state gate to False."""
    flags: list = []
    ctes = evt.get("ctes") or []
    if isinstance(ctes, list):
        for cte in ctes:
            kdes = (cte or {}).get("kdes") if isinstance(cte, dict) else None
            if isinstance(kdes, dict) and kdes.get("is_ftl_covered") is not None:
                flags.append(kdes["is_ftl_covered"])
    top_kdes = evt.get("kdes")
    if isinstance(top_kdes, dict) and top_kdes.get("is_ftl_covered") is not None:
        flags.append(top_kdes["is_ftl_covered"])
    return flags
