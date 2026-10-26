"""A date-rejected EDI interchange must not burn its ISA13.

Uses the repo's synthetic fixture ``tests/fixtures/edi_corpus/asn_856.edi``.
The rejected variant only moves the BSN ship date to 5 days after now; the
corrected resend is the unmodified fixture.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import (
    dedup as dedup_mod,  # noqa: E402
    rejection_log,  # noqa: E402
    router as edi_router,  # noqa: E402
)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE = service_dir / "tests" / "fixtures" / "edi_corpus" / "asn_856.edi"
FIXTURE_BSN = "BSN*00*ASN-12345*20260310*1200~"


class _NxStore:
    """Minimal SET NX semantics, matching how dedup uses Redis."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def get(self, key):
        return self.keys.get(key)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _NxStore:
    fake = _NxStore()
    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: fake)
    return fake


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.setattr(edi_routes, "_resolve_principal_tenant_id", lambda *args: "tenant-a")
    rejection_log.reset_edi_rejections()
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(key_id="", scopes=["edi.ingest"])
    with TestClient(app) as test_client:
        yield test_client


def _future_variant() -> bytes:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert FIXTURE_BSN in raw
    future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y%m%d")
    return raw.replace(FIXTURE_BSN, f"BSN*00*ASN-12345*{future}*1200~").encode()


def _post(client: TestClient, raw: bytes, route: str):
    return client.post(
        f"/api/v1/ingest/edi{route}",
        data={"traceability_lot_code": "ASN-12345"},
        files={"file": ("asn_856.edi", raw, "application/edi-x12")},
    )


@pytest.mark.parametrize("route", ["", "/document"])
def test_reject_then_corrected_resend_is_not_a_replay(client, store, route):
    rejected = _post(client, _future_variant(), route)
    assert rejected.status_code == 400
    detail = rejected.json()["detail"]
    assert detail["error"] == "edi_date_in_future"
    assert detail["needs_review"] is True
    assert store.keys == {}, "ISA13 must not be reserved by a date rejection"

    records = rejection_log.list_edi_rejections("tenant-a")
    assert [r["rejection_id"] for r in records] == [detail["rejection_id"]]
    assert records[0]["needs_review"] is True
    assert records[0]["reason"] == "edi_date_in_future"

    resend = _post(client, FIXTURE.read_bytes(), route)
    assert resend.status_code != 409, resend.json()
    assert len(store.keys) == 1, "corrected resend reserves the ISA13"

    replay = _post(client, FIXTURE.read_bytes(), route)
    assert replay.status_code == 409
    assert replay.json()["detail"]["error"] == "duplicate_interchange"


def test_missing_date_rejection_is_logged_for_review(client, store):
    raw = FIXTURE.read_text(encoding="utf-8").replace(FIXTURE_BSN, "BSN*00*ASN-12345**1200~")
    response = _post(client, raw.encode(), "/document")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "missing_edi_date"
    assert detail["needs_review"] is True
    record = rejection_log.list_edi_rejections("tenant-a")[0]
    assert record["rejection_id"] == detail["rejection_id"]
    assert record["needs_review"] is True
    assert store.keys == {}
