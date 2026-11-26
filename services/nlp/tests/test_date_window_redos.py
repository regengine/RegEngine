"""Focused tests for the date-window parser regex hardening.

Regression for CodeQL py/polynomial-redos in ``_extract_date_window`` and
``_parse_human_date_prefix``. The rewritten regexes must stay linear on
adversarial input while producing identical results for normal queries.
"""

from __future__ import annotations

import time
from datetime import date

from services.nlp.app.query_planner import parse_query

TODAY = date(2026, 3, 10)


def test_between_window_parsed_with_trailing_filter():
    plan = parse_query(
        "show events between January 1, 2026 and February 2, 2026 for spinach",
        today=TODAY,
    )
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-02"
    assert plan.product_contains == "spinach"
    assert not any("defaulted to last 30 days" in w for w in plan.warnings)


def test_between_iso_dates():
    plan = parse_query("events between 2026-01-01 and 2026-02-02", today=TODAY)
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-02"


def test_between_reversed_dates_swap():
    plan = parse_query(
        "events between February 2, 2026 and January 1, 2026 for spinach",
        today=TODAY,
    )
    assert plan.start_date == "2026-01-01"
    assert plan.end_date == "2026-02-02"


def test_since_window_with_trailing_filter():
    plan = parse_query("show events since January 5, 2026 for spinach", today=TODAY)
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-03-10"


def test_since_window_with_long_trailing_word_preserves_date():
    # Regression: the capped trim regex ({1,128}) silently dropped the date
    # when the trailing filler word exceeded 128 chars, defaulting to the
    # 30-day window. The linear scan must strip trailing words of any length,
    # matching main's parsing semantics.
    query = "since January 5, 2026 for " + "x" * 130
    plan = parse_query(query, today=TODAY)
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-03-10"
    assert not any("defaulted to last 30 days" in w for w in plan.warnings)


def test_between_regex_is_linear_on_adversarial_input():
    # No " and " / no parseable date: previously quadratic/greedy backtracking.
    malicious = "events between " + "a " * 40000
    start = time.perf_counter()
    plan = parse_query(malicious, today=TODAY)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"parse_query took {elapsed:.3f}s on adversarial input"
    # With no parseable dates it falls back to the default 30-day window.
    assert plan.start_date == "2026-02-08"
    assert plan.end_date == "2026-03-10"


def test_date_prefix_trim_is_linear_on_long_trailing_run():
    # The previous input ("since " + "." * 40000) never reached the trim
    # logic: '.' is outside the ``since`` capture class, so the capture was
    # empty and _parse_human_date_prefix was never invoked. Use a parseable
    # date followed by a huge trailing token run so the trim path actually
    # runs; the overlapping "[sep]+[token]+$" regex backtracked quadratically
    # on such input, while the linear scan stays well under a second.
    malicious = "show events since January 5, 2026 " + "x" * 200000
    start = time.perf_counter()
    plan = parse_query(malicious, today=TODAY)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"parse_query took {elapsed:.3f}s on long trailing run"
    # The trailing filler is stripped and the explicit date is preserved.
    assert plan.start_date == "2026-01-05"
    assert plan.end_date == "2026-03-10"
