"""Data-free checks for the separate EDI ingest-time field and the
timestamp/event_date mismatch check. No fixtures, records or database."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
repo_root = service_dir.parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.edi_ingestion.utils import _ingest_time_iso, _ship_timestamp_and_date  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_edi_event_time_mismatch", repo_root / "scripts" / "check_edi_event_time_mismatch.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

UTC = timezone.utc


def test_ingest_time_is_separate_from_backfilled_event_time():
    real = datetime.now(UTC) - timedelta(days=200)
    before = datetime.now(UTC)
    ingested = datetime.fromisoformat(_ingest_time_iso())
    timestamp, event_date = _ship_timestamp_and_date(real.strftime("%Y%m%d"), None)
    assert ingested >= before
    assert ingested.tzinfo is not None
    assert timestamp[:10] == event_date == real.date().isoformat()
    assert ingested.date() != date.fromisoformat(event_date)


def test_routes_store_ingest_time_kde():
    src = (service_dir / "app" / "edi_ingestion" / "routes.py").read_text()
    assert src.count('"edi_ingested_at"') >= 2


@pytest.mark.parametrize(
    "ts, d, expected",
    [
        (datetime(2026, 3, 1, 14, 30, tzinfo=UTC), date(2026, 3, 1), False),
        (datetime(2026, 3, 2, 23, 0, tzinfo=UTC), date(2026, 3, 1), False),
        (datetime(2026, 2, 28, 1, 0, tzinfo=UTC), date(2026, 3, 1), False),
        (datetime(2026, 3, 3, 0, 0, 1, tzinfo=UTC), date(2026, 3, 1), True),
        (datetime(2026, 2, 27, 23, 59, tzinfo=UTC), date(2026, 3, 1), True),
        (datetime(2026, 10, 25, 9, 0, tzinfo=UTC), date(2026, 4, 8), True),
    ],
)
def test_is_mismatch(ts, d, expected):
    assert check.is_mismatch(ts, d) is expected


def test_count_mismatches_old_vs_new_behaviour():
    day = date(2026, 4, 8)
    ingest_now = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    real = datetime(2026, 4, 8, 14, 30, tzinfo=UTC)
    assert check.count_mismatches([(ingest_now, day)] * 3) == 3  # snapped to ingest time
    assert check.count_mismatches([(real, day)] * 3) == 0  # real event time kept


def test_sql_is_read_only_count():
    sql = check.MISMATCH_SQL.upper()
    assert sql.lstrip().startswith("SELECT COUNT(*)")
    for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        assert verb not in sql


@pytest.mark.parametrize(
    "url, env, refused",
    [
        ("postgresql://u@localhost:5432/regengine_test", {}, False),
        ("postgresql://u@db.prod.example/regengine", {}, True),
        ("postgresql://u@localhost/regengine", {"REGENGINE_ENV": "production"}, True),
        ("postgresql://u@localhost/regengine", {"ENVIRONMENT": "Prod"}, True),
    ],
)
def test_refuses_production(url, env, refused):
    assert (check.refuse_production(url, env) is not None) is refused


def test_main_requires_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert check.main([]) == 2


def test_main_refuses_production_without_connecting(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    assert check.main(["--database-url", "postgresql://u@localhost/x"]) == 3


def test_r1_time_to_fix_reads_ingest_clocks_not_event_time():
    src = (repo_root / "services" / "shared" / "data_gap_tracking.py").read_text()
    sql_blocks = [b for b in src.split('text(\n    """')[1:]]
    assert sql_blocks
    for block in sql_blocks:
        body = block.split('"""')[0].lower()
        assert "event_timestamp" not in body
        assert "event_date" not in body
    assert "closed_at = GREATEST(now(), opened_at)" in src
