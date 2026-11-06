"""An EDI interchange stores every event or none.

A partly stored interchange could not be retried: the claim stayed, a resend got
a 409, and releasing the claim is unsafe because event keys carry line numbers.
Only storage is faked here, with a journal that savepoints really undo.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir.parent))

from shared.paths import ensure_shared_importable  # noqa: E402

ensure_shared_importable()
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_compat as webhook_compat  # noqa: E402
import shared.canonical_event as canonical_event  # noqa: E402
import shared.canonical_persistence as canonical_persistence  # noqa: E402
import shared.cte_persistence as cte_persistence  # noqa: E402
import shared.rules_engine as rules_engine  # noqa: E402
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload  # noqa: E402

TENANT = "00000000-0000-0000-0000-000000000123"


class _Savepoint:
    def __init__(self, journal: list[Any]) -> None:
        self.journal = journal
        self.mark = len(journal)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        del self.journal[self.mark :]


class _Session:
    def __init__(self, journal: list[Any]) -> None:
        self.journal = journal

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self.journal)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        self.journal.clear()

    def close(self) -> None:
        return None


class _Stored:
    sha256_hash = "h" * 64
    chain_hash = "c" * 64

    def __init__(self, event_id: str) -> None:
        self.event_id = event_id


class _Canonical:
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


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {"journal": [], "fail_on": None, "published": []}
    journal = state["journal"]

    class _Persistence:
        def __init__(self, db: Any) -> None:
            self.db = db

        def store_event(self, **kwargs: Any) -> _Stored:
            lot = kwargs["traceability_lot_code"]
            if lot == state["fail_on"]:
                raise RuntimeError("storage failed")
            journal.append(("cte", lot))
            return _Stored(f"00000000-0000-0000-0000-{len(journal):012d}")

    class _CanonicalStore:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def persist_event(self, event: Any) -> None:
            journal.append(("canonical", event.event_id))

    class _NoRules:
        def __init__(self, db: Any) -> None:
            return None

        def evaluate_event(self, *args: Any, **kwargs: Any) -> None:
            return None

    def _session() -> Iterator[_Session]:
        yield _Session(journal)

    monkeypatch.setattr(webhook_compat, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_get_db_session", _session)
    monkeypatch.setattr(webhook_compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(
        webhook_compat,
        "_publish_graph_sync",
        lambda event_id, event, tenant_id: state["published"].append(event_id),
    )
    monkeypatch.setattr(cte_persistence, "CTEPersistence", _Persistence)
    monkeypatch.setattr(canonical_event, "normalize_webhook_event", lambda *a, **k: _Canonical())
    monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _CanonicalStore)
    monkeypatch.setattr(rules_engine, "RulesEngine", _NoRules)
    yield state


def _event(lot: str) -> IngestEvent:
    return IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code=lot,
        product_description="Romaine Hearts",
        quantity=200,
        unit_of_measure="cases",
        location_name="Valley Fresh Farms",
        timestamp=datetime(2026, 3, 10, 12, tzinfo=timezone.utc).isoformat(),
        kdes={
            "ship_date": "2026-03-10",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "Metro Distribution Center",
            "reference_document": "BOL-9001",
            "tlc_source_reference": "0061414100001",
        },
    )


async def _ingest(**kwargs: Any) -> Any:
    payload = WebhookPayload(
        source="edi_inbound_856",
        events=[_event("00012345678901-LOT1"), _event("00012345678901-LOT2")],
        tenant_id=TENANT,
    )
    return await webhook_compat.ingest_events(payload, principal_tenant_id=TENANT, **kwargs)


@pytest.mark.asyncio
async def test_one_failed_event_undoes_the_batch_in_both_stores(harness: dict[str, Any]) -> None:
    harness["fail_on"] = "00012345678901-LOT2"

    result = await _ingest(all_or_nothing=True)

    assert (result.accepted, result.rejected) == (0, 2)
    assert harness["journal"] == []
    assert harness["published"] == []
    assert [event.status for event in result.events] == ["rejected", "rejected"]
    assert result.events[0].event_id is None
    assert result.events[0].errors == ["Not stored: another event in this batch was rejected"]


@pytest.mark.asyncio
async def test_a_clean_batch_stores_every_event_and_syncs_after_commit(harness: dict[str, Any]) -> None:
    result = await _ingest(all_or_nothing=True)

    assert (result.accepted, result.rejected) == (2, 0)
    assert sum(1 for kind, _ in harness["journal"] if kind == "cte") == 2
    assert harness["published"] == [event.event_id for event in result.events]


@pytest.mark.asyncio
async def test_other_callers_keep_per_event_acceptance(harness: dict[str, Any]) -> None:
    harness["fail_on"] = "00012345678901-LOT2"

    result = await _ingest()

    assert (result.accepted, result.rejected) == (1, 1)
    assert ("cte", "00012345678901-LOT1") in harness["journal"]
    assert len(harness["published"]) == 1
