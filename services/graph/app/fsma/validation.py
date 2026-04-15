"""
FSMA 204 temporal validation wrapper.

Legacy wrapper around shared.fsma_rules.TimeArrowRule for backward
compatibility with tests.
"""

from __future__ import annotations

from shared.fsma_rules import TraceEvent as SharedTraceEvent, TimeArrowRule


def _validate_temporal_order(events: list) -> list:
    """
    Validate that events are in temporal order.

    Wrapper around shared.fsma_rules.TimeArrowRule for backward compatibility.

    Args:
        events: List of dicts with 'event_id' and 'event_date' keys.

    Returns:
        List of violation dicts (empty list if no violations).
    """
    from shared.fsma_rules import TraceEvent as SharedTraceEvent, TimeArrowRule

    trace_events = []
    for e in events:
        eid = e.get("event_id")
        edate = e.get("event_date")
        if eid and edate:
            try:
                trace_events.append(SharedTraceEvent(
                    event_id=eid,
                    tlc="N/A",
                    event_date=edate,
                    event_type=e.get("type"),
                ))
            except (ValueError, TypeError):
                continue

    if len(trace_events) < 2:
        return []

    rule = TimeArrowRule()
    result = rule.validate(trace_events)

    violations = []
    if not result.passed:
        for v in result.violations:
            details = v.details or {}
            violations.append({
                "violation_type": "TIME_ARROW",
                "description": v.description,
                "prev_event_id": v.event_ids[0] if v.event_ids else None,
                "curr_event_id": v.event_ids[1] if len(v.event_ids) > 1 else None,
                "prev_event_date": details.get("upstream_date"),
                "curr_event_date": details.get("downstream_date"),
            })

    return violations
