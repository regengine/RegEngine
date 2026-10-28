"""Data-free checks that EDI event time is never replaced by ingest time.

Dates are constructed relative to now; no fixtures or records are used.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.edi_ingestion.utils import _ship_timestamp_and_date  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _ccyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def test_backfilled_date_keeps_real_event_time():
    real = datetime.now(timezone.utc) - timedelta(days=200)
    timestamp, event_date = _ship_timestamp_and_date(_ccyymmdd(real), "1430")
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.date() == real.date()
    assert (parsed.hour, parsed.minute) == (14, 30)
    assert event_date == real.date().isoformat()
    assert timestamp[:10] == event_date


def test_recent_date_unchanged():
    real = datetime.now(timezone.utc) - timedelta(days=3)
    timestamp, event_date = _ship_timestamp_and_date(_ccyymmdd(real), None)
    assert timestamp[:10] == event_date == real.date().isoformat()


def test_future_date_is_flagged_not_replaced():
    future = datetime.now(timezone.utc) + timedelta(days=5)
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date(_ccyymmdd(future), None)
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "edi_date_in_future"
    assert exc.value.detail["needs_review"] is True


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_date_is_rejected(raw):
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date(raw, None)
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "missing_edi_date"


def test_invalid_date_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _ship_timestamp_and_date("20261345", None)
    assert exc.value.detail["error"] == "invalid_edi_date"
