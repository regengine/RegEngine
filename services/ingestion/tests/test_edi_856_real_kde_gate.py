"""Valid EDI must get through the real required-KDE gate, or fail before ISA13.

Every other EDI route test stubs ``ingest_events``, so nothing ran the gate in
``_validate_event_kdes`` against what the routes actually build. That is how a
valid ASN came to return HTTP 201 with ``accepted: 0``. Only storage is faked
here: ``ingest_events`` and the gate are the real ones.

The later tests cover every set on ``/document``. Each one either stores, or gets
a logged 422 before the ISA13 is reserved so a corrected resend is not a replay.
"""

from __future__ import annotations

import hashlib
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
from shared import edi_rejection_audit  # noqa: E402

TENANT = "00000000-0000-0000-0000-000000000123"
FIXTURE = Path(__file__).parent / "fixtures" / "edi_corpus" / "asn_856.edi"
ROUTES = ["", "/document"]
TLC_SOURCE = "0061414100001"
receipts: list[Any] = []


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
    monkeypatch.setattr(
        webhook_compat,
        "_open_ingestion_run",
        lambda db, tenant_id, source, receipt: (receipts.append(receipt), "00000000-0000-0000-0000-000000000777")[1],
    )
    monkeypatch.setattr(webhook_compat, "_close_ingestion_run", lambda *a, **k: None)
    # The PostgreSQL interchange receipt has its own tests; this fake session has no SQL.
    monkeypatch.setattr(webhook_compat.EDIInterchange, "reserve", lambda self, session, tenant_id: None)
    monkeypatch.setattr(webhook_compat.EDIInterchange, "record_stored", lambda self, session, tenant_id: None)
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


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        (b"LIN**SK*ROMAINE-12CT~", b"", "product_description"),
        (b"SN1**200*CA~", b"SN1**200~", "unit_of_measure"),
        (b"SN1**200*CA~", b"", "quantity"),
        (b"N1*SF*Valley Fresh Farms*92", b"N1*SF**92", "ship_from_location"),
        (b"N1*ST*Metro Distribution Center*92", b"N1*ST**92", "ship_to_location"),
    ],
    ids=["product", "unit", "quantity", "ship_from", "ship_to"],
)
def test_synthesized_856_kdes_are_rejected_before_the_isa13_is_reserved(
    client: TestClient,
    stored: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    old: bytes,
    new: bytes,
    missing: str,
) -> None:
    """The gate cannot catch these: the route's placeholder would pass it."""
    reserved: list[Any] = []
    monkeypatch.setattr(
        edi_routes,
        "check_and_record_interchange",
        lambda **kwargs: (reserved.append(kwargs), (False, None))[1],
    )
    raw = FIXTURE.read_bytes().replace(old, new)

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 422, response.text
    assert missing in response.json()["detail"]["missing_kdes"]
    assert stored == []
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


def _document(transaction_set: str, *body: str) -> bytes:
    segments = [f"ST*{transaction_set}*0001", *body]
    segments.append(f"SE*{len(segments) + 1}*0001")
    return (
        "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     "
        "*260310*1200*U*00401*000000001*0*P*>~GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
        + "~".join(segments)
        + "~GE*1*1~IEA*1*000000001~"
    ).encode()


SHIP_FROM = "N1*SF*Valley Fresh Farms*92*6141410000014"
SHIP_TO = "N1*ST*Metro Distribution Center*92*6141410000069"
PRODUCT = "PID*F****Romaine Hearts"
WAREHOUSE_PRODUCT = "G69*Romaine Hearts"
ASN_LINE = ("LIN**SK*ROMAINE-12CT", "SN1**200*CA")
ASN_HEADER = ("BSN*00*ASN-12345*20260310*1200", "HL*1**S")
RECEIPT_LINE = (PRODUCT, "RCD**200*CA")
PO_HEADER = "BEG*00*NE*PO-1**20260310"
INVOICE_HEADER = "BIG*20260310*INV-1**PO-1"

VALID_DOCUMENTS = {
    "861": ("BRA*RA-77*20260311*00", "REF*PO*PO-1", SHIP_FROM, SHIP_TO, *RECEIPT_LINE),
    "944": (
        "W17*F*20260311*R-1*ORD-1",
        SHIP_FROM,
        "N1*WH*Metro Warehouse*92*6141410000069",
        "W07*200*CA**UP*012345678905***LOT-ROMAINE-A",
        WAREHOUSE_PRODUCT,
    ),
    "945": (
        "W06*N*ORD-1*20260310*SHIP-1",
        SHIP_FROM,
        SHIP_TO,
        "W12*CC*200*200*0*CA****LOT-ROMAINE-A",
        WAREHOUSE_PRODUCT,
    ),
}


def _without(transaction_set: str, segment: str) -> bytes:
    body = VALID_DOCUMENTS[transaction_set]
    assert segment in body
    return _document(transaction_set, *(item for item in body if item != segment))


@pytest.fixture()
def reserved(stored: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record ISA13 reservations. ``stored`` first, as it stubs the same name."""
    calls: list[Any] = []
    monkeypatch.setattr(
        edi_routes,
        "check_and_record_interchange",
        lambda **kwargs: (calls.append(kwargs), (False, None))[1],
    )
    return calls


def _assert_rejected_before_reservation(
    response: Any,
    transaction_set: str,
    missing: list[str],
    stored: list[dict[str, Any]],
    reserved: list[Any],
) -> None:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == f"edi_{transaction_set}_missing_required_kdes"
    assert detail["missing_kdes"] == missing
    assert detail["rejection_id"]
    assert stored == []
    assert reserved == []


@pytest.mark.parametrize("transaction_set", VALID_DOCUMENTS)
def test_valid_document_stores_through_the_real_gate(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any], transaction_set: str
) -> None:
    raw = _document(transaction_set, *VALID_DOCUMENTS[transaction_set])

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    result = response.json()["ingestion_result"]
    assert (result["accepted"], result["rejected"]) == (1, 0), result
    assert len(stored) == 1
    assert len(reserved) == 1
    assert stored[0]["kdes"]["tlc_source_reference"] == TLC_SOURCE


def test_861_kdes_come_from_the_document(client: TestClient, stored: list[dict[str, Any]]) -> None:
    raw = _document("861", *VALID_DOCUMENTS["861"])

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    kdes = stored[0]["kdes"]
    assert kdes["receive_date"] == "2026-03-11"
    assert kdes["receiving_location"] == "Metro Distribution Center"
    assert kdes["immediate_previous_source"] == "Valley Fresh Farms"
    assert kdes["reference_document"] == "RA-77"


def test_861_previous_source_can_be_the_ship_from_gln(client: TestClient, stored: list[dict[str, Any]]) -> None:
    body = ["N1*SF**92*6141410000014" if item == SHIP_FROM else item for item in VALID_DOCUMENTS["861"]]

    response = _post(client, "/document", _document("861", *body), tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    assert stored[0]["kdes"]["immediate_previous_source"] == "6141410000014"


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        (("N1*SF**92*6141410000014", SHIP_TO), ["ship_from_location"]),
        ((SHIP_FROM, "N1*ST**92*6141410000069"), ["ship_to_location"]),
        (("N1*SF**92*6141410000014", "N1*ST**92*6141410000069"), ["ship_from_location", "ship_to_location"]),
    ],
    ids=["no_ship_from_name", "no_ship_to_name", "neither_name"],
)
def test_856_party_with_no_name_is_rejected_before_reservation(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    body: tuple[str, ...],
    missing: list[str],
) -> None:
    raw = _document("856", *ASN_HEADER, *body, *ASN_LINE, "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "856", missing, stored, reserved)


def test_location_override_does_not_supply_the_ship_from_kde(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    raw = _document("856", *ASN_HEADER, "N1*SF**92*6141410000014", SHIP_TO, *ASN_LINE, "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE, location_override="Dock 4")

    _assert_rejected_before_reservation(response, "856", ["ship_from_location"], stored, reserved)


def test_856_line_with_no_product_id_is_rejected_before_reservation(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    raw = _document("856", *ASN_HEADER, SHIP_FROM, SHIP_TO, "SN1**200*CA", "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "856", ["product_description"], stored, reserved)


def test_856_with_no_item_line_is_rejected_before_reservation(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    raw = _document("856", *ASN_HEADER, SHIP_FROM, SHIP_TO, "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(
        response, "856", ["quantity", "unit_of_measure", "product_description"], stored, reserved
    )


def test_one_856_line_with_no_product_id_rejects_the_document(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    raw = _document("856", *ASN_HEADER, SHIP_FROM, SHIP_TO, *ASN_LINE, "LIN*2", "SN1**100*CA", "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "856", ["product_description"], stored, reserved)


def test_product_description_override_supplies_the_missing_product(
    client: TestClient, stored: list[dict[str, Any]]
) -> None:
    raw = _document("856", *ASN_HEADER, SHIP_FROM, SHIP_TO, "SN1**200*CA", "REF*BM*BOL-9001")

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE, product_description="Romaine Hearts")

    assert response.status_code == 201, response.text
    assert stored[0]["product_description"] == "Romaine Hearts"


@pytest.mark.parametrize("transaction_set", VALID_DOCUMENTS)
def test_document_with_no_tlc_source_is_rejected_before_reservation(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any], transaction_set: str
) -> None:
    raw = _document(transaction_set, *VALID_DOCUMENTS[transaction_set])

    response = _post(client, "/document", raw)

    _assert_rejected_before_reservation(response, transaction_set, ["tlc_source_reference"], stored, reserved)


@pytest.mark.parametrize(
    ("transaction_set", "segment", "missing"),
    [
        ("861", SHIP_FROM, ["immediate_previous_source"]),
        ("861", SHIP_TO, ["receiving_location"]),
        ("861", PRODUCT, ["product_description"]),
        ("944", SHIP_FROM, ["immediate_previous_source"]),
        ("944", "N1*WH*Metro Warehouse*92*6141410000069", ["receiving_location"]),
        ("944", WAREHOUSE_PRODUCT, ["product_description"]),
        ("945", SHIP_FROM, ["ship_from_location"]),
        ("945", SHIP_TO, ["ship_to_location"]),
        ("945", WAREHOUSE_PRODUCT, ["product_description"]),
    ],
)
def test_missing_kde_is_rejected_before_reservation(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    transaction_set: str,
    segment: str,
    missing: list[str],
) -> None:
    raw = _without(transaction_set, segment)

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, transaction_set, missing, stored, reserved)


@pytest.mark.parametrize(
    ("transaction_set", "good", "bad", "missing"),
    [
        ("861", "RCD**200*CA", "RCD**200", ["unit_of_measure"]),
        ("861", "RCD**200*CA", "RCD**200*XX", ["unit_of_measure"]),
        ("861", "RCD**200*CA", "RCD***CA", ["quantity"]),
        ("861", "RCD**200*CA", "RCD**0*CA", ["quantity"]),
        (
            "944",
            "W07*200*CA**UP*012345678905***LOT-ROMAINE-A",
            "W07*200***UP*012345678905***LOT-ROMAINE-A",
            ["unit_of_measure"],
        ),
        (
            "944",
            "W07*200*CA**UP*012345678905***LOT-ROMAINE-A",
            "W07**CA**UP*012345678905***LOT-ROMAINE-A",
            ["quantity"],
        ),
        ("945", "W12*CC*200*200*0*CA****LOT-ROMAINE-A", "W12*CC*200*200*0*****LOT-ROMAINE-A", ["unit_of_measure"]),
        ("945", "W12*CC*200*200*0*CA****LOT-ROMAINE-A", "W12*CC*200**0*CA****LOT-ROMAINE-A", ["quantity"]),
    ],
)
def test_quantity_and_unit_are_not_synthesized_on_other_sets(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    transaction_set: str,
    good: str,
    bad: str,
    missing: list[str],
) -> None:
    body = [bad if item == good else item for item in VALID_DOCUMENTS[transaction_set]]
    assert bad in body

    response = _post(client, "/document", _document(transaction_set, *body), tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, transaction_set, missing, stored, reserved)


def test_unit_override_supplies_a_blank_unit(client: TestClient, stored: list[dict[str, Any]]) -> None:
    body = ["RCD**200" if item == "RCD**200*CA" else item for item in VALID_DOCUMENTS["861"]]

    response = _post(
        client,
        "/document",
        _document("861", *body),
        tlc_source_reference=TLC_SOURCE,
        unit_of_measure_override="CA",
    )

    assert response.status_code == 201, response.text
    assert len(stored) == 1


@pytest.mark.parametrize(
    ("transaction_set", "body"),
    [
        (
            "850",
            (
                PO_HEADER,
                "N1*BY*Metro Distribution Center*92*6141410000069",
                "N1*SE*Valley Fresh Farms*92*6141410000014",
                "PO1*1*200*CA*2.50**UP*012345678905",
                PRODUCT,
            ),
        ),
        (
            "810",
            (
                INVOICE_HEADER,
                "N1*RI*Metro Distribution Center*92*6141410000069",
                "N1*SF*Valley Fresh Farms*92*6141410000014",
                "IT1*1*200*CA*2.50**UP*012345678905",
                PRODUCT,
                "TDS*50000",
            ),
        ),
    ],
)
def test_commercial_documents_supply_no_shipping_kdes(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    transaction_set: str,
    body: tuple[str, ...],
) -> None:
    """The PO or invoice date is not a ship date, and buyer and seller are not locations."""
    raw = _document(transaction_set, *body)

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(
        response,
        transaction_set,
        ["ship_date", "ship_from_location", "ship_to_location"],
        stored,
        reserved,
    )


def test_one_bad_set_in_a_batch_rejects_the_interchange(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    good = ("ST*856*0001", *ASN_HEADER, SHIP_FROM, SHIP_TO, *ASN_LINE, "REF*BM*BOL-9001", "SE*10*0001")
    bad = ("ST*856*0002", *ASN_HEADER, SHIP_FROM, *ASN_LINE, "REF*BM*BOL-9002", "SE*9*0002")
    single = _document("856", *ASN_HEADER).decode()
    envelope, _, _ = single.partition("ST*856")
    raw = (envelope + "~".join((*good, *bad)) + "~GE*2*1~IEA*1*000000001~").encode()

    response = _post(client, "/document", raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "856", ["ship_to_location"], stored, reserved)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        (b"N1*SF*Valley Fresh Farms*92", b"N1*SF*   *92", "ship_from_location"),
        (b"N1*ST*Metro Distribution Center*92", b"N1*ST*   *92", "ship_to_location"),
    ],
    ids=["ship_from", "ship_to"],
)
def test_whitespace_856_party_name_is_rejected_before_reservation(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    route: str,
    old: bytes,
    new: bytes,
    missing: str,
) -> None:
    raw = FIXTURE.read_bytes().replace(old, new)

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "856", [missing], stored, reserved)


@pytest.mark.parametrize(
    ("old", "new", "missing"),
    [
        (SHIP_TO, "N1*ST*   ", ["receiving_location"]),
        (SHIP_FROM, "N1*SF*   ", ["immediate_previous_source"]),
    ],
    ids=["receiving_location", "previous_source"],
)
def test_whitespace_861_party_name_is_rejected_before_reservation(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    old: str,
    new: str,
    missing: list[str],
) -> None:
    body = [new if item == old else item for item in VALID_DOCUMENTS["861"]]

    response = _post(client, "/document", _document("861", *body), tlc_source_reference=TLC_SOURCE)

    _assert_rejected_before_reservation(response, "861", missing, stored, reserved)


@pytest.mark.parametrize("route", ROUTES)
def test_blank_product_override_keeps_the_document_product(
    client: TestClient, stored: list[dict[str, Any]], route: str
) -> None:
    response = _post(client, route, tlc_source_reference=TLC_SOURCE, product_description="   ")

    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["accepted"] == 1
    assert stored[0]["product_description"] == "ROMAINE-12CT"


@pytest.mark.parametrize("route", ROUTES)
def test_uploaded_856_is_retained_as_the_source_of_its_events(
    client: TestClient, stored: list[dict[str, Any]], route: str
) -> None:
    receipts.clear()
    raw = FIXTURE.read_bytes()

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["ingestion_run_id"]
    assert [receipt.sha256 for receipt in receipts] == [hashlib.sha256(raw).hexdigest()]
    assert receipts[0].filename == "asn.edi"
    assert receipts[0].raw_bytes == raw
    assert receipts[0].source_system == "edi"
    assert receipts[0].record_count == 1


@pytest.mark.parametrize("route", ROUTES)
def test_rejection_id_is_not_issued_without_durable_evidence(
    client: TestClient,
    stored: list[dict[str, Any]],
    reserved: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    def _unavailable(record: dict[str, Any]) -> None:
        raise edi_rejection_audit.EdiRejectionAuditUnavailable("down")

    monkeypatch.setattr(edi_rejection_audit, "persist_edi_rejection", _unavailable)

    response = _post(client, route)

    assert response.status_code == 503, response.text
    assert "rejection_id" not in response.text
    assert stored == []
    assert reserved == []


@pytest.mark.parametrize("route", ROUTES)
def test_rejection_evidence_is_written_durably(client: TestClient, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    written: list[dict[str, Any]] = []
    monkeypatch.setattr(edi_rejection_audit, "persist_edi_rejection", written.append)

    response = _post(client, route)

    assert response.status_code == 422, response.text
    assert [row["rejection_id"] for row in written] == [response.json()["detail"]["rejection_id"]]
    assert written[0]["tenant_id"] == TENANT
    assert written[0]["errors"][0]["loc"] == ["tlc_source_reference"]


@pytest.mark.parametrize("route", ROUTES)
def test_blank_unit_override_keeps_the_document_unit(
    client: TestClient, stored: list[dict[str, Any]], route: str
) -> None:
    response = _post(client, route, tlc_source_reference=TLC_SOURCE, unit_of_measure_override="   ")

    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["accepted"] == 1
    assert stored[0]["unit_of_measure"] == "cases"


def test_whitespace_861_ship_from_name_falls_back_to_the_gln(
    client: TestClient, stored: list[dict[str, Any]], reserved: list[Any]
) -> None:
    gln = "6141410000014"
    body = [f"N1*SF*   *92*{gln}" if item == SHIP_FROM else item for item in VALID_DOCUMENTS["861"]]

    response = _post(client, "/document", _document("861", *body), tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["accepted"] == 1
    assert stored[0]["kdes"]["immediate_previous_source"] == gln


@pytest.mark.parametrize(
    ("route", "error"),
    [("", "edi_invalid_event"), ("/document", "fsma_validation_failed")],
    ids=["legacy", "document"],
)
def test_too_short_line_lot_is_a_logged_422_and_frees_the_claim(
    client: TestClient,
    stored: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    error: str,
) -> None:
    written: list[dict[str, Any]] = []
    released: list[Any] = []
    monkeypatch.setattr(edi_rejection_audit, "persist_edi_rejection", written.append)
    monkeypatch.setattr(edi_routes, "release_interchange", lambda *claim: released.append(claim))
    raw = FIXTURE.read_bytes().replace(b"SN1**200*CA~", b"SN1**200*CA~REF*LT*AA~")

    response = _post(client, route, raw, tlc_source_reference=TLC_SOURCE)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == error
    assert len(written) == 1
    assert stored == []
    assert len(released) == 1


@pytest.mark.parametrize("transaction_set", ["861", "944", "945"])
def test_quantity_override_repairs_a_blank_line_quantity(
    client: TestClient, stored: list[dict[str, Any]], transaction_set: str
) -> None:
    blanked = {
        "861": ("RCD**200*CA", "RCD***CA"),
        "944": ("W07*200*CA", "W07**CA"),
        "945": ("W12*CC*200*200*0*CA", "W12*CC*200**0*CA"),
    }[transaction_set]
    body = [item.replace(*blanked) for item in VALID_DOCUMENTS[transaction_set]]

    response = _post(
        client,
        "/document",
        _document(transaction_set, *body),
        tlc_source_reference=TLC_SOURCE,
        quantity_override="150",
    )

    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["accepted"] == 1
    assert stored[0]["quantity"] == 150
