"""Caps and skip reporting for the Sensitech TempTale CSV parser.

Regression tests for the audit finding: ``_parse_sensitech_csv`` used to
accumulate an unbounded ``readings`` list and skip malformed rows with a bare
``continue``, so callers never learned that data was dropped.

The parser now stops at ``MAX_SENSITECH_READINGS`` and reports both skipped
rows and truncation through ``_parse_sensitech_csv_with_stats`` and the
``rows_skipped`` / ``truncated`` fields of the import response.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

_services_dir = service_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

import app.sensitech_parser as sensitech_parser_module
from app.sensitech_parser import (
    MAX_SENSITECH_READINGS,
    _parse_sensitech_csv,
    _parse_sensitech_csv_with_stats,
    router as sensitech_router,
)
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse


def _csv_with_bad_rows() -> str:
    return (
        "Timestamp, Temperature (C), Alarm Status, Serial Number\n"
        "2026-02-26T08:00:00Z, 2.1, OK, ST-1\n"
        "2026-02-26T08:15:00Z, NOT_A_NUMBER, OK, ST-1\n"
        "2026-02-26T08:30:00Z\n"
        "2026-02-26T08:45:00Z, 3.0, OK, ST-1\n"
    )


def _csv_with_rows(n: int) -> str:
    lines = ["Timestamp, Temperature (C), Alarm Status, Serial Number"]
    for i in range(n):
        lines.append(f"2026-02-26T08:{i % 60:02d}:00Z, 2.0, OK, ST-1")
    return "\n".join(lines) + "\n"


class TestSkipReporting:
    def test_skipped_rows_are_counted_not_silent(self) -> None:
        result = _parse_sensitech_csv_with_stats(_csv_with_bad_rows())
        assert len(result.readings) == 2
        assert result.rows_skipped == 2
        assert result.truncated is False

    def test_clean_csv_reports_zero_skips(self) -> None:
        result = _parse_sensitech_csv_with_stats(_csv_with_rows(3))
        assert len(result.readings) == 3
        assert result.rows_skipped == 0
        assert result.truncated is False

    def test_legacy_wrapper_still_returns_readings_list(self) -> None:
        readings = _parse_sensitech_csv(_csv_with_bad_rows())
        assert len(readings) == 2


class TestReadingCap:
    def test_readings_capped_with_truncation_flag(self) -> None:
        result = _parse_sensitech_csv_with_stats(_csv_with_rows(10), max_readings=5)
        assert len(result.readings) == 5
        assert result.truncated is True

    def test_default_cap_is_positive_and_bounded(self) -> None:
        assert 0 < MAX_SENSITECH_READINGS <= 1_000_000

    def test_large_file_capped_at_default_max(self) -> None:
        result = _parse_sensitech_csv_with_stats(_csv_with_rows(MAX_SENSITECH_READINGS + 10))
        assert len(result.readings) == MAX_SENSITECH_READINGS
        assert result.truncated is True


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    app = FastAPI()
    app.include_router(sensitech_router)
    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant="tenant-sensitech-caps")

    async def _fake_ingest_events(
        payload: Any,
        *,
        principal_tenant_id: Any = None,
        x_regengine_api_key: Any = None,
    ) -> IngestResponse:
        captured_payload["payload"] = payload
        event = payload.events[0]
        return IngestResponse(
            accepted=1,
            rejected=0,
            total=1,
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id="evt-sensitech-caps",
                    sha256_hash="hash-caps",
                    chain_hash="chain-caps",
                )
            ],
        )

    monkeypatch.setattr(sensitech_parser_module, "ingest_events", _fake_ingest_events)

    with TestClient(app) as test_client:
        yield test_client


def test_endpoint_reports_skipped_rows(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/iot/sensitech",
        data={
            "traceability_lot_code": "LOT-CAPS-0001",
            "product_description": "Romaine Lettuce",
            "cte_type": "cooling",
            "location_name": "Metro DC Cold Room 1",
        },
        files={"file": ("temptale.csv", _csv_with_bad_rows().encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["readings_parsed"] == 2
    assert body["rows_skipped"] == 2
    assert body["truncated"] is False
