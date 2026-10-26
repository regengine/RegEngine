"""Checks that EDI ingest time stays out of hashed KDEs, and the
timestamp/event_date mismatch check. Dates are built relative to now; the
only input file is the repo's synthetic fixture edi_corpus/asn_856.edi.
No database."""

from __future__ import annotations

import importlib.util
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
repo_root = service_dir.parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.edi_ingestion.utils import _ship_timestamp_and_date  # noqa: E402
from shared.cte_persistence.hashing import compute_idempotency_key  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_edi_event_time_mismatch", repo_root / "scripts" / "check_edi_event_time_mismatch.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

UTC = timezone.utc


FIXTURE = service_dir / "tests" / "fixtures" / "edi_corpus" / "asn_856.edi"


def _fixture_event():
    """Build the 856 event from the repo's synthetic fixture, as /document does."""
    segments = _parse_x12_segments(FIXTURE.read_text(encoding="utf-8"))
    extracted = _extract_fields_for_set("856", segments)
    header = {k: v for k, v in extracted.items() if k != "line_items"}
    merged = {**header, **extracted["line_items"][0], "edi_line_index": 1}
    return edi_routes._build_ingest_event_for_set(
        "856", merged, extracted["asn_number"], None, None, None, None, segments=segments
    )


def _key(event) -> str:
    return compute_idempotency_key(
        event.cte_type.value,
        event.traceability_lot_code,
        event.timestamp,
        "edi_inbound",
        dict(event.kdes),
        location_gln=event.location_gln,
        location_name=event.location_name,
    )


def test_same_document_same_idempotency_key():
    """A resend must hash the same, so backup dedupe works when Redis is down.

    Ingest time lives in the ``fsma.cte_events.ingested_at`` column, never in
    the hashed KDEs.
    """
    first = _fixture_event()
    time.sleep(0.01)
    second = _fixture_event()
    assert "edi_ingested_at" not in first.kdes
    assert first.kdes == second.kdes
    assert _key(first) == _key(second)


def test_routes_do_not_put_ingest_time_in_kdes():
    src = (service_dir / "app" / "edi_ingestion" / "routes.py").read_text()
    assert "edi_ingested_at" not in src


def test_backfilled_event_time_is_kept():
    real = datetime.now(UTC) - timedelta(days=200)
    timestamp, event_date = _ship_timestamp_and_date(real.strftime("%Y%m%d"), None)
    assert timestamp[:10] == event_date == real.date().isoformat()


def _day(offset_days: int) -> date:
    return (datetime.now(UTC) - timedelta(days=offset_days)).date()


def _at(d: date, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> datetime:
    start = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return start + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


@pytest.mark.parametrize(
    "days, hours, minutes, seconds, expected",
    [
        (0, 14, 30, 0, False),  # same day
        (1, 23, 0, 0, False),  # within a day after the day ends
        (-1, 1, 0, 0, False),  # within a day before the day starts
        (2, 0, 0, 1, True),  # just over a day after the day ends
        (-1, 0, -1, 0, True),  # just over a day before the day starts
        (200, 9, 0, 0, True),  # snapped to an ingest time months later
    ],
)
def test_is_mismatch(days, hours, minutes, seconds, expected):
    d = _day(200)
    assert check.is_mismatch(_at(d, days, hours, minutes, seconds), d) is expected


def test_count_mismatches_old_vs_new_behaviour():
    day = _day(200)
    ingest_now = datetime.now(UTC)
    real = _at(day, hours=14, minutes=30)
    assert check.count_mismatches([(ingest_now, day)] * 3) == 3  # snapped to ingest time
    assert check.count_mismatches([(real, day)] * 3) == 0  # real event time kept


def test_sql_is_read_only_count():
    sql = check.MISMATCH_SQL.upper()
    assert sql.lstrip().startswith("SELECT COUNT(DISTINCT E.ID)")
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
