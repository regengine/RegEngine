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
from app.webhook_models import EventResult, IngestResponse  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE = service_dir / "tests" / "fixtures" / "edi_corpus" / "asn_856.edi"
FIXTURE_BSN = "BSN*00*ASN-12345*20260310*1200~"
TENANT = "00000000-0000-0000-0000-000000000123"
OTHER_TENANT = "00000000-0000-0000-0000-000000000456"
# GTIN-14 + lot suffix, the FSMA 204 TLC format strict validation accepts
# (same value test_edi_wire_format_2974_2976_2978 uses).
VALID_TLC = "00012345678901-LOT001"
ALLOWLIST_ENV = "EDI_PARTNER_ALLOWLIST_" + TENANT.upper().replace("-", "_")


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

    def eval(self, script, numkeys, key, token):
        assert script == dedup_mod._RELEASE_IF_OWNER_LUA
        if self.keys.get(key) == token:
            del self.keys[key]
            return 1
        return 0


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _NxStore:
    fake = _NxStore()
    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: fake)
    return fake


@pytest.fixture()
def ingested(monkeypatch: pytest.MonkeyPatch) -> list:
    """Stub the canonical write; capture each accepted payload."""
    calls: list = []

    async def _fake_ingest_events(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
        calls.append(payload)
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id=f"evt-{idx}",
                    sha256_hash="hash",
                    chain_hash="chain",
                )
                for idx, event in enumerate(payload.events)
            ],
        )

    monkeypatch.setattr(edi_routes, "ingest_events", _fake_ingest_events)
    return calls


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, ingested: list) -> TestClient:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    rejection_log.reset_edi_rejections()
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], auth_mode="test"
    )
    with TestClient(app) as test_client:
        yield test_client


def _future_variant() -> bytes:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert FIXTURE_BSN in raw
    future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y%m%d")
    return raw.replace(FIXTURE_BSN, f"BSN*00*ASN-12345*{future}*1200~").encode()


def _post(client: TestClient, raw: bytes, route: str, tenant: str = TENANT):
    return client.post(
        f"/api/v1/ingest/edi{route}",
        data={
            "traceability_lot_code": VALID_TLC,
            "tenant_id": tenant,
            "tlc_source_reference": "0061414100001",
        },
        files={"file": ("asn_856.edi", raw, "application/edi-x12")},
    )


@pytest.mark.parametrize("route", ["", "/document"])
def test_reject_then_corrected_resend_is_accepted(client, store, ingested, route):
    rejected = _post(client, _future_variant(), route)
    assert rejected.status_code == 400
    detail = rejected.json()["detail"]
    assert detail["error"] == "edi_date_in_future"
    assert detail["needs_review"] is True
    assert store.keys == {}, "ISA13 must not be reserved by a date rejection"

    assert ingested == []
    records = rejection_log.list_edi_rejections(TENANT)
    assert [r["rejection_id"] for r in records] == [detail["rejection_id"]]
    assert records[0]["needs_review"] is True
    assert records[0]["reason"] == "edi_date_in_future"

    resend = _post(client, FIXTURE.read_bytes(), route)
    assert resend.status_code == 201, resend.json()
    assert resend.json()["ingestion_result"]["accepted"] == 1
    assert len(ingested) == 1
    event = ingested[0].events[0]
    assert event.traceability_lot_code == VALID_TLC
    assert event.timestamp.startswith("2026-03-10")
    assert len(store.keys) == 1, "corrected resend reserves the ISA13"

    replay = _post(client, FIXTURE.read_bytes(), route)
    assert replay.status_code == 409
    assert replay.json()["detail"]["error"] == "duplicate_interchange"
    assert len(ingested) == 1


def test_missing_date_rejection_is_logged_for_review(client, store):
    raw = FIXTURE.read_text(encoding="utf-8").replace(FIXTURE_BSN, "BSN*00*ASN-12345**1200~")
    response = _post(client, raw.encode(), "/document")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "missing_edi_date"
    assert detail["needs_review"] is True
    record = rejection_log.list_edi_rejections(TENANT)[0]
    assert record["rejection_id"] == detail["rejection_id"]
    assert record["needs_review"] is True
    assert store.keys == {}


@pytest.mark.parametrize("route", ["", "/document"])
def test_disallowed_sender_with_bad_date_gets_403_and_no_rejection(client, store, ingested, monkeypatch, route):
    monkeypatch.setenv(ALLOWLIST_ENV, "SOMEONEELSE")
    response = _post(client, _future_variant(), route)
    assert response.status_code == 403, response.json()
    assert response.json()["detail"]["error"] == "trading_partner_not_allowed"
    assert rejection_log.list_edi_rejections(TENANT) == []
    assert store.keys == {}
    assert ingested == []


@pytest.mark.parametrize("route", ["", "/document"])
def test_missing_quantity_is_rejected_before_isa13_reservation(client, store, ingested, route):
    """A zero SN1 quantity is rejected before the ISA13 is reserved."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "SN1**200*CA~" in raw
    rejected = _post(client, raw.replace("SN1**200*CA~", "SN1**0*CA~").encode(), route)
    assert rejected.status_code == 422, rejected.json()
    assert rejected.json()["detail"]["error"] == "edi_856_missing_required_kdes"
    assert "quantity" in rejected.json()["detail"]["missing_kdes"]
    assert store.keys == {}, "a preflight rejection must not reserve its ISA13"
    assert ingested == []

    resend = _post(client, FIXTURE.read_bytes(), route)
    assert resend.status_code == 201, resend.json()
    assert len(ingested) == 1


@pytest.mark.parametrize("route", ["", "/document"])
def test_ingest_failure_frees_isa13_for_retry(client, store, ingested, monkeypatch, route):
    """A server error during ingest must not turn the partner's retry into a 409."""
    working = edi_routes.ingest_events

    async def _broken(*args, **kwargs):
        raise RuntimeError("ingest blew up")

    monkeypatch.setattr(edi_routes, "ingest_events", _broken)
    with pytest.raises(RuntimeError, match="ingest blew up"):
        _post(client, FIXTURE.read_bytes(), route)
    assert store.keys == {}

    monkeypatch.setattr(edi_routes, "ingest_events", working)
    retry = _post(client, FIXTURE.read_bytes(), route)
    assert retry.status_code == 201, retry.json()
    assert len(ingested) == 1
    assert len(store.keys) == 1

    replay = _post(client, FIXTURE.read_bytes(), route)
    assert replay.status_code == 409


@pytest.mark.parametrize("route", ["", "/document"])
def test_all_events_rejected_frees_isa13(client, store, monkeypatch, route):
    """201 with accepted=0 stored nothing, so the corrected resend must not 409."""

    async def _rejecting(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
        return IngestResponse(
            accepted=0,
            rejected=len(payload.events),
            total=len(payload.events),
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=["Missing required KDE 'tlc_source_reference' for shipping CTE"],
                )
                for event in payload.events
            ],
        )

    monkeypatch.setattr(edi_routes, "ingest_events", _rejecting)
    first = _post(client, FIXTURE.read_bytes(), route)
    assert first.status_code == 201, first.json()
    assert first.json()["ingestion_result"]["accepted"] == 0
    assert store.keys == {}, "an all-rejected interchange must not burn its ISA13"


def _zero_quantity_variant() -> bytes:
    """Rejected only after the ISA13 step, as in the content-rejection test."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "SN1**200*CA~" in raw
    return raw.replace("SN1**200*CA~", "SN1**0*CA~").encode()


@pytest.mark.parametrize("route", ["", "/document"])
def test_failed_open_ingest_keeps_concurrent_claim(client, store, ingested, monkeypatch, route):
    """A failed-open Redis claim must not delete a concurrent request's claim."""

    def _claimed_elsewhere_then_timeout(key, value, nx=False, ex=None):
        store.keys[key] = "concurrent-retry"
        raise TimeoutError("redis timed out")

    async def _broken(*args, **kwargs):
        raise RuntimeError("ingest blew up")

    monkeypatch.setattr(store, "set", _claimed_elsewhere_then_timeout)
    monkeypatch.setattr(edi_routes, "ingest_events", _broken)
    with pytest.raises(RuntimeError, match="ingest blew up"):
        _post(client, FIXTURE.read_bytes(), route)
    assert list(store.keys.values()) == ["concurrent-retry"]


@pytest.mark.parametrize("route", ["", "/document"])
def test_rejection_frees_claim_when_set_landed_but_reply_was_lost(client, store, ingested, monkeypatch, route):
    """A claim landed despite a timeout and is released after ingest fails."""

    def _landed_then_timeout(key, value, nx=False, ex=None):
        store.keys[key] = value
        raise TimeoutError("redis timed out")

    async def _broken(*args, **kwargs):
        raise RuntimeError("ingest blew up")

    monkeypatch.setattr(store, "set", _landed_then_timeout)
    monkeypatch.setattr(edi_routes, "ingest_events", _broken)
    with pytest.raises(RuntimeError, match="ingest blew up"):
        _post(client, FIXTURE.read_bytes(), route)
    assert store.keys == {}


def test_release_is_a_noop_without_a_matching_token(store):
    dedup_mod.check_and_record_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-a")
    dedup_mod.release_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-b")
    assert list(store.keys.values()) == ["claim-a"]
    dedup_mod.release_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-a")
    assert store.keys == {}


@pytest.mark.parametrize("route", ["", "/document"])
def test_two_tenants_with_identical_envelope_ids_do_not_collide(client, store, ingested, route):
    """Same sender, receiver and ISA13 under another tenant is a new interchange."""
    first = _post(client, FIXTURE.read_bytes(), route, tenant=TENANT)
    assert first.status_code == 201, first.json()

    second = _post(client, FIXTURE.read_bytes(), route, tenant=OTHER_TENANT)
    assert second.status_code == 201, second.json()

    assert len(ingested) == 2
    assert len(store.keys) == 2


@pytest.mark.parametrize("route", ["", "/document"])
def test_true_replay_within_a_tenant_still_gets_409(client, store, ingested, route):
    first = _post(client, FIXTURE.read_bytes(), route)
    assert first.status_code == 201, first.json()

    replay = _post(client, FIXTURE.read_bytes(), route)
    assert replay.status_code == 409, replay.json()
    assert replay.json()["detail"]["error"] == "duplicate_interchange"
    assert len(ingested) == 1
    assert len(store.keys) == 1


@pytest.mark.parametrize("route", ["", "/document"])
def test_one_tenants_failure_leaves_the_other_tenants_claim(client, store, ingested, monkeypatch, route):
    """Releasing one tenant's failed claim leaves the other tenant's claim."""
    stored = _post(client, FIXTURE.read_bytes(), route, tenant=TENANT)
    assert stored.status_code == 201, stored.json()

    async def _broken(*args, **kwargs):
        raise RuntimeError("ingest blew up")

    working = edi_routes.ingest_events
    monkeypatch.setattr(edi_routes, "ingest_events", _broken)
    with pytest.raises(RuntimeError, match="ingest blew up"):
        _post(client, FIXTURE.read_bytes(), route, tenant=OTHER_TENANT)
    monkeypatch.setattr(edi_routes, "ingest_events", working)
    replay = _post(client, FIXTURE.read_bytes(), route, tenant=TENANT)
    assert replay.status_code == 409, replay.json()
