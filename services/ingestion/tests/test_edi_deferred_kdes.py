"""EDI shipments without a TLC source reference are stored with an open gap.

X12 has no element for ``tlc_source_reference``. The EDI routes defer that one
KDE on shipping events: the event is stored, its result names the gap, and a
``missing_kde`` gap stays open. Everything else keeps the strict gate, and the
exemption must be unreachable from anything the sender controls.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from services.ingestion.app import webhook_compat as wc
from services.ingestion.app.edi_ingestion import routes as edi_routes
from services.ingestion.app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from shared.data_gap_tracking import GAP_KIND_MISSING_KDE, Gap

TENANT = "11111111-1111-1111-1111-111111111111"
TLC = "00012345678901-LOT001"
EVENT_HASH = "a" * 64
TLC_SOURCE_GAP = Gap(GAP_KIND_MISSING_KDE, "tlc_source_reference")


class _Session:
    def begin_nested(self) -> "_Session":
        return self

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(stored=[], outcomes=[])

    class _Persistence:
        def __init__(self, db: Any) -> None:
            return None

        def store_event(self, **kwargs: Any) -> SimpleNamespace:
            state.stored.append(kwargs)
            return SimpleNamespace(event_id="ev-1", sha256_hash=EVENT_HASH, chain_hash="c" * 64)

    def _no_canonical(*_args: Any, **_kwargs: Any) -> None:
        raise ValueError("canonical write not under test")

    def _sessions():
        yield _Session()

    import shared.canonical_event as canonical_event
    import shared.cte_persistence as cte_persistence

    monkeypatch.setattr(cte_persistence, "CTEPersistence", _Persistence)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", _no_canonical)
    monkeypatch.setattr(wc, "_get_db_session", _sessions)
    monkeypatch.setattr(wc, "_check_rate_limit", lambda _tenant: None)
    monkeypatch.setattr(wc, "_verify_api_key_sync", lambda **_kwargs: None)
    monkeypatch.setattr(wc, "_generate_alerts", lambda _event: [])
    monkeypatch.setattr(wc, "_publish_graph_sync", lambda *_args: None)
    monkeypatch.setattr(wc, "record_outcomes", lambda _db, _tenant, outcomes: state.outcomes.extend(outcomes))
    return state


def _shipment(**kde_overrides: Any) -> IngestEvent:
    kdes = {
        "ship_date": "2026-03-10",
        "ship_from_location": "Valley Fresh Farms",
        "ship_to_location": "Metro Distribution Center",
        "reference_document": "BOL-9001",
        **kde_overrides,
    }
    return IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code=TLC,
        product_description="Romaine 12CT",
        quantity=200,
        unit_of_measure="cases",
        timestamp="2026-03-10T12:00:00Z",
        location_name="Valley Fresh Farms",
        kdes={key: value for key, value in kdes.items() if value is not None},
    )


def _receipt() -> IngestEvent:
    return IngestEvent(
        cte_type=WebhookCTEType.RECEIVING,
        traceability_lot_code=TLC,
        product_description="Romaine 12CT",
        quantity=200,
        unit_of_measure="cases",
        timestamp="2026-03-10T12:00:00Z",
        location_name="Metro Distribution Center",
        kdes={
            "receive_date": "2026-03-10",
            "receiving_location": "Metro Distribution Center",
            "immediate_previous_source": "Valley Fresh Farms",
            "reference_document": "BOL-9001",
        },
    )


def _ingest(event: IngestEvent, *, source: str = "edi_856_inbound", **kwargs: Any):
    payload = WebhookPayload(tenant_id=TENANT, source=source, events=[event])
    return asyncio.run(
        wc.ingest_events(
            payload,
            principal_tenant_id=TENANT,
            x_regengine_api_key="test-key",  # pragma: allowlist secret — synthetic test fixture only
            **kwargs,
        )
    )


def test_deferred_kde_stores_event_and_keeps_gap_open(harness) -> None:
    response = _ingest(_shipment(), deferred_kdes=edi_routes._EDI_DEFERRED_KDES)

    assert (response.accepted, response.rejected) == (1, 0)
    assert response.events[0].open_gaps == ["tlc_source_reference"]
    assert len(harness.stored) == 1

    outcome = harness.outcomes[0]
    assert outcome.gaps == (TLC_SOURCE_GAP,)
    # A receipt would close every open gap on this lot, including its own.
    assert outcome.closing_record_id is None
    assert outcome.closing_record_hash is None


def test_supplied_reference_stores_event_and_closes_gaps(harness) -> None:
    response = _ingest(
        _shipment(tlc_source_reference="PACK-0310"),
        deferred_kdes=edi_routes._EDI_DEFERRED_KDES,
    )

    assert response.accepted == 1
    assert response.events[0].open_gaps == []
    outcome = harness.outcomes[0]
    assert outcome.gaps == ()
    assert (outcome.closing_record_id, outcome.closing_record_hash) == ("ev-1", EVENT_HASH)


def test_another_missing_kde_still_rejects(harness) -> None:
    response = _ingest(_shipment(reference_document=None), deferred_kdes=edi_routes._EDI_DEFERRED_KDES)

    assert (response.accepted, response.rejected) == (0, 1)
    assert harness.stored == []
    assert set(harness.outcomes[0].gaps) == {
        TLC_SOURCE_GAP,
        Gap(GAP_KIND_MISSING_KDE, "reference_document"),
    }


def test_receiving_is_not_deferred(harness) -> None:
    response = _ingest(_receipt(), deferred_kdes=edi_routes._EDI_DEFERRED_KDES)

    assert (response.accepted, response.rejected) == (0, 1)
    assert harness.stored == []


def test_error_with_no_gap_key_still_rejects(harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wc, "_validate_event_kdes", lambda _event: ["   "])

    response = _ingest(_shipment(), deferred_kdes=edi_routes._EDI_DEFERRED_KDES)

    assert (response.accepted, response.rejected) == (0, 1)
    assert harness.stored == []


def test_sender_cannot_claim_the_exemption(harness) -> None:
    """EDI-looking source and KDEs change nothing without the server-side argument."""
    response = _ingest(
        _shipment(edi_transaction_set="856", deferred_kdes=["tlc_source_reference"]),
        source="edi_856_inbound",
    )

    assert (response.accepted, response.rejected) == (0, 1)
    assert harness.stored == []
    assert response.events[0].open_gaps == []
