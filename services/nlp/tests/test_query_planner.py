from datetime import date

from services.nlp.app.query_planner import parse_query


def test_detects_trace_forward_with_lot():
    plan = parse_query("trace forward lot LOT-2026-001", today=date(2026, 3, 10))
    assert plan.intent == "trace_forward"
    assert plan.tlc == "LOT-2026-001"


def test_falls_back_to_event_search_when_lot_missing():
    plan = parse_query(
        "trace back lettuce from Supplier X in the last 30 days",
        today=date(2026, 3, 10),
    )
    assert plan.intent == "events_search"
    assert plan.product_contains == "lettuce"
    assert plan.facility_contains == "Supplier X"
    assert plan.start_date == "2026-02-08"
    assert plan.end_date == "2026-03-10"
    assert any("No traceability lot code found" in warning for warning in plan.warnings)


def test_extracts_events_search_filters_and_cte_type():
    plan = parse_query(
        "show me all lettuce from Supplier X in the last 30 days receiving",
        today=date(2026, 3, 10),
    )
    assert plan.intent == "events_search"
    assert plan.product_contains == "lettuce"
    assert plan.facility_contains == "Supplier X"
    assert plan.start_date == "2026-02-08"
    assert plan.end_date == "2026-03-10"
    assert plan.cte_type == "RECEIVING"


def test_detects_gaps_intent():
    plan = parse_query("show compliance gaps and missing KDEs")
    assert plan.intent == "compliance_gaps"


def test_detects_orphan_intent_and_days():
    plan = parse_query("find orphan lots in the last 45 days")
    assert plan.intent == "orphan_lots"
    assert plan.days_stagnant == 45
