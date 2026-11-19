"""The EDI response status must say what ``ingest_events`` actually stored.

The other EDI route tests stub ``ingest_events``, so a document whose events
were all rejected still looked like a success: HTTP 201, ``status: "accepted"``,
``ingestion_result.accepted == 0``. These tests post through the routes into
the real ``ingest_events`` and the real ``_validate_event_kdes``. Only the
layers below it (auth, rate limit, database, canonical store, graph sync) are
faked, using the same seams as ``test_webhook_compat_enforcement.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
import shared.canonical_event as canonical_event  # noqa: E402
import shared.cte_persistence as cte_persistence  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.models import ingest_status  # noqa: E402
from app.webhook_models import IngestResponse  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TENANT = "00000000-0000-0000-0000-000000000123"
ASN_856 = service_dir / "tests" / "fixtures" / "edi_corpus" / "asn_856.edi"
ENVELOPE = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     "
    "*260310*1200*U*00401*000000002*0*P*>~GS*SW*SENDERID*RECEIVERID*20260310*1200*2*X*004010~"
)


def _set_945(control: str, lot: str, *, ship_to: bool = True) -> str:
    """One 945 ST/SE set. Without N1*ST only ``ship_to_location`` is missing."""
    body = [
        f"ST*945*{control}",
        f"W06*N*ORDER-{control}*20260310*SHIP-{control}",
        "N1*SF*Valley Fresh Warehouse",
    ]
    if ship_to:
        body.append("N1*ST*Metro Distribution Center")
    body.append(f"W12*CC*10*10**CA*012345678905***{lot}")
    body.append(f"SE*{len(body) + 1}*{control}")
    return "~".join(body) + "~"


def _batch_945(*sets: str) -> bytes:
    trailer = f"GE*{len(sets)}*2~IEA*1*000000002~"
    return (ENVELOPE + "".join(sets) + trailer).encode()


class _Savepoint:
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class _Session:
    def begin_nested(self) -> _Savepoint:
        return _Savepoint()

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class _Persistence:
    """Records what reached storage."""

    def __init__(self) -> None:
        self.stored: list[str] = []

    def store_event(self, **kwargs):
        self.stored.append(kwargs["traceability_lot_code"])
        return SimpleNamespace(
            event_id=f"evt-{len(self.stored)}",
            sha256_hash="sha",
            chain_hash="chain",
            idempotent=False,
        )


@pytest.fixture()
def persistence(monkeypatch: pytest.MonkeyPatch) -> _Persistence:
    compat = sys.modules[edi_routes.ingest_events.__module__]
    store = _Persistence()

    def _session_gen():
        yield _Session()

    def _no_canonical(*_args, **_kwargs):
        raise ImportError("canonical store not under test")

    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    monkeypatch.setattr(compat, "_verify_api_key_sync", lambda x_regengine_api_key=None: None)
    monkeypatch.setattr(compat, "_check_rate_limit", lambda _tenant_id: None)
    monkeypatch.setattr(compat, "_get_db_session", _session_gen)
    monkeypatch.setattr(compat, "_publish_graph_sync", lambda *_args: None)
    monkeypatch.setattr(compat, "record_outcomes", lambda *_args: None)
    monkeypatch.setattr(cte_persistence, "CTEPersistence", lambda _session: store)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", _no_canonical)
    # ISA13 dedup lives in Redis and has its own suite.
    monkeypatch.setattr(edi_routes, "check_and_record_interchange", lambda *a, **kw: (False, None))
    return store


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id=TENANT, auth_mode="test"
    )
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, route: str, document: bytes, **form: str):
    return client.post(
        f"/api/v1/ingest/edi{route}",
        data={"traceability_lot_code": "00012345678901-LOT001", **form},
        files={"file": ("doc.edi", document, "application/edi-x12")},
    )


@pytest.mark.parametrize("route", ["", "/document"])
def test_all_events_rejected_is_reported_as_rejected(
    client: TestClient, persistence: _Persistence, route: str
) -> None:
    """The live failure: every event fails KDE validation, nothing is stored."""
    response = _post(client, route, ASN_856.read_bytes())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection"] is None
    result = body["ingestion_result"]
    assert (result["accepted"], result["rejected"], result["total"]) == (0, 1, 1)
    assert "Missing required KDE 'tlc_source_reference' for shipping CTE" in result["events"][0]["errors"]
    assert persistence.stored == []


def test_some_events_rejected_is_reported_as_partial(client: TestClient, persistence: _Persistence) -> None:
    good_lot, bad_lot = "00012345678905-LOTGOOD", "00012345678905-LOTBAD"
    document = _batch_945(_set_945("0001", good_lot), _set_945("0002", bad_lot, ship_to=False))

    response = _post(client, "/document", document, tlc_source_reference="Valley Fresh Packhouse")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "partial"
    assert body["rejection"] is None
    result = body["ingestion_result"]
    assert (result["accepted"], result["rejected"], result["total"]) == (1, 1, 2)
    by_lot = {event["traceability_lot_code"]: event for event in result["events"]}
    assert by_lot[good_lot]["status"] == "accepted"
    assert by_lot[bad_lot]["status"] == "rejected"
    assert "Missing required KDE 'ship_to_location' for shipping CTE" in by_lot[bad_lot]["errors"]
    assert persistence.stored == [good_lot]


def test_all_events_stored_is_reported_as_accepted(client: TestClient, persistence: _Persistence) -> None:
    lots = ["00012345678905-LOTONE", "00012345678905-LOTTWO"]
    document = _batch_945(_set_945("0001", lots[0]), _set_945("0002", lots[1]))

    response = _post(client, "/document", document, tlc_source_reference="Valley Fresh Packhouse")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["ingestion_result"]["accepted"] == 2
    assert persistence.stored == lots


@pytest.mark.parametrize(
    "accepted,rejected,expected",
    [(1, 0, "accepted"), (1, 2, "partial"), (0, 3, "rejected"), (0, 0, "rejected")],
)
def test_856_route_uses_the_same_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accepted: int,
    rejected: int,
    expected: str,
) -> None:
    """Stubbed: without #3781 no real 856 passes KDE validation on this route."""

    async def _fake_ingest_events(_payload, **_kwargs):
        return IngestResponse(accepted=accepted, rejected=rejected, total=accepted + rejected)

    monkeypatch.setattr(edi_routes, "ingest_events", _fake_ingest_events)
    monkeypatch.setattr(edi_routes, "check_and_record_interchange", lambda *a, **kw: (False, None))

    response = _post(client, "", ASN_856.read_bytes())

    assert response.status_code == 201, response.text
    assert response.json()["status"] == expected


def test_status_treats_an_empty_result_as_nothing_stored() -> None:
    assert ingest_status(IngestResponse(accepted=0, rejected=0, total=0)) == "rejected"
