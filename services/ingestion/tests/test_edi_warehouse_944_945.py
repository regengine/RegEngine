"""X12 944 and 945 warehouse advices on the unified EDI document route.

944 (Warehouse Stock Transfer Receipt Advice) is a receiving CTE.
945 (Warehouse Shipping Advice) is a shipping CTE. Both use the same
validation, envelope checks, interchange dedup, and persistence path
as 861 and 856. An unrecognized set still returns the same 400.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.edi_ingestion.transaction_sets import _SUPPORTED_TRANSACTION_SETS  # noqa: E402
from app.webhook_compat import _batch_dedup_key  # noqa: E402
from app.webhook_models import EventResult, IngestEvent, IngestResponse, WebhookCTEType  # noqa: E402
from app.webhook_router_v2.validation import _validate_event_kdes  # noqa: E402

_CORPUS_DIR = Path(__file__).parent / "fixtures" / "edi_corpus"
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
_VALID_FSMA_TLC = "00012345678901-LOT001"
_TLC_SOURCE_REFERENCE = "Packinghouse Assigner"
_LINE_TLCS = ["00012345678905-A", "00012345678912-B", "00012345678929-C"]


@pytest.fixture()
def captured_payload() -> dict:
    return {}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, captured_payload: dict) -> TestClient:
    monkeypatch.setenv("EDI_STRICT_MODE", "true")
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )

    async def _fake_ingest_events(payload, *, principal_tenant_id=None, x_regengine_api_key=None):
        captured_payload["payload"] = payload
        captured_payload["calls"] = captured_payload.get("calls", 0) + 1
        keys = [_batch_dedup_key(event) for event in payload.events]
        assert len(keys) == len(set(keys)), "the real save path would reject duplicate batch keys"
        assert all(not _validate_event_kdes(event) for event in payload.events), (
            "the real save path would reject missing required KDEs"
        )
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id=f"evt-edi-warehouse-{index}",
                    sha256_hash="hash-1",
                    chain_hash="chain-1",
                )
                for index, event in enumerate(payload.events, start=1)
            ],
        )

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", _fake_ingest_events)
    monkeypatch.setattr(
        edi_ingestion_routes,
        "check_and_record_interchange",
        lambda *a, **kw: (False, None),
    )
    with TestClient(app) as test_client:
        yield test_client


def _post(
    client: TestClient,
    raw: bytes,
    *,
    name: str,
    strict: bool | None = None,
    tlc_source_reference: str | None = _TLC_SOURCE_REFERENCE,
    submitted_tlc: str = _VALID_FSMA_TLC,
):
    params = None if strict is None else {"strict": "true" if strict else "false"}
    data = {
        "traceability_lot_code": submitted_tlc,
        "tenant_id": TEST_TENANT_ID,
    }
    if tlc_source_reference is not None:
        data["tlc_source_reference"] = tlc_source_reference
    return client.post(
        "/api/v1/ingest/edi/document",
        params=params,
        data=data,
        files={"file": (name, raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )


def test_golden_944_receiving_event_populates_kdes(client: TestClient, captured_payload: dict) -> None:
    """The first receipt line retains its own receiving KDEs."""
    raw = (_CORPUS_DIR / "receipt_944.edi").read_bytes()
    response = _post(client, raw, name="receipt_944.edi")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "X12_944"
    assert body["extracted"]["fsma_validation_status"] == "passed"
    assert body["ingestion_result"]["accepted"] == 3

    event = captured_payload["payload"].events[0]
    assert event.cte_type == WebhookCTEType.RECEIVING
    assert event.quantity == 10.0
    assert event.unit_of_measure == "cases"
    assert event.product_description == "Romaine Hearts 12ct"
    assert event.location_name == "Metro Distribution Center"
    assert event.location_gln == "6141410000069"
    assert event.kdes["event_date"] == "2026-03-18"
    assert event.kdes["lot_number"] == "A"
    assert event.kdes["receiving_location"] == "Metro Distribution Center"
    assert event.kdes["ship_from_location"] == "Valley Fresh Farms"
    assert event.kdes["reference_document_number"] == "WR-944001"
    assert event.traceability_lot_code == _LINE_TLCS[0]
    assert event.kdes["tlc_source_reference"] == _TLC_SOURCE_REFERENCE


def test_golden_945_shipping_event_populates_ship_from_and_ship_to(client: TestClient, captured_payload: dict) -> None:
    """The first advice line retains its own shipping KDEs and parties."""
    raw = (_CORPUS_DIR / "advice_945.edi").read_bytes()
    response = _post(client, raw, name="advice_945.edi")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "X12_945"
    assert body["extracted"]["fsma_validation_status"] == "passed"

    event = captured_payload["payload"].events[0]
    assert event.cte_type == WebhookCTEType.SHIPPING
    # W1203 (units shipped) is 10. W1202 (ordered) is 80 and must not win.
    assert event.quantity == 10.0
    assert event.unit_of_measure == "cases"
    assert event.kdes["event_date"] == "2026-03-19"
    assert event.kdes["ship_from_location"] == "Metro Distribution Center"
    assert event.kdes["ship_to_location"] == "Harbor Market"
    assert event.kdes["ship_from_gln"] == "6141410000069"
    assert event.kdes["ship_to_gln"] == "6141410000014"
    assert event.location_gln == "6141410000069"
    assert event.kdes["lot_number"] == "A"
    assert event.traceability_lot_code == _LINE_TLCS[0]
    # Qualifier 92 is an assigned id, not a GLN, so the depositor id stays
    # off the GLN fields.
    assert event.kdes["depositor_name"] == "Valley Fresh Farms"
    assert event.kdes["depositor_id"] == "DEP-100"
    assert "depositor_gln" not in event.kdes


@pytest.mark.parametrize(
    ("name", "cte_type", "lots", "event_date", "shared_kdes"),
    [
        (
            "receipt_944.edi",
            WebhookCTEType.RECEIVING,
            ["A", "B", "C"],
            "2026-03-18",
            {
                "reference_document_number": "WR-944001",
                "receiving_location": "Metro Distribution Center",
                "ship_from_location": "Valley Fresh Farms",
                "bill_of_lading": "BOL-9001",
                "depositor_order_number": "DO-44021",
            },
        ),
        (
            "advice_945.edi",
            WebhookCTEType.SHIPPING,
            ["A", "B", "C"],
            "2026-03-19",
            {
                "reference_document_number": "SID-945001",
                "ship_from_location": "Metro Distribution Center",
                "ship_to_location": "Harbor Market",
                "bill_of_lading": "BOL-9451",
                "depositor_order_number": "DO-44022",
            },
        ),
    ],
)
def test_three_warehouse_lines_persist_as_three_events(
    client: TestClient,
    captured_payload: dict,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    cte_type: WebhookCTEType,
    lots: list[str],
    event_date: str,
    shared_kdes: dict[str, str],
) -> None:
    dedup_calls = []

    def _check_once(sender_id, receiver_id, isa13):
        dedup_calls.append((sender_id, receiver_id, isa13))
        return (False, None)

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _check_once)
    response = _post(client, (_CORPUS_DIR / name).read_bytes(), name=name, submitted_tlc="caller-reference")
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(dedup_calls) == 1
    assert captured_payload["calls"] == 1
    assert body["extracted"]["transaction_set_count"] == 1
    assert body["extracted"]["event_count"] == 3
    assert body["extracted"]["submitted_traceability_lot_code"] == "caller-reference"
    assert body["ingestion_result"]["accepted"] == body["ingestion_result"]["total"] == 3
    assert [result["event_id"] for result in body["ingestion_result"]["events"]] == [
        "evt-edi-warehouse-1",
        "evt-edi-warehouse-2",
        "evt-edi-warehouse-3",
    ]

    events = captured_payload["payload"].events
    assert len(events) == 3
    assert [event.cte_type for event in events] == [cte_type] * 3
    assert len({event.timestamp for event in events}) == 1
    assert [event.kdes["lot_number"] for event in events] == lots
    assert [event.quantity for event in events] == [10.0, 20.0, 30.0]
    assert [event.unit_of_measure for event in events] == ["cases", "cases", "each"]
    assert [event.product_description for event in events] == [
        "Romaine Hearts 12ct",
        "Romaine Hearts 24ct",
        "Spinach Clamshell",
    ]
    assert [event.kdes["upc"] for event in events] == ["012345678905", "012345678912", "012345678929"]
    assert [event.kdes["gtin"] for event in events] == [
        "00012345678905",
        "00012345678912",
        "00012345678929",
    ]
    assert [event.traceability_lot_code for event in events] == _LINE_TLCS
    assert body["traceability_lot_code"] == _LINE_TLCS[0]
    assert [result["traceability_lot_code"] for result in body["ingestion_result"]["events"]] == _LINE_TLCS
    assert [summary["traceability_lot_code"] for summary in body["extracted"]["events"]] == _LINE_TLCS
    for event in events:
        assert event.kdes["event_date"] == event_date
        assert event.kdes["edi_sender_id"] == "SENDERID"
        assert event.kdes["edi_receiver_id"] == "RECEIVERID"
        assert event.kdes["edi_isa13"] == dedup_calls[0][2]
        assert event.kdes["warehouse_gln"] == "6141410000069"
        assert event.kdes["depositor_name"] == "Valley Fresh Farms"
        assert event.kdes["tlc_source_reference"] == _TLC_SOURCE_REFERENCE
        assert event.kdes["g62_date_raw"]
        for key, value in shared_kdes.items():
            assert event.kdes[key] == value
    if cte_type == WebhookCTEType.RECEIVING:
        assert all(event.kdes["reference_numbers"]["PO"] == "PO-7788" for event in events)
    else:
        assert [event.kdes["quantity_ordered"] for event in events] == [80.0, 40.0, 60.0]
        assert all(event.kdes["po_number"] == "PO-8801" for event in events)


@pytest.mark.parametrize(
    ("name", "old_date", "header_date"),
    [
        ("receipt_944.edi", "20260318", "W17"),
        ("advice_945.edi", "20260319", "W06"),
    ],
)
def test_recent_warehouse_lines_pass_real_batch_guards_even_with_repeated_lot(
    client: TestClient,
    captured_payload: dict,
    name: str,
    old_date: str,
    header_date: str,
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert f"{header_date}*" in raw
    raw = raw.replace(old_date, today, 1)
    if name.startswith("receipt"):
        raw = raw.replace("***B~", "***A~")
    else:
        raw = raw.replace("*B~", "*A~")
    response = _post(client, raw.encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    assert response.json()["ingestion_result"]["accepted"] == 3
    events = captured_payload["payload"].events
    assert len({event.timestamp for event in events}) == 1
    assert events[0].kdes["lot_number"] == events[1].kdes["lot_number"]
    assert events[0].traceability_lot_code != events[1].traceability_lot_code
    assert [event.kdes["edi_line_index"] for event in events] == [1, 2, 3]


@pytest.mark.parametrize(("name", "old_date"), [("receipt_944.edi", "20260318"), ("advice_945.edi", "20260319")])
def test_http_route_calls_real_save_path_for_each_warehouse_line(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    old_date: str,
) -> None:
    import app.webhook_compat as webhook_compat
    import shared.canonical_event as canonical_event
    import shared.cte_persistence as cte_persistence
    import shared.rules.enforcement as enforcement

    stored: list[dict] = []

    class _Savepoint:
        def commit(self):
            pass

        def rollback(self):
            pass

    class _Session:
        def begin_nested(self):
            return _Savepoint()

        def commit(self):
            pass

        def rollback(self):
            pass

    class _Persistence:
        def __init__(self, session):
            pass

        def store_event(self, **kwargs):
            stored.append(kwargs)
            return SimpleNamespace(
                event_id=f"stored-{len(stored)}",
                sha256_hash=f"hash-{len(stored)}",
                chain_hash=f"chain-{len(stored)}",
            )

    def _db_session():
        yield _Session()

    def _skip_canonical(*args, **kwargs):
        raise ImportError("canonical store disabled in isolated save-path test")

    monkeypatch.setattr(edi_ingestion_routes, "ingest_events", webhook_compat.ingest_events)
    monkeypatch.setattr(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(webhook_compat, "_get_db_session", _db_session)
    monkeypatch.setattr(webhook_compat, "_publish_graph_sync", lambda *args: None)
    monkeypatch.setattr(cte_persistence, "CTEPersistence", _Persistence)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", _skip_canonical)
    monkeypatch.setattr(enforcement, "handle_preeval_exception", lambda *args, **kwargs: None)

    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    recent = raw.replace(old_date, datetime.now(timezone.utc).strftime("%Y%m%d"), 1)
    response = _post(client, recent.encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    result = response.json()["ingestion_result"]
    assert result["accepted"] == result["total"] == len(stored) == 3
    assert result["rejected"] == 0
    assert [event["event_id"] for event in result["events"]] == ["stored-1", "stored-2", "stored-3"]
    assert [entry["quantity"] for entry in stored] == [10.0, 20.0, 30.0]
    assert [entry["traceability_lot_code"] for entry in stored] == [
        event["traceability_lot_code"] for event in result["events"]
    ]
    assert [entry["traceability_lot_code"] for entry in stored] == _LINE_TLCS
    assert len({entry["event_timestamp"] for entry in stored}) == 1

    missing_source = _post(client, recent.encode("utf-8"), name=name, tlc_source_reference=None)
    assert missing_source.status_code == 201, missing_source.text
    rejected = missing_source.json()["ingestion_result"]
    assert (rejected["accepted"], rejected["rejected"], rejected["total"]) == (0, 3, 3)
    assert all(
        "Missing required KDE 'tlc_source_reference'" in result["errors"][0] for result in rejected["events"]
    )
    assert len(stored) == 3


def test_944_header_date_wins_over_g62_and_lot_stays_on_its_line() -> None:
    """W17 supplies the date; a shared N9*LT must not supply a missing W07 lot."""
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    n9_only = raw.replace("***A~", "***~").replace(
        "SE*14*0001~", "N9*LT*A~SE*15*0001~"
    )
    extracted = _extract_fields_for_set("944", _parse_x12_segments(n9_only))
    assert extracted["line_items"][0]["lot_number"] is None
    assert extracted["line_items"][1]["lot_number"] == "B"
    assert extracted["reference_numbers"]["LT"] == "A"
    assert extracted["receive_date_raw"] == "20260318"
    assert extracted["g62_date_raw"] == "20260317"
    assert extracted["line_items"][0]["gtin"] == "00012345678905"
    assert extracted["line_items"][0]["upc"] == "012345678905"
    assert extracted["warehouse_gln"] == "6141410000069"
    assert extracted["depositor_gln"] == "6141410000014"

    assert extracted["line_items"][0]["quantity"] == 10.0


def test_944_header_lot_reference_does_not_bleed_to_other_lines(
    client: TestClient, captured_payload: dict
) -> None:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    with_lot_ref = raw.replace("SE*14*0001~", "N9*LT*A~SE*15*0001~")
    response = _post(client, with_lot_ref.encode("utf-8"), name="receipt_944.edi")
    assert response.status_code == 201, response.text
    events = captured_payload["payload"].events
    assert [event.kdes["lot_number"] for event in events] == [
        "A",
        "B",
        "C",
    ]
    assert events[0].kdes["reference_numbers"]["LT"] == "A"
    assert all("LT" not in event.kdes["reference_numbers"] for event in events[1:])
    assert all(event.kdes["reference_numbers"]["PO"] == "PO-7788" for event in events)


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_line_without_item_ids_or_pattern_matching_lot_rejects(
    client: TestClient, captured_payload: dict, name: str
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    no_item_ids = raw.replace("012345678912*UK*00012345678912", "**")
    assert no_item_ids != raw
    response = _post(client, no_item_ids.encode("utf-8"), name=name)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "fsma_validation_failed"
    assert any("tlc" in error["loc"] for error in response.json()["detail"]["errors"])
    assert "payload" not in captured_payload


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_pattern_matching_lot_is_used_verbatim(
    client: TestClient, captured_payload: dict, name: str
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    old_lot = "***B~" if name.startswith("receipt") else "*B~"
    full_tlc = "00012345678901-LotB"
    edited = raw.replace(old_lot, old_lot.replace("B", full_tlc))
    assert edited != raw
    response = _post(client, edited.encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    event = captured_payload["payload"].events[1]
    assert event.traceability_lot_code == full_tlc
    assert event.kdes["lot_number"] == full_tlc
    assert event.kdes["gtin"] == "00012345678912"


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_upc_zero_pads_to_gtin14_when_gtin_is_absent(
    client: TestClient, captured_payload: dict, name: str
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    edited = raw.replace("012345678912*UK*00012345678912", "123456789012*VN*VENDOR-42")
    assert edited != raw
    response = _post(client, edited.encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    event = captured_payload["payload"].events[1]
    assert event.traceability_lot_code == "00123456789012-B"
    assert event.kdes["lot_number"] == "B"
    assert event.kdes["upc"] == "123456789012"
    assert "gtin" not in event.kdes


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_ean13_zero_pads_to_gtin14(client: TestClient, captured_payload: dict, name: str) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    edited = raw.replace("UK*00012345678912", "EN*1234567890123")
    assert edited != raw
    response = _post(client, edited.encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    event = captured_payload["payload"].events[1]
    assert event.traceability_lot_code == "01234567890123-B"
    assert event.kdes["gtin"] == "1234567890123"
    assert event.kdes["lot_number"] == "B"


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_vendor_item_number_and_punctuated_lot_are_preserved(
    client: TestClient, captured_payload: dict, name: str
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    edited = raw.replace("UK*00012345678912", "VN*VENDOR-42")
    old_lot = "***B~" if name.startswith("receipt") else "*B~"
    assert raw.count(old_lot) == 1
    edited = edited.replace(old_lot, old_lot.replace("B", "B / 2"))
    assert edited != raw
    extracted = _extract_fields_for_set("944" if name.startswith("receipt") else "945", _parse_x12_segments(edited))
    assert extracted["line_items"][1]["lot_number"] == "B / 2"
    assert extracted["line_items"][1]["gtin"] is None
    response = _post(client, edited.encode("utf-8"), name=name)
    assert response.status_code == 422, response.text
    assert any("tlc" in error["loc"] for error in response.json()["detail"]["errors"])
    assert "payload" not in captured_payload


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_warehouse_line_without_unit_uses_existing_unit_fallback(
    client: TestClient, captured_payload: dict, name: str
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    old = "W07*20*CA*" if name.startswith("receipt") else "W12*CC*40*20*0*CA*"
    new = "W07*20**" if name.startswith("receipt") else "W12*CC*40*20*0**"
    assert raw.count(old) == 1
    response = _post(client, raw.replace(old, new).encode("utf-8"), name=name)
    assert response.status_code == 201, response.text
    assert captured_payload["payload"].events[1].unit_of_measure == "units"


def test_945_shipped_quantity_ignores_ordered_and_non_gln_qualifier() -> None:
    raw = (_CORPUS_DIR / "advice_945.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("945", _parse_x12_segments(raw))
    assert extracted["line_items"][0]["quantity"] == 10.0
    assert extracted["line_items"][0]["quantity_ordered"] == 80.0
    assert extracted["ship_date_raw"] == "20260319"
    assert extracted["g62_date_raw"] == "20260318"
    assert extracted["ship_from_name"] == "Metro Distribution Center"
    assert extracted["ship_from_gln"] == "6141410000069"
    assert extracted["ship_to_name"] == "Harbor Market"
    assert extracted["ship_to_gln"] == "6141410000014"
    assert extracted["depositor_id"] == "DEP-100"
    assert extracted["depositor_gln"] is None
    assert extracted["po_number"] == "PO-8801"
    assert extracted["reference_document_number"] == "SID-945001"
    assert extracted["line_items"][0]["lot_number"] == "A"


def test_945_keeps_zero_ordered_quantity_with_positive_shipped_quantity(
    client: TestClient, captured_payload: dict
) -> None:
    raw = (_CORPUS_DIR / "advice_945.edi").read_text(encoding="utf-8")
    zero_ordered = raw.replace("W12*CC*40*20*0*CA*", "W12*CC*0*20*0*CA*")
    response = _post(client, zero_ordered.encode("utf-8"), name="advice_945.edi")
    assert response.status_code == 201, response.text
    assert captured_payload["payload"].events[1].quantity == 20.0
    assert captured_payload["payload"].events[1].kdes["quantity_ordered"] == 0.0
    assert response.json()["extracted"]["events"][1]["quantity_ordered"] == 0.0


def _receipt_missing_lot() -> bytes:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    edited = raw.replace("***A~", "***~")
    return edited.encode("utf-8")


def _receipt_missing_quantity() -> bytes:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    edited = raw.replace("W07*10*CA*", "W07*0*CA*")
    return edited.encode("utf-8")


def test_944_strict_missing_lot_returns_422_and_persists_nothing(client: TestClient, captured_payload: dict) -> None:
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_lot(), name="receipt_944_no_lot.edi", strict=True)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert detail["transaction_set"] == "944"
    locs = [tuple(err.get("loc") or ()) for err in detail["errors"]]
    assert any("lot_number" in loc for loc in locs)
    assert "payload" not in captured_payload
    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "fsma_validation_failed"
    assert rejections[0]["transaction_set"] == "944"


def test_944_strict_missing_quantity_returns_422_and_persists_nothing(
    client: TestClient, captured_payload: dict
) -> None:
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_quantity(), name="receipt_944_no_qty.edi", strict=True)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "fsma_validation_failed"
    assert detail["transaction_set"] == "944"
    locs = [tuple(err.get("loc") or ()) for err in detail["errors"]]
    assert any("quantity" in loc for loc in locs)
    assert "payload" not in captured_payload
    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    assert rejections[0]["transaction_set"] == "944"


def test_944_advisory_missing_lot_writes_rejection_log(client: TestClient, captured_payload: dict) -> None:
    """Advisory mode records the rejection and does not call the canonical ingest path."""
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    reset_edi_rejections()
    captured_payload.clear()
    response = _post(client, _receipt_missing_lot(), name="receipt_944_no_lot.edi", strict=False)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["document_type"] == "X12_944"
    assert body["extracted"]["fsma_validation_status"] == "failed"
    assert body["ingestion_result"] is None
    rejection = body["rejection"]
    assert rejection["reason"] == "fsma_validation_failed"
    assert rejection["rejection_id"].startswith("edi-rej-")
    assert "payload" not in captured_payload

    rejections = list_edi_rejections(TEST_TENANT_ID)
    assert len(rejections) == 1
    recorded = rejections[0]
    assert recorded["rejection_id"] == rejection["rejection_id"]
    assert recorded["transaction_set"] == "944"
    assert recorded["traceability_lot_code"] == _VALID_FSMA_TLC
    assert recorded["partner_id"] == "WALMART"


def test_warehouse_envelope_runs_once_before_fsma_line_validation(
    client: TestClient, captured_payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    dedup_calls = []

    def _dedup(sender_id, receiver_id, isa13):
        dedup_calls.append((sender_id, receiver_id, isa13))
        return False, None

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _dedup)
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    rejected = _post(client, raw.replace("***B~", "***~").encode("utf-8"), name="receipt_944.edi")
    assert rejected.status_code == 422, rejected.text
    assert len(dedup_calls) == 1
    assert "payload" not in captured_payload


def test_webhook_event_requires_tlc_source_reference_for_warehouse() -> None:
    event = IngestEvent(
        cte_type=WebhookCTEType.RECEIVING,
        traceability_lot_code=_VALID_FSMA_TLC,
        product_description="Romaine Hearts",
        quantity=10,
        unit_of_measure="cases",
        location_name="Warehouse",
        timestamp=datetime.now(timezone.utc).isoformat(),
        kdes={"edi_transaction_set": "944"},
    )
    assert "Missing required KDE 'tlc_source_reference' for receiving CTE" in _validate_event_kdes(event)


@pytest.mark.parametrize(
    ("name", "old", "new", "field"),
    [
        ("receipt_944.edi", "***B~", "***~", "lot_number"),
        ("advice_945.edi", "*B~", "*~", "lot_number"),
        ("receipt_944.edi", "W07*20*CA*", "W07*0*CA*", "quantity"),
        ("advice_945.edi", "W12*CC*40*20*0*CA*", "W12*CC*40*0*0*CA*", "quantity"),
        ("receipt_944.edi", "W07*20*CA*", "W07*inf*CA*", "quantity"),
        ("advice_945.edi", "W12*CC*40*20*0*CA*", "W12*CC*40*inf*0*CA*", "quantity"),
    ],
)
@pytest.mark.parametrize("strict", [True, False])
def test_one_bad_warehouse_line_rejects_the_whole_document(
    client: TestClient,
    captured_payload: dict,
    name: str,
    old: str,
    new: str,
    field: str,
    strict: bool,
) -> None:
    from app.edi_ingestion.rejection_log import list_edi_rejections, reset_edi_rejections

    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    assert raw.count(old) == 1
    reset_edi_rejections()
    response = _post(client, raw.replace(old, new).encode("utf-8"), name=name, strict=strict)
    assert response.status_code == (422 if strict else 201), response.text
    if strict:
        detail = response.json()["detail"]
        assert detail["error"] == "fsma_validation_failed"
        errors = detail["errors"]
    else:
        body = response.json()
        assert body["status"] == "rejected"
        assert body["ingestion_result"] is None
        assert body["extracted"]["event_count"] == 3
        assert body["extracted"]["events"][1]["fsma_validation_status"] == "failed"
        errors = list_edi_rejections(TEST_TENANT_ID)[0]["errors"]
    assert any(field in (error.get("loc") or ()) for error in errors)
    assert "payload" not in captured_payload
    assert len(list_edi_rejections(TEST_TENANT_ID)) == 1


@pytest.mark.parametrize("name", ["receipt_944.edi", "advice_945.edi"])
def test_warehouse_envelope_mismatch_matches_856(client: TestClient, captured_payload: dict, name: str) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8")
    mismatched = raw.replace("GS*RE*SENDERID*", "GS*RE*OTHERSENDER*", 1).replace(
        "GS*SW*SENDERID*", "GS*SW*OTHERSENDER*", 1
    )
    assert mismatched != raw
    captured_payload.clear()
    response = _post(client, mismatched.encode("utf-8"), name=name)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "edi_envelope_mismatch"
    assert detail["isa_sender_id"] == "SENDERID"
    assert detail["gs_sender_id"] == "OTHERSENDER"
    assert "payload" not in captured_payload


@pytest.mark.parametrize(
    ("name", "isa13"),
    [("receipt_944.edi", "000000944"), ("advice_945.edi", "000000945")],
)
def test_warehouse_isa13_replay_matches_856(
    client: TestClient,
    captured_payload: dict,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    isa13: str,
) -> None:
    seen: dict[str, str | None] = {}

    def _duplicate(sender_id, receiver_id, isa13):
        seen["sender_id"] = sender_id
        seen["receiver_id"] = receiver_id
        seen["isa13"] = isa13
        return (True, "seen")

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _duplicate)
    captured_payload.clear()
    raw = (_CORPUS_DIR / name).read_bytes()
    response = _post(client, raw, name=name)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "duplicate_interchange"
    assert detail["idempotent_replay"] is True
    assert detail["isa13"] == isa13
    assert seen["isa13"] == isa13
    assert seen["sender_id"] == "SENDERID"
    assert seen["receiver_id"] == "RECEIVERID"
    assert "payload" not in captured_payload


def test_944_keeps_each_quantity_and_mixed_unit_separate() -> None:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_text(encoding="utf-8")
    extracted = _extract_fields_for_set("944", _parse_x12_segments(raw))
    assert [(line["lot_number"], line["quantity"], line["unit_of_measure"]) for line in extracted["line_items"]] == [
        ("A", 10.0, "CA"),
        ("B", 20.0, "CA"),
        ("C", 30.0, "EA"),
    ]


@pytest.mark.parametrize(
    ("name", "code", "upc_index", "gtin_index"),
    [("receipt_944.edi", "944", 3, 5), ("advice_945.edi", "945", 6, 8)],
)
def test_warehouse_line_description_and_item_ids_do_not_bleed(
    name: str, code: str, upc_index: int, gtin_index: int
) -> None:
    raw = (_CORPUS_DIR / name).read_text(encoding="utf-8").replace("G69*Spinach Clamshell~", "")
    segments = _parse_x12_segments(raw)
    item_id = "W07" if code == "944" else "W12"
    last_line = [segment for segment in segments if segment[0] == item_id][2]
    last_line[upc_index] = ""
    last_line[gtin_index] = ""
    lines = _extract_fields_for_set(code, segments)["line_items"]
    assert lines[0]["product_description"] == "Romaine Hearts 12ct"
    assert lines[1]["product_description"] == "Romaine Hearts 24ct"
    assert lines[2]["product_description"] is None
    assert lines[2]["upc"] is None
    assert lines[2]["gtin"] is None


def test_multi_line_product_override_cannot_replace_each_description(
    client: TestClient, captured_payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    dedup_calls = []

    def _dedup(sender_id, receiver_id, isa13):
        dedup_calls.append((sender_id, receiver_id, isa13))
        return False, None

    monkeypatch.setattr(edi_ingestion_routes, "check_and_record_interchange", _dedup)
    raw = (_CORPUS_DIR / "receipt_944.edi").read_bytes()
    response = client.post(
        "/api/v1/ingest/edi/document",
        data={
            "traceability_lot_code": _VALID_FSMA_TLC,
            "tlc_source_reference": _TLC_SOURCE_REFERENCE,
            "tenant_id": TEST_TENANT_ID,
            "product_description": "One description for all lines",
        },
        files={"file": ("receipt_944.edi", raw, "application/edi-x12")},
        headers={"X-Partner-ID": "WALMART"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "edi_overrides_with_multiple_line_items"
    assert "payload" not in captured_payload
    assert len(dedup_calls) == 1
    corrected = _post(client, raw, name="receipt_944.edi")
    assert corrected.status_code == 201, corrected.text
    assert corrected.json()["ingestion_result"]["accepted"] == 3
    assert len(dedup_calls) == 2


def test_unknown_transaction_set_keeps_the_same_error(client: TestClient, captured_payload: dict) -> None:
    raw = (_CORPUS_DIR / "receipt_944.edi").read_bytes().replace(b"ST*944*", b"ST*943*")
    captured_payload.clear()
    response = _post(client, raw, name="unknown.edi")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail == (f"Unsupported or unrecognized transaction set. Supported: {sorted(_SUPPORTED_TRANSACTION_SETS)}")
    assert detail.startswith("Unsupported or unrecognized transaction set. Supported:")
    assert "943" not in detail
    for code in ("810", "850", "856", "861", "944", "945"):
        assert code in detail
    assert "payload" not in captured_payload
