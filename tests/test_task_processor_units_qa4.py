"""QA deep-pass: task-processor pure units (no database, no threads).

Covers server/workers/task_processor.py heartbeat cadence derivation,
retry backoff math, handler registration, and the empty-payload early exit
of the NLP handler. Database-backed claim/complete/fail paths need Postgres
and are not covered here. Fast and deterministic.
"""

from __future__ import annotations

import pytest

from server.workers import task_processor
from server.workers.task_processor import (
    DEFAULT_TIMEOUT_SECONDS,
    TASK_HANDLERS,
    TASK_TIMEOUTS_SECONDS,
    _handle_nlp_extraction,
    _heartbeat_interval_for,
    _retry_delay_seconds,
)


@pytest.mark.parametrize(
    ("timeout", "expected"),
    [
        (300, 75),
        (120, 30),
        (30, 7),
        (5, 1),
        (1, 1),
        (4, 1),
    ],
)
def test_heartbeat_interval_is_quarter_window_floored_at_one(timeout, expected):
    assert _heartbeat_interval_for(timeout) == expected


@pytest.mark.parametrize("bad", [0, -30])
def test_heartbeat_interval_rejects_non_positive_timeout(bad):
    with pytest.raises(ValueError, match="positive number of seconds"):
        _heartbeat_interval_for(bad)


def test_heartbeat_interval_always_lands_before_expiry():
    # The extension must land before the visibility window expires. The
    # quarter-window target in _heartbeat_interval_for gives two beats of
    # margin for production-sized windows; tiny windows keep the 1s floor.
    for timeout in (2, 3, 30, 120, 300):
        assert 0 < _heartbeat_interval_for(timeout) < timeout


def test_every_registered_task_type_has_a_heartbeat_safe_timeout():
    for task_type in TASK_HANDLERS:
        timeout = TASK_TIMEOUTS_SECONDS.get(task_type, DEFAULT_TIMEOUT_SECONDS)
        assert 0 < _heartbeat_interval_for(timeout) < timeout / 2


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        (1, 60),
        (2, 120),
        (3, 240),
        (4, 480),
        (10, 3600),
        (100, 3600),
    ],
)
def test_retry_backoff_doubles_with_hour_cap(attempts, expected):
    assert _retry_delay_seconds(attempts) == expected


def test_retry_backoff_floors_at_first_retry_for_bad_input():
    assert _retry_delay_seconds(0) == 60
    assert _retry_delay_seconds(-5) == 60


def test_retry_backoff_honors_custom_cap():
    assert _retry_delay_seconds(10, cap_seconds=100) == 100


def test_registered_handlers_cover_expected_task_types():
    assert set(TASK_HANDLERS) == {"nlp_extraction", "review_item"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": "some text without an id"},
        {"document_id": "doc-1"},
        {"document_id": "", "text": ""},
    ],
)
def test_nlp_handler_skips_empty_payload_without_raising(payload):
    assert _handle_nlp_extraction(dict(payload)) is None


def test_module_defaults_are_sane():
    assert task_processor.POLL_INTERVAL > 0
    assert task_processor.LOCK_TIMEOUT_MINUTES > 0
    assert task_processor.SHUTDOWN_TIMEOUT_SECONDS > 0
    assert task_processor.HEARTBEAT_INTERVAL_SECONDS > 0
