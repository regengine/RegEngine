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
from shared.error_handling import install_exception_handlers  # noqa: E402

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
        self.ttls: dict[str, int | None] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        self.ttls[key] = ex
        return True

    def get(self, key):
        return self.keys.get(key)

    def eval(self, script, numkeys, key, *args):
        if self.keys.get(key) != args[0]:
            return 0
        if script == dedup_mod._RELEASE_IF_OWNER_LUA:
            del self.keys[key]
            return 1
        assert script == dedup_mod._MARK_STORED_IF_OWNER_LUA
        self.keys[key] = args[1]
        self.ttls[key] = int(args[2])
        return 1


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


def _edi_app() -> FastAPI:
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], auth_mode="test"
    )
    return app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, ingested: list) -> TestClient:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    rejection_log.reset_edi_rejections()
    with TestClient(_edi_app()) as test_client:
        yield test_client


@pytest.fixture()
def production_client(client: TestClient) -> TestClient:
    """The same router behind the handlers both production apps install."""
    app = _edi_app()
    install_exception_handlers(app)
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
        data={"traceability_lot_code": VALID_TLC, "tenant_id": tenant},
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
def test_content_rejection_after_reservation_frees_isa13(client, store, ingested, route):
    """A zero SN1 quantity is rejected after the ISA13 is reserved."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "SN1**200*CA~" in raw
    rejected = _post(client, raw.replace("SN1**200*CA~", "SN1**0*CA~").encode(), route)
    assert 400 <= rejected.status_code < 500 and rejected.status_code != 409, rejected.json()
    assert store.keys == {}, "a rejected document must not burn its ISA13"
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
def test_failed_open_rejection_keeps_concurrent_claim(client, store, ingested, monkeypatch, route):
    """A request that never got the claim must not delete the retry's claim."""

    def _claimed_elsewhere_then_timeout(key, value, nx=False, ex=None):
        store.keys[key] = "concurrent-retry"
        raise TimeoutError("redis timed out")

    monkeypatch.setattr(store, "set", _claimed_elsewhere_then_timeout)
    rejected = _post(client, _zero_quantity_variant(), route)
    assert 400 <= rejected.status_code < 500 and rejected.status_code != 409, rejected.json()
    assert list(store.keys.values()) == ["concurrent-retry"]


@pytest.mark.parametrize("route", ["", "/document"])
def test_rejection_frees_claim_when_set_landed_but_reply_was_lost(client, store, ingested, monkeypatch, route):
    """SET applied server-side and the client timed out: the claim is still ours."""

    def _landed_then_timeout(key, value, nx=False, ex=None):
        store.keys[key] = value
        raise TimeoutError("redis timed out")

    monkeypatch.setattr(store, "set", _landed_then_timeout)
    rejected = _post(client, _zero_quantity_variant(), route)
    assert 400 <= rejected.status_code < 500 and rejected.status_code != 409, rejected.json()
    assert store.keys == {}


def test_release_is_a_noop_without_a_matching_token(store):
    dedup_mod.check_and_record_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-a")
    dedup_mod.release_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-b")
    assert list(store.keys.values()) == ["pending:claim-a"]
    dedup_mod.release_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-a")
    assert store.keys == {}


def test_mark_stored_is_a_noop_without_a_matching_token(store):
    dedup_mod.check_and_record_interchange("tenant", "sender", "receiver", "isa-13-1", "claim-a")
    dedup_mod.mark_interchange_stored("tenant", "sender", "receiver", "isa-13-1", "claim-b")
    assert list(store.keys.values()) == ["pending:claim-a"]


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
def test_one_tenants_rejection_leaves_the_other_tenants_claim(client, store, ingested, route):
    """Releasing a claim is scoped to the tenant that took it."""
    stored = _post(client, FIXTURE.read_bytes(), route, tenant=TENANT)
    assert stored.status_code == 201, stored.json()

    rejected = _post(client, _zero_quantity_variant(), route, tenant=OTHER_TENANT)
    assert 400 <= rejected.status_code < 500 and rejected.status_code != 409, rejected.json()

    replay = _post(client, FIXTURE.read_bytes(), route, tenant=TENANT)
    assert replay.status_code == 409, replay.json()


def _partial_ingest(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
    """One event stored, one rejected: the shape a multi-event interchange can return."""

    async def _result():
        return IngestResponse(accepted=1, rejected=1, total=2, events=[])

    return _result()


@pytest.mark.parametrize("route", ["", "/document"])
def test_partly_accepted_interchange_keeps_its_claim(client, store, ingested, monkeypatch, route):
    """Not released: event keys include line position, so a resend can double-store."""
    monkeypatch.setattr(edi_routes, "ingest_events", _partial_ingest)
    first = _post(client, FIXTURE.read_bytes(), route)
    assert first.status_code == 201, first.json()
    assert [value.split(":")[0] for value in store.keys.values()] == ["stored"]

    resend = _post(client, FIXTURE.read_bytes(), route)
    assert resend.status_code == 409, resend.json()


@pytest.mark.parametrize("route", ["", "/document"])
def test_claim_is_short_lived_until_events_are_stored(client, store, ingested, monkeypatch, route):
    """A worker killed mid-ingest must not leave a 7-day false 409 behind."""
    working = edi_routes.ingest_events
    during: list[tuple[str, int | None]] = []

    async def _observing(payload, **kwargs):
        key = next(iter(store.keys))
        during.append((store.keys[key], store.ttls[key]))
        return await working(payload, **kwargs)

    monkeypatch.setattr(edi_routes, "ingest_events", _observing)
    response = _post(client, FIXTURE.read_bytes(), route)
    assert response.status_code == 201, response.json()

    assert len(during) == 1
    value, ttl = during[0]
    assert value.startswith("pending:")
    assert ttl == dedup_mod._PENDING_TTL_SECONDS
    assert ttl < dedup_mod._DEDUP_TTL_SECONDS

    key = next(iter(store.keys))
    assert store.keys[key].startswith("stored:")
    assert store.ttls[key] == dedup_mod._DEDUP_TTL_SECONDS


def _seed_key(client, store, route: str, value: str) -> str:
    """Learn the key from a real post, then give it ``value``."""
    assert _post(client, FIXTURE.read_bytes(), route).status_code == 201
    key = next(iter(store.keys))
    store.keys[key] = value
    return key


@pytest.mark.parametrize("route", ["", "/document"])
def test_retransmit_during_in_flight_claim_is_told_to_retry(production_client, store, ingested, route):
    """An unfinished claim must not be reported as already processed."""
    key = _seed_key(production_client, store, route, "pending:other-request")

    retransmit = _post(production_client, FIXTURE.read_bytes(), route)
    assert retransmit.status_code == 503, retransmit.json()
    assert retransmit.headers["Retry-After"] == str(dedup_mod._IN_PROGRESS_RETRY_AFTER_SECONDS)
    error = retransmit.json()["error"]
    assert error["type"] == "http_503"
    assert "still being processed" in error["message"]
    assert "Retry-After" in error["message"]
    assert len(ingested) == 1
    assert store.keys[key] == "pending:other-request", "the retransmit must not touch the owner's claim"

    # The owner then fails and releases, and the partner's retry goes through.
    del store.keys[key]
    retry = _post(production_client, FIXTURE.read_bytes(), route)
    assert retry.status_code == 201, retry.json()
    assert len(ingested) == 2


@pytest.mark.parametrize("route", ["", "/document"])
def test_key_gone_between_set_and_get_is_retryable(production_client, store, ingested, monkeypatch, route):
    """SET NX lost to a claim that was released before the GET: nothing is known stored."""
    _seed_key(production_client, store, route, "pending:other-request")
    monkeypatch.setattr(store, "get", lambda key: None)

    response = _post(production_client, FIXTURE.read_bytes(), route)
    assert response.status_code == 503, response.json()
    assert "still being processed" in response.json()["error"]["message"]


@pytest.mark.parametrize("route", ["", "/document"])
def test_key_written_by_the_previous_format_counts_as_stored(client, store, ingested, route):
    """Keys live for up to 7 days across a deploy, and hold a bare token."""
    _seed_key(client, store, route, "f" * 32)

    replay = _post(client, FIXTURE.read_bytes(), route)
    assert replay.status_code == 409, replay.json()
    assert replay.json()["detail"]["idempotent_replay"] is True
    assert len(ingested) == 1


@pytest.mark.parametrize("route", ["", "/document"])
def test_redis_error_on_mark_stored_keeps_the_response(client, store, ingested, monkeypatch, route):
    """Events are committed. The claim just lapses and event idempotency takes over."""

    def _boom(*args, **kwargs):
        raise TimeoutError("redis timed out")

    monkeypatch.setattr(store, "eval", _boom)
    response = _post(client, FIXTURE.read_bytes(), route)
    assert response.status_code == 201, response.json()
    assert list(store.ttls.values()) == [dedup_mod._PENDING_TTL_SECONDS]


def test_advisory_rejection_frees_isa13(client, store, ingested):
    """``?strict=false`` answers 201 rejected with no ingestion_result: nothing stored."""
    advisory = client.post(
        "/api/v1/ingest/edi/document",
        params={"strict": "false"},
        data={"traceability_lot_code": "A" * 2, "tenant_id": TENANT},
        files={"file": ("asn_856.edi", FIXTURE.read_bytes(), "application/edi-x12")},
    )
    assert advisory.status_code == 201, advisory.json()
    assert advisory.json()["status"] == "rejected"
    assert advisory.json()["ingestion_result"] is None
    assert store.keys == {}, "an advisory rejection must not burn its ISA13"
    assert ingested == []

    resend = _post(client, FIXTURE.read_bytes(), "/document")
    assert resend.status_code == 201, resend.json()
    assert len(ingested) == 1


def test_document_route_zero_quantity_writes_a_rejection_record(client, store, ingested):
    """A refused FSMA document needs an audit record, and its claim is freed."""
    rejected = _post(client, _zero_quantity_variant(), "/document")
    assert rejected.status_code == 422, rejected.json()
    detail = rejected.json()["detail"]
    assert detail["error"] == "edi_non_positive_quantity"
    assert detail["needs_review"] is True

    records = rejection_log.list_edi_rejections(TENANT)
    assert [record["rejection_id"] for record in records] == [detail["rejection_id"]]
    assert records[0]["reason"] == "edi_non_positive_quantity"
    assert records[0]["needs_review"] is True
    assert ingested == []
