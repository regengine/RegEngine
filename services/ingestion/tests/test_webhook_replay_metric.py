"""Regression tests for the replay-window Prometheus metric (#1245).

The replay-window check itself (``_validate_event_timestamp_window``)
is covered by ``test_webhook_hmac_and_replay.py``. This file locks in
the observability half: an SRE needs a time-series that distinguishes
partner-clock-skew from a replay attack.

Metric:
- ``webhook_replay_rejected_total{reason, age_bucket}`` — counter.

``reason``      : ``stale`` / ``future`` / ``unparseable``.
``age_bucket``  : bounded-cardinality bucket of how far off from now
                  the event timestamp is. ``na`` when unparseable.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("prometheus_client")

import app.webhook_router_v2 as wr  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _counter_value(counter, reason: str, age_bucket: str) -> float:
    """Sum the specific labelled sample value for
    ``webhook_replay_rejected_total{reason=..., age_bucket=...}``."""
    if counter is None:
        return 0.0
    for metric in counter.collect():
        for sample in metric.samples:
            if (
                sample.labels.get("reason") == reason
                and sample.labels.get("age_bucket") == age_bucket
            ):
                return sample.value
    return 0.0


# ── 1. Module-level metric presence ────────────────────────────────────────


def test_replay_metric_exists_on_module():
    """A refactor that accidentally removes or renames the counter
    would break SRE dashboards silently — this test fails loudly."""
    assert hasattr(wr, "WEBHOOK_REPLAY_REJECTED"), (
        "#1245: webhook_router_v2 must expose WEBHOOK_REPLAY_REJECTED counter"
    )
    assert hasattr(wr, "_WEBHOOK_METRICS_ENABLED")
    if wr._WEBHOOK_METRICS_ENABLED:
        assert wr.WEBHOOK_REPLAY_REJECTED is not None


# ── 2. Classifier correctness ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "timestamp,expected_reason,expected_bucket",
    [
        # Unparseable inputs
        ("not-a-date", "unparseable", "na"),
        ("", "unparseable", "na"),
        ("2026-13-45T99:99:99", "unparseable", "na"),
    ],
)
def test_classify_unparseable_inputs(timestamp, expected_reason, expected_bucket):
    reason, bucket = wr._classify_replay_rejection(timestamp)
    assert reason == expected_reason
    assert bucket == expected_bucket


def test_classify_future_window_buckets():
    """Future offsets land in one of 3 bounded buckets."""
    now = datetime.now(timezone.utc)

    # < 48h future
    ts = (now + timedelta(hours=25)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("future", "lt_48h")

    # < 30d future
    ts = (now + timedelta(days=15)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("future", "lt_30d")

    # >= 30d future
    ts = (now + timedelta(days=60)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("future", "gte_30d")


def test_classify_stale_window_buckets():
    """Stale offsets land in one of 3 bounded buckets."""
    now = datetime.now(timezone.utc)

    # Older than cap but < 180d
    ts = (now - timedelta(days=120)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("stale", "lt_180d")

    # < 1y
    ts = (now - timedelta(days=300)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("stale", "lt_1y")

    # >= 1y
    ts = (now - timedelta(days=500)).isoformat()
    assert wr._classify_replay_rejection(ts) == ("stale", "gte_1y")


# ── 3. Counter increments on rejection ─────────────────────────────────────


def test_record_replay_rejection_increments_stale():
    """Calling the recorder with a clearly-stale timestamp must
    increment the ``stale`` counter exactly once. 300 days lands in
    the ``lt_1y`` bucket (boundary: 180 < days <= 365)."""
    if not wr._WEBHOOK_METRICS_ENABLED:
        pytest.skip("prometheus_client not available")

    now = datetime.now(timezone.utc)
    stale_ts = (now - timedelta(days=300)).isoformat()

    before = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "stale", "lt_1y"
    )
    wr._record_replay_rejection(stale_ts)
    after = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "stale", "lt_1y"
    )
    assert after == before + 1, (
        f"#1245: recorder must increment stale/lt_1y bucket; "
        f"before={before} after={after}"
    )


def test_record_replay_rejection_increments_future():
    """A near-future rejection must land in ``future/lt_48h``."""
    if not wr._WEBHOOK_METRICS_ENABLED:
        pytest.skip("prometheus_client not available")

    now = datetime.now(timezone.utc)
    future_ts = (now + timedelta(hours=30)).isoformat()

    before = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "future", "lt_48h"
    )
    wr._record_replay_rejection(future_ts)
    after = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "future", "lt_48h"
    )
    assert after == before + 1


def test_record_replay_rejection_increments_unparseable():
    """Garbage input still increments (unparseable/na) so an SRE can
    see malformed-payload spikes."""
    if not wr._WEBHOOK_METRICS_ENABLED:
        pytest.skip("prometheus_client not available")

    before = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "unparseable", "na"
    )
    wr._record_replay_rejection("not-a-real-date")
    after = _counter_value(
        wr.WEBHOOK_REPLAY_REJECTED, "unparseable", "na"
    )
    assert after == before + 1


# ── 4. Safety / fallback paths ─────────────────────────────────────────────


def test_record_is_noop_when_metrics_disabled(monkeypatch):
    """If prometheus_client init failed at import time, the recorder
    must be a no-op rather than crashing the ingest path."""
    monkeypatch.setattr(wr, "_WEBHOOK_METRICS_ENABLED", False)
    # Must not raise, even with garbage input.
    wr._record_replay_rejection("not-a-date")
    wr._record_replay_rejection("")
    wr._record_replay_rejection(None)  # type: ignore[arg-type]


def test_classify_never_raises_on_hostile_input():
    """The classifier is on the rejection path — its input is by
    definition untrusted. It must NEVER raise; only return a pair of
    strings with bounded cardinality."""
    hostile = [
        None,
        "",
        "not-a-date",
        "2026-99-99T99:99:99Z",
        "\x00\x00\x00",
        "'; DROP TABLE events; --",
        "a" * 10_000,  # extreme length
    ]
    for ts in hostile:
        reason, bucket = wr._classify_replay_rejection(ts)  # type: ignore[arg-type]
        assert reason in {"stale", "future", "unparseable"}
        # age_bucket must be from a closed set to bound label cardinality
        assert bucket in {
            "lt_48h", "lt_30d", "gte_30d",
            "lt_180d", "lt_1y", "gte_1y",
            "na",
        }


# ── 5. Label-cardinality invariant ─────────────────────────────────────────


def test_label_cardinality_is_bounded():
    """The metric's label values MUST come from a closed set. This is
    enforced via the ``_classify_replay_rejection`` contract — drive a
    wide range of inputs and assert no leaks."""
    seen_reasons: set[str] = set()
    seen_buckets: set[str] = set()

    now = datetime.now(timezone.utc)
    sample_inputs = [
        # future
        (now + timedelta(hours=1)).isoformat(),
        (now + timedelta(hours=47)).isoformat(),
        (now + timedelta(days=29)).isoformat(),
        (now + timedelta(days=31)).isoformat(),
        (now + timedelta(days=400)).isoformat(),
        # stale
        (now - timedelta(days=91)).isoformat(),
        (now - timedelta(days=179)).isoformat(),
        (now - timedelta(days=181)).isoformat(),
        (now - timedelta(days=364)).isoformat(),
        (now - timedelta(days=366)).isoformat(),
        (now - timedelta(days=10_000)).isoformat(),
        # unparseable
        "", "garbage", "2026-99-99",
    ]

    for ts in sample_inputs:
        reason, bucket = wr._classify_replay_rejection(ts)
        seen_reasons.add(reason)
        seen_buckets.add(bucket)

    # All reasons must be in the closed set
    assert seen_reasons.issubset({"stale", "future", "unparseable"})
    # All buckets must be in the closed set
    assert seen_buckets.issubset({
        "lt_48h", "lt_30d", "gte_30d",
        "lt_180d", "lt_1y", "gte_1y",
        "na",
    })


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
