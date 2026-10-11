"""QA5: explicit since/between dates must survive trailing filter text.

``_extract_date_window`` captured everything after ``since`` (or each side
of ``between``) with a greedy ``([A-Za-z0-9,\\-\\s]+)`` group, so
"show events since January 5, 2026 for spinach" captured
"january 5, 2026 for spinach", which no date parser accepts. The dates
were silently discarded and the query fell back to the generic 30-day
default, answering a different question than the user asked.
"""

from __future__ import annotations

from datetime import date

from services.nlp.app.query_planner import parse_query

TODAY = date(2026, 3, 10)


def test_since_date_with_trailing_product_filter():
    plan = parse_query("show events since January 5, 2026 for spinach", today=TODAY)
    assert plan.intent == "events_search"
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-03-10"
    assert plan.product_contains == "spinach"
    assert not any("defaulted to last 30 days" in w for w in plan.warnings)


def test_between_dates_with_trailing_filter():
    plan = parse_query(
        "show events between January 1, 2026 and February 2, 2026 for spinach",
        today=TODAY,
    )
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-02"
    assert not any("defaulted to last 30 days" in w for w in plan.warnings)


def test_between_reversed_dates_still_swap_with_trailing_filter():
    plan = parse_query(
        "show events between February 2, 2026 and January 1, 2026 for spinach",
        today=TODAY,
    )
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-02"


def test_since_iso_date_with_trailing_filter():
    plan = parse_query("show events since 2026-01-05 for spinach", today=TODAY)
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-03-10"


def test_no_date_still_defaults_to_last_30_days():
    plan = parse_query("show me all lettuce from Supplier X", today=TODAY)
    assert plan.start_date == "2026-02-08"
    assert plan.end_date == "2026-03-10"
    assert any("defaulted to last 30 days" in w for w in plan.warnings)


def test_since_with_no_parseable_date_still_defaults():
    plan = parse_query("show events since harvest season for spinach", today=TODAY)
    assert plan.start_date == "2026-02-08"
    assert plan.end_date == "2026-03-10"
