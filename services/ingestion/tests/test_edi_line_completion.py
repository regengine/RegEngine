"""A resend that only supplies a deferred KDE completes the stored line.

Owner decision recorded in ADR-007: an EDI shipment stored without its
``tlc_source_reference`` (X12 cannot carry it) may be completed by resending the
same line with the reference. The completed line is stored as a new event that
supersedes the old one, because ``fsma.cte_events`` is append-only and its hash
covers every KDE. Any other change to a stored line stays refused with 409.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from services.ingestion.app import webhook_compat as wc
from services.ingestion.app.edi_ingestion import routes as edi_routes
from services.ingestion.app.edi_line_identity import (
    LINE_CONFLICT_ERROR,
    StoredLine,
    completes_stored_line,
    identify_lines,
)
from services.ingestion.app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload

TENANT = "11111111-1111-1111-1111-111111111111"
DEFERRED = edi_routes._EDI_DEFERRED_KDES[WebhookCTEType.SHIPPING]
STORED_EVENT = "00000000-0000-0000-0000-0000000000a1"
STORED_CANONICAL = "00000000-0000-0000-0000-0000000000c1"
NEW_CANONICAL = "00000000-0000-0000-0000-0000000000c2"


def _line(quantity: float = 200, **kdes: Any) -> IngestEvent:
    base = {
        "edi_transaction_set": "856",
        "edi_sender_id": "SENDERID",
        "edi_receiver_id": "RECEIVERID",
        "asn_number": "ASN-12345",
        "ship_date": "2026-03-10",
        "ship_from_location": "Valley Fresh Farms",
        "ship_to_location": "Metro Distribution Center",
        "reference_document": "BOL-9001",
        **kdes,
    }
    return IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code="00012345678901-LOT001",
        product_description="Romaine 12CT",
        quantity=quantity,
        unit_of_measure="cases",
        timestamp="2026-03-10T12:00:00Z",
        location_name="Valley Fresh Farms",
        kdes={key: value for key, value in base.items() if value is not None},
    )


def _stored(event: IngestEvent, canonical_event_id: str | None = STORED_CANONICAL) -> StoredLine:
    line = identify_lines([event])[0]
    return StoredLine(line.content_digest, STORED_EVENT, "a" * 64, "c" * 64, canonical_event_id)


INCOMPLETE = _line()


# --- detection ----------------------------------------------------------------


def test_supplying_the_deferred_kde_completes_the_stored_line() -> None:
    assert completes_stored_line(_line(tlc_source_reference="PACK-0310"), _stored(INCOMPLETE), DEFERRED)


def test_a_stored_empty_value_also_counts_as_missing() -> None:
    stored = _stored(_line(tlc_source_reference=""))
    stored_with_none = StoredLine(
        identify_lines([INCOMPLETE.model_copy(update={"kdes": {**INCOMPLETE.kdes, "tlc_source_reference": None}})])[
            0
        ].content_digest,
        STORED_EVENT,
        canonical_event_id=STORED_CANONICAL,
    )
    completed = _line(tlc_source_reference="PACK-0310")
    assert completes_stored_line(completed, stored, DEFERRED)
    assert completes_stored_line(completed, stored_with_none, DEFERRED)


@pytest.mark.parametrize(
    "resend",
    [
        pytest.param(_line(quantity=150, tlc_source_reference="PACK-0310"), id="also-changes-quantity"),
        pytest.param(_line(tlc_source_reference="PACK-0310", carrier="Other"), id="also-adds-another-kde"),
        pytest.param(_line(), id="supplies-nothing"),
        pytest.param(_line(tlc_source_reference="   "), id="supplies-blank"),
    ],
)
def test_anything_else_is_not_a_completion(resend: IngestEvent) -> None:
    assert not completes_stored_line(resend, _stored(INCOMPLETE), DEFERRED)


def test_a_line_that_already_had_the_kde_is_not_completed_again() -> None:
    stored = _stored(_line(tlc_source_reference="PACK-0310"))
    assert not completes_stored_line(_line(tlc_source_reference="OTHER"), stored, DEFERRED)


def test_a_line_stored_without_its_canonical_link_cannot_be_completed() -> None:
    stored = _stored(INCOMPLETE, canonical_event_id=None)
    assert not completes_stored_line(_line(tlc_source_reference="PACK-0310"), stored, DEFERRED)


def test_receiving_defers_nothing_so_it_is_never_completed() -> None:
    assert not completes_stored_line(_line(tlc_source_reference="PACK-0310"), _stored(INCOMPLETE), frozenset())


# --- ingest -------------------------------------------------------------------


class _Savepoint:
    def __init__(self, state: SimpleNamespace) -> None:
        self.state = state
        self.stored_before = len(state.stored)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        del self.state.stored[self.stored_before :]


class _Session:
    def __init__(self, state: SimpleNamespace) -> None:
        self.state = state

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self.state)

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _Registry:
    """Holds one stored line and records what ingest asks of it."""

    def __init__(self, stored: StoredLine) -> None:
        self.stored = stored
        self.recorded: list[tuple] = []
        self.superseded: list[tuple] = []

    def lookup(self, _db: Any, _tenant: str, lines: list) -> dict:
        return {line.identity_key: self.stored for line in lines if line is not None}

    def record(self, _db: Any, _tenant: str, line: Any, event_id: str, canonical_event_id: Any = None) -> None:
        self.recorded.append((event_id, canonical_event_id))

    def supersede(self, _db: Any, _tenant: str, line: Any, stored: StoredLine, event_id: str, canonical: Any) -> None:
        self.superseded.append((stored.event_id, event_id, canonical, line.content_digest))


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(stored=[], canonical=[], outcomes=[], canonical_fails=False)

    class _Persistence:
        def __init__(self, _db: Any) -> None:
            return None

        def store_event(self, **kwargs: Any) -> SimpleNamespace:
            state.stored.append(kwargs)
            return SimpleNamespace(event_id="ev-new", sha256_hash="b" * 64, chain_hash="d" * 64, idempotent=False)

    def _normalize(event: IngestEvent, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        if state.canonical_fails:
            raise ValueError("canonical write failed")
        return SimpleNamespace(
            event_id=NEW_CANONICAL,
            supersedes_event_id=None,
            event_type=SimpleNamespace(value="shipping"),
            traceability_lot_code=event.traceability_lot_code,
            product_reference=None,
            quantity=event.quantity,
            unit_of_measure=event.unit_of_measure,
            from_facility_reference=None,
            to_facility_reference=None,
            from_entity_reference=None,
            to_entity_reference=None,
            kdes={},
        )

    class _CanonicalStore:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def persist_event(self, canonical: Any) -> SimpleNamespace:
            state.canonical.append(canonical)
            return SimpleNamespace(event_id=canonical.event_id, idempotent=False)

    class _Rules:
        def __init__(self, _db: Any) -> None:
            return None

        def evaluate_event(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    def _sessions():
        yield _Session(state)

    import shared.canonical_event as canonical_event
    import shared.canonical_persistence as canonical_persistence
    import shared.cte_persistence as cte_persistence
    import shared.rules_engine as rules_engine

    monkeypatch.setattr(cte_persistence, "CTEPersistence", _Persistence)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", _normalize)
    monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _CanonicalStore)
    monkeypatch.setattr(rules_engine, "RulesEngine", _Rules)
    monkeypatch.setattr(wc, "_get_db_session", _sessions)
    monkeypatch.setattr(wc, "_check_rate_limit", lambda _tenant: None)
    monkeypatch.setattr(wc, "_verify_api_key_sync", lambda **_kwargs: None)
    monkeypatch.setattr(wc, "_generate_alerts", lambda _event: [])
    monkeypatch.setattr(wc, "_publish_graph_sync", lambda *_args: None)
    monkeypatch.setattr(wc, "open_gaps_for_stored_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wc, "record_outcomes", lambda _db, _tenant, outcomes: state.outcomes.extend(outcomes))
    return state


def _ingest(event: IngestEvent, registry: _Registry):
    payload = WebhookPayload(tenant_id=TENANT, source="edi_856_inbound", events=[event])
    return asyncio.run(
        wc.ingest_events(
            payload,
            principal_tenant_id=TENANT,
            x_regengine_api_key="test-key",  # pragma: allowlist secret — synthetic test fixture only
            deferred_kdes=edi_routes._EDI_DEFERRED_KDES,
            all_or_nothing=True,
            edi_lines=registry,
        )
    )


def test_a_completing_resend_supersedes_the_stored_event(harness) -> None:
    registry = _Registry(_stored(INCOMPLETE))
    completed = _line(tlc_source_reference="PACK-0310")

    response = _ingest(completed, registry)

    assert (response.accepted, response.rejected) == (1, 0)
    assert response.events[0].event_id == "ev-new"
    assert response.events[0].open_gaps == []
    assert len(harness.stored) == 1
    assert str(harness.canonical[0].supersedes_event_id) == STORED_CANONICAL
    assert registry.superseded == [
        (STORED_EVENT, "ev-new", NEW_CANONICAL, identify_lines([completed])[0].content_digest)
    ]
    assert registry.recorded == []
    # The new, complete record closes the lot's gap with its own receipt.
    assert [outcome.closing_record_id for outcome in harness.outcomes] == ["ev-new"]


def test_a_correction_is_still_refused(harness) -> None:
    registry = _Registry(_stored(INCOMPLETE))

    with pytest.raises(HTTPException) as refused:
        _ingest(_line(quantity=150, tlc_source_reference="PACK-0310"), registry)

    assert refused.value.status_code == 409
    assert refused.value.detail["error"] == LINE_CONFLICT_ERROR
    assert harness.stored == [] and registry.superseded == []


def test_an_older_line_without_its_canonical_link_is_still_refused(harness) -> None:
    registry = _Registry(_stored(INCOMPLETE, canonical_event_id=None))

    with pytest.raises(HTTPException) as refused:
        _ingest(_line(tlc_source_reference="PACK-0310"), registry)

    assert refused.value.status_code == 409
    assert harness.stored == []


def test_a_completion_is_not_stored_when_the_canonical_write_fails(harness) -> None:
    harness.canonical_fails = True
    registry = _Registry(_stored(INCOMPLETE))

    response = _ingest(_line(tlc_source_reference="PACK-0310"), registry)

    assert (response.accepted, response.rejected) == (0, 1)
    assert harness.stored == [], "the legacy event must roll back with the failed completion"
    assert registry.superseded == []


def test_a_new_line_records_its_canonical_link(harness) -> None:
    registry = _Registry(_stored(INCOMPLETE))
    registry.lookup = lambda *_args: {}

    _ingest(_line(tlc_source_reference="PACK-0310"), registry)

    assert registry.recorded == [("ev-new", NEW_CANONICAL)]


def test_a_batch_replay_close_is_followed_by_a_later_gap(harness) -> None:
    """A replayed complete line queues a close; a later incomplete line must requeue its gap."""
    complete = _line(tlc_source_reference="PACK-0310")
    stored = _stored(complete)
    other_lot = _line(asn_number="ASN-OTHER").model_copy(update={"timestamp": "2026-03-10T13:00:00Z"})
    registry = _Registry(stored)
    complete_identity = identify_lines([complete])[0].identity_key
    registry.lookup = lambda *_args: {complete_identity: stored}

    payload = WebhookPayload(tenant_id=TENANT, source="edi_856_inbound", events=[complete, other_lot])
    asyncio.run(
        wc.ingest_events(
            payload,
            principal_tenant_id=TENANT,
            x_regengine_api_key="test-key",  # pragma: allowlist secret — synthetic test fixture only
            deferred_kdes=edi_routes._EDI_DEFERRED_KDES,
            all_or_nothing=True,
            edi_lines=registry,
        )
    )

    assert [outcome.closing_record_id for outcome in harness.outcomes] == [STORED_EVENT, None]
    assert [gap.gap_key for gap in harness.outcomes[1].gaps] == ["tlc_source_reference"]
