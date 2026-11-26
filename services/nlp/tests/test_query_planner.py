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


def test_between_date_window_still_parses():
    plan = parse_query("events between 2026-01-01 and 2026-01-31", today=date(2026, 3, 10))
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-01-31"


def test_between_with_trailing_and_filter_keeps_date_range():
    plan = parse_query(
        "between 2026-01-01 and 2026-02-01 and product spinach",
        today=date(2026, 3, 10),
    )
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-01"


def test_between_human_dates_with_trailing_and_filter():
    plan = parse_query(
        "events between january 5, 2026 and january 20, 2026 and lot abc",
        today=date(2026, 3, 10),
    )
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-01-20"


def test_long_query_is_not_truncated():
    import services.nlp.app.query_planner as qp

    assert not hasattr(qp, "MAX_QUERY_CHARS")
    padding = "x " * 400
    plan = parse_query(padding + "events between 2026-01-01 and 2026-01-31", today=date(2026, 3, 10))
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-01-31"


def test_long_between_query_is_fast():
    import time

    hostile = "between " + "a " * 50_000 + "!"
    started = time.monotonic()
    plan = parse_query(hostile, today=date(2026, 3, 10))
    assert time.monotonic() - started < 2.0
    assert plan.start_date == "2026-02-08"  # 30-day default


def test_many_and_separators_query_is_fast():
    import time

    hostile = "between " + "a and " * 20_000 + "!"
    started = time.monotonic()
    plan = parse_query(hostile, today=date(2026, 3, 10))
    assert time.monotonic() - started < 2.0
    assert plan.start_date == "2026-02-08"


def test_long_since_query_is_fast():
    import time

    hostile = "since " + "a " * 50_000 + "!"
    started = time.monotonic()
    parse_query(hostile, today=date(2026, 3, 10))
    assert time.monotonic() - started < 2.0
