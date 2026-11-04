"""A valid 856 must get through the real required-KDE gate on both EDI routes.

Every other EDI route test stubs ``ingest_events``, so nothing ran the gate in
``_validate_event_kdes`` against what the routes actually build. That is how a
valid ASN came to return HTTP 201 with ``accepted: 0``. Only storage is faked
here: ``ingest_events`` and the gate are the real ones.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir.parent))

from shared.paths import ensure_shared_importable  # noqa: E402

ensure_shared_importable()
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
import app.webhook_compat as webhook_compat  # noqa: E402
import shared.canonical_event as canonical_event  # noqa: E402
import shared.canonical_persistence as canonical_persistence  # noqa: E402
import shared.cte_persistence as cte_persistence  # noqa: E402
import shared.rules_engine as rules_engine  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402

TENANT = "00000000-0000-0000-0000-000000000123"
FIXTURE = Path(__file__).parent / "fixtures" / "edi_corpus" / "asn_856.edi"
ROUTES = ["", "/document"]
TLC_SOURCE = "0061414100001"


class _Savepoint:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _FakeSession:
    def begin_nested(self) -> _Savepoint:
        return _Savepoint()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def _fake_db_session() -> Iterator[_FakeSession]:
    yield _FakeSession()


class _StoreResult:
    event_id = "00000000-0000-0000-0000-000000000099"
    sha256_hash = "h" * 64
    chain_hash = "c" * 64


@pytest.fixture()
def stored(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Fake storage only, and record what reached it."""
    calls: list[dict[str, Any]] = []

    class _FakePersistence:
        def __init__(self, db: Any) -> None:
            self.db = db

        def store_event(self, **kwargs: Any) -> _StoreResult:
            calls.append(kwargs)
            return _StoreResult()

    class _NoCanonicalStore:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def persist_event(self, event: Any) -> None:
            return None

    class _FakeCanonical:
        event_id = "00000000-0000-0000-0000-000000000099"
        event_type = type("EventType", (), {"value": "shipping"})()
        traceability_lot_code = "LOT"
        product_reference = None
        quantity = 1.0
        unit_of_measure = "cases"
        from_facility_reference = None
        to_facility_reference = None
        from_entity_reference = None
        to_entity_reference = None
        kdes: dict[str, Any] = {}

    class _NoRules:
        def __init__(self, db: Any) -> None:
            return None

        def evaluate_event(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(webhook_compat, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_get_db_session", _fake_db_session)
    monkeypatch.setattr(webhook_compat, "_publish_graph_sync", lambda *args: None)
    monkeypatch.setattr(cte_persistence, "CTEPersistence", _FakePersistence)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", lambda *a, **k: _FakeCanonical())
    monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _NoCanonicalStore)
    monkeypatch.setattr(rules_engine, "RulesEngine", _NoRules)
    monkeypatch.setattr(edi_routes, "check_and_record_interchange", lambda **kwargs: (False, None))
    return calls


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    monkeypatch.setattr(edi_routes, "_resolve_principal_tenant_id", lambda *args: TENANT)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(key_id="test", scopes=["edi.ingest"])
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, route: str, raw: bytes | None = None, **form: str):
    return client.post(
        f"/api/v1/ingest/edi{route}",
        data={"traceability_lot_code": "LOT-ROMAINE-001", **form},
        files={"file": ("asn.edi", raw if raw is not None else FIXTURE.read_bytes(), "application/edi-x12")},
    )


@pytest.mark.parametrize("route", ROUTES)
def test_valid_856_stores_through_the_real_gate(client: TestClient, stored: list[dict[str, Any]], route: str) -> None:
    response = _post(client, route, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    result = response.json()["ingestion_result"]
    assert result["accepted"] == 1, result
    assert result["rejected"] == 0, result
    assert len(stored) == 1

    kdes = stored[0]["kdes"]
    assert kdes["reference_document"] == "BOL-9001"
    assert kdes["tlc_source_reference"] == TLC_SOURCE
    assert kdes["ship_date"] == "2026-03-10"
    assert kdes["ship_from_location"] == "Valley Fresh Farms"
    assert kdes["ship_to_location"] == "Metro Distribution Center"


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("form", [{}, {"tlc_source_reference": "   "}])
def test_missing_tlc_source_is_rejected_before_the_isa13_is_reserved(
    client: TestClient,
    stored: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    form: dict[str, str],
) -> None:
    reserved: list[Any] = []
    monkeypatch.setattr(
        edi_routes,
        "check_and_record_interchange",
        lambda **kwargs: (reserved.append(kwargs), (False, None))[1],
    )

    response = _post(client, route, **form)

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_856_missing_required_kdes"
    assert detail["missing_kdes"] == ["tlc_source_reference"]
    assert detail["rejection_id"]
    assert stored == []
    # The corrected resend must not come back as a 409 replay.
    assert reserved == []


def test_strict_false_does_not_downgrade_a_missing_tlc_source(
    client: TestClient, stored: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    reserved: list[Any] = []
    monkeypatch.setattr(
        edi_routes,
        "check_and_record_interchange",
        lambda **kwargs: (reserved.append(kwargs), (False, None))[1],
    )

    response = _post(client, "/document?strict=false")

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["missing_kdes"] == ["tlc_source_reference"]
    assert stored == []
    assert reserved == []


@pytest.mark.parametrize("route", ROUTES)
def test_tlc_source_is_not_taken_from_the_ship_from_party(client: TestClient, route: str) -> None:
    response = _post(client, route)

    assert response.status_code == 422
    assert "Valley Fresh Farms" not in str(response.json()["detail"].get("errors"))


@pytest.mark.parametrize("route", ROUTES)
def test_856_with_no_ref_segment_uses_the_asn_as_reference_document(
    client: TestClient, stored: list[dict[str, Any]], route: str
) -> None:
    raw = FIXTURE.read_bytes().replace(b"REF*BM*BOL-9001~", b"").replace(b"SE*10*0001", b"SE*9*0001")

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    assert stored[0]["kdes"]["reference_document"] == "ASN-12345"


@pytest.mark.parametrize("route", ROUTES)
def test_856_with_no_reference_document_at_all_is_rejected(
    client: TestClient, stored: list[dict[str, Any]], route: str
) -> None:
    raw = (
        FIXTURE.read_bytes()
        .replace(b"REF*BM*BOL-9001~", b"")
        .replace(b"SE*10*0001", b"SE*9*0001")
        .replace(b"BSN*00*ASN-12345*", b"BSN*00**")
    )

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["missing_kdes"] == ["reference_document"]
    assert stored == []
