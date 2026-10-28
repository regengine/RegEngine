"""SEL-597: canonical persistence replay contracts, without business records.

Inputs are synthesized from required model fields, schema bounds and enums.
Only the SQL/storage boundary is mocked, following ingestion's existing
MagicMock session pattern. These are orchestration tests, not DB/RLS proofs.

Cases left out
--------------
2: compute_idempotency_key excludes event_id; different IDs with identical
content are silently merged. No possible-duplicate flag exists here.
3: KDE changes produce a different key; persist_event has no event-ID conflict
comparison or conflict-to-gap-report path. A DB uniqueness error is not that
contract.
4 (upload counter): batch results expose idempotent, but IngestionRun has no
duplicate counter. Only cross-batch persistence/counting is covered below.
5: raw-lot key preservation is covered, but the key omits product_reference;
there is no GTIN-paired lenient-lot merge policy in this writer. No GTIN is made up.
7: no file is fabricated. compliance_score queries the legacy store and its
endpoint needs configured services; canonical replay alone cannot establish
file-level score idempotency with this isolated harness.
"""

from datetime import datetime, timezone
from enum import Enum
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from shared.canonical_event import TraceabilityEvent
from shared.canonical_persistence import CanonicalEventStore


def _event():
    values = {}
    for name, field in TraceabilityEvent.model_fields.items():
        if not field.is_required():
            continue
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, Enum):
            values[name] = next(iter(kind))
        elif kind is UUID:
            values[name] = uuid4()
        elif kind is datetime:
            values[name] = datetime.now(timezone.utc)
        elif kind is float:
            values[name] = next(bound.ge for bound in field.metadata if hasattr(bound, "ge"))
        elif kind is str:
            values[name] = str(uuid4())  # Opaque references, never product numbers.
        else:
            raise AssertionError(f"Unhandled required schema field: {name}")
    return TraceabilityEvent(**values)


@pytest.fixture
def store(monkeypatch):
    """Keep production replay decisions; replace only storage and side effects."""
    session = MagicMock()
    writer = CanonicalEventStore(session, dual_write=False, meter_usage=False)
    rows = {}

    def execute(statement, params=None):
        result = MagicMock()
        sql = str(statement)
        if "idempotency_key IN" in sql:
            assert "tenant_id = :tid" in sql
            result.fetchall.return_value = [
                (key, *row) for (tenant, key), row in rows.items() if tenant == params["tid"] and key in params["keys"]
            ]
        elif "WHERE idempotency_key =" in sql:
            assert "tenant_id = :tid" in sql
            result.fetchone.return_value = rows.get((params["tid"], params["key"]))
        elif "FROM fsma.hash_chain" in sql:
            result.fetchone.return_value = None
        else:
            raise AssertionError(f"Unexpected storage operation: {sql}")
        return result

    def insert(event):
        assert all(row[0] != str(event.event_id) for row in rows.values()), "Duplicate event_id primary key"
        row = (str(event.event_id), event.sha256_hash, event.chain_hash)
        rows[(str(event.tenant_id), event.idempotency_key)] = row
        return row

    session.execute.side_effect = execute
    monkeypatch.setattr(writer, "set_tenant_context", MagicMock())
    monkeypatch.setattr(writer, "_acquire_chain_lock", MagicMock())
    monkeypatch.setattr(writer, "_insert_canonical_event", insert)
    monkeypatch.setattr(writer, "_batch_insert_canonical_events", lambda events: {insert(event)[0] for event in events})
    monkeypatch.setattr(writer, "_insert_chain_entry", MagicMock())
    monkeypatch.setattr(writer, "_batch_insert_chain_entries", MagicMock())
    monkeypatch.setattr("shared.canonical_persistence.legacy_dual_write.stage_graph_sync", MagicMock())
    return writer, rows


def test_identical_event_replay_reports_duplicate_without_another_insert(store):
    writer, rows = store
    event = _event()
    first = writer.persist_event(event)
    before = rows.copy()
    replay = writer.persist_event(event.model_copy(deep=True))
    assert first.success and not first.idempotent
    assert replay.success and replay.idempotent and not replay.errors
    assert replay.event_id == first.event_id
    assert rows == before
    assert writer._insert_chain_entry.call_count == len(before)


def test_second_batch_reports_duplicate_and_preserves_event_count(store):
    writer, rows = store
    event = _event()
    first = writer.persist_events_batch([event])
    before = rows.copy()
    second = writer.persist_events_batch([event.model_copy(deep=True)])
    assert all(result.success and not result.idempotent for result in first)
    assert all(result.success and result.idempotent and not result.errors for result in second)
    assert sum(result.idempotent for result in second) == len(first)
    assert [result.event_id for result in second] == [result.event_id for result in first]
    assert rows == before


def test_raw_lot_whitespace_is_not_normalized_into_a_duplicate(store):
    writer, rows = store
    event = _event()
    variant = event.model_copy(
        update={"event_id": uuid4(), "traceability_lot_code": f" {event.traceability_lot_code} ", "sha256_hash": None}
    )
    assert event.traceability_lot_code.strip() == variant.traceability_lot_code.strip()
    assert event.compute_idempotency_key() != variant.compute_idempotency_key()
    results = writer.persist_events_batch([event, variant])
    assert all(result.success and not result.idempotent for result in results)
    assert len(rows) == len(results)


def test_replay_lookup_is_scoped_to_tenant(store):
    writer, rows = store
    event = _event()
    first = writer.persist_event(event)
    before = rows.copy()
    other = event.model_copy(update={"event_id": uuid4(), "tenant_id": uuid4(), "sha256_hash": None})
    second = writer.persist_event(other)
    assert event.compute_idempotency_key() == other.compute_idempotency_key()
    assert first.success and second.success
    assert not first.idempotent and not second.idempotent
    assert all(rows[key] == value for key, value in before.items())
    assert set(rows) - set(before) == {(str(other.tenant_id), other.idempotency_key)}
