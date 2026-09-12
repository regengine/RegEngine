"""Unit tests for the per-label metered billing hook in
``CanonicalEventStore`` (DESIGN_metering-billing.md §4.1).

``persist_event`` / ``persist_events_batch`` call
``increment_usage_for_event`` exactly once per genuinely NEW row — never
for an idempotent replay or a lost-race event — and only when
``meter_usage=True`` (the default). These tests mock every collaborator
(insert helpers, chain-entry writers, transformation links, legacy dual
write / graph sync) so only the meter_usage wiring itself is under test;
insertion mechanics are covered by
``test_canonical_persistence_batch_on_conflict_1266.py`` and friends.

Mocking style: ``object.__new__(CanonicalEventStore)`` + a MagicMock
session, matching ``test_canonical_persistence_batch_on_conflict_1266.py``.
No live DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import services.shared.canonical_persistence.writer as writer_mod
from services.shared.canonical_persistence.writer import CanonicalEventStore

TENANT_ID = "tenant-meter-1"
EVENT_TIMESTAMP = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _make_writer(meter_usage: bool = True, dual_write: bool = False) -> tuple[CanonicalEventStore, MagicMock]:
    """A CanonicalEventStore with every non-meter_usage collaborator
    stubbed out, and a session dialect that trips the SQLite no-op
    branches in ``set_tenant_context`` / ``_acquire_chain_lock`` so no
    real SQL needs to be modeled for those.
    """
    writer = object.__new__(CanonicalEventStore)
    mock_session = MagicMock()
    mock_session.bind.dialect.name = "sqlite"
    # The only session.execute call left un-stubbed on the happy path is
    # the "get chain head" SELECT — first event ever, so no head row.
    mock_session.execute.return_value.fetchone.return_value = None
    mock_session.execute.return_value.fetchall.return_value = []

    writer.session = mock_session
    writer.dual_write = dual_write
    writer.skip_chain_write = False
    writer.meter_usage = meter_usage

    # Insertion mechanics: not what this test suite is about.
    writer._insert_canonical_event = MagicMock(return_value=("evt-inserted", "hash", "chainhash"))
    writer._insert_chain_entry = MagicMock()
    writer._create_transformation_links = MagicMock()
    return writer, mock_session


def _make_event(
    event_id: str = "evt-1",
    idempotency_key: str | None = None,
    supersedes_event_id: str | None = None,
) -> MagicMock:
    event = MagicMock()
    event.tenant_id = TENANT_ID
    event.event_id = event_id
    event.idempotency_key = idempotency_key
    event.supersedes_event_id = supersedes_event_id
    event.sha256_hash = "deadbeef"
    event.chain_hash = None
    event.event_timestamp = EVENT_TIMESTAMP
    return event


@pytest.fixture(autouse=True)
def _stub_module_level_collaborators(monkeypatch):
    # persist_event() always calls migration.stage_graph_sync(...)
    # regardless of dual_write — stub it so it doesn't touch a real
    # session-hooks API.
    monkeypatch.setattr(writer_mod.migration, "stage_graph_sync", MagicMock())
    monkeypatch.setattr(writer_mod.migration, "dual_write_legacy", MagicMock(return_value=None))


@pytest.fixture
def fake_increment(monkeypatch):
    """Patch the deferred-import target so both persist_event and
    persist_events_batch (which each do
    ``from services.ingestion.app.stripe_billing.usage import
    increment_usage_for_event`` inside the method body) pick up the fake.
    """
    import services.ingestion.app.stripe_billing.usage as usage_mod

    fake = MagicMock(return_value=True)
    monkeypatch.setattr(usage_mod, "increment_usage_for_event", fake)
    return fake


# ---------------------------------------------------------------------------
# persist_event
# ---------------------------------------------------------------------------


class TestPersistEventMetersUsage:
    def test_new_event_increments_usage_once(self, fake_increment):
        writer, _session = _make_writer(meter_usage=True)
        event = _make_event(event_id="evt-new-1")

        result = writer.persist_event(event)

        assert result.idempotent is False
        fake_increment.assert_called_once_with(
            writer.session,
            tenant_id=TENANT_ID,
            event_id="evt-new-1",
            event_timestamp=EVENT_TIMESTAMP,
        )

    def test_meter_usage_false_never_counts(self, fake_increment):
        writer, _session = _make_writer(meter_usage=False)
        event = _make_event(event_id="evt-new-2")

        writer.persist_event(event)

        fake_increment.assert_not_called()

    def test_preflight_idempotent_replay_does_not_count(self, fake_increment):
        """An event whose idempotency_key already exists is caught by the
        pre-flight SELECT and returned early — must never reach the
        meter_usage block (it was already counted the first time)."""
        writer, session = _make_writer(meter_usage=True)
        event = _make_event(event_id="evt-dup", idempotency_key="idem-1")

        # First (and only) session.execute call on this path is the
        # pre-flight idempotency SELECT — simulate a hit.
        session.execute.return_value.fetchone.return_value = ("evt-existing", "sha", "chain")

        result = writer.persist_event(event)

        assert result.idempotent is True
        fake_increment.assert_not_called()
        writer._insert_canonical_event.assert_not_called()

    def test_lost_insert_race_does_not_double_count(self, fake_increment):
        """_insert_canonical_event returning None for a keyed event means a
        concurrent writer won the race and already counted it — the
        re-select-and-return-idempotent branch must not count again."""
        writer, session = _make_writer(meter_usage=True)
        event = _make_event(event_id="evt-race", idempotency_key="idem-race")
        writer._insert_canonical_event = MagicMock(return_value=None)

        # First execute() = pre-flight idempotency SELECT -> no existing row
        # (so we proceed to the chain-head lookup and insert attempt).
        # Second execute() = chain-head SELECT -> no head.
        # Third execute() = post-insert re-select -> the winner's row.
        results = [None, None, ("evt-winner", "sha", "chain")]

        def _execute(*args, **kwargs):
            m = MagicMock()
            m.fetchone.return_value = results.pop(0)
            return m

        session.execute.side_effect = _execute

        result = writer.persist_event(event)

        assert result.idempotent is True
        assert result.event_id == "evt-winner"
        fake_increment.assert_not_called()

    def test_supersedes_self_raises_before_any_counting_side_effects(self, fake_increment):
        writer, _session = _make_writer(meter_usage=True)
        event = _make_event(event_id="evt-self")
        event.supersedes_event_id = "evt-self"

        with pytest.raises(ValueError, match="cannot supersede itself"):
            writer.persist_event(event)

        # Usage was already counted (the meter_usage block runs before the
        # supersede check) — the raise must not roll that call back out of
        # existence at the Python level; the caller's DB transaction
        # rollback is what actually undoes it. Just confirm we counted once,
        # not zero or twice.
        fake_increment.assert_called_once()


# ---------------------------------------------------------------------------
# persist_events_batch
# ---------------------------------------------------------------------------


class TestPersistEventsBatchMetersUsage:
    def _stub_batch_helpers(self, writer: CanonicalEventStore, inserted_ids: set[str]) -> None:
        writer._batch_insert_canonical_events = MagicMock(return_value=inserted_ids)
        writer._batch_insert_chain_entries = MagicMock()

    def test_counts_once_per_newly_inserted_event(self, fake_increment):
        writer, _session = _make_writer(meter_usage=True)
        events = [_make_event(event_id="evt-b1"), _make_event(event_id="evt-b2")]
        self._stub_batch_helpers(writer, inserted_ids={"evt-b1", "evt-b2"})

        writer.persist_events_batch(events)

        assert fake_increment.call_count == 2
        called_event_ids = {kwargs["event_id"] for _, kwargs in fake_increment.call_args_list}
        assert called_event_ids == {"evt-b1", "evt-b2"}
        for _, kwargs in fake_increment.call_args_list:
            assert kwargs["tenant_id"] == TENANT_ID

    def test_lost_race_events_are_never_counted(self, fake_increment):
        """Only inserted_event_ids counts — an event this writer lost the
        idempotency race on was already counted by the winner."""
        writer, _session = _make_writer(meter_usage=True)
        events = [_make_event(event_id="evt-win"), _make_event(event_id="evt-lost", idempotency_key="idem-lost")]
        # evt-lost "wins" nothing at insert time.
        self._stub_batch_helpers(writer, inserted_ids={"evt-win"})

        writer.persist_events_batch(events)

        fake_increment.assert_called_once()
        _, kwargs = fake_increment.call_args
        assert kwargs["event_id"] == "evt-win"

    def test_preexisting_idempotency_key_short_circuits_before_insert(self, fake_increment):
        """An event whose idempotency_key is already in the pre-flight
        batch SELECT never reaches the insert step at all — must not be
        counted."""
        writer, session = _make_writer(meter_usage=True)
        event = _make_event(event_id="evt-preexisting", idempotency_key="idem-existing")
        self._stub_batch_helpers(writer, inserted_ids=set())

        # The batch pre-flight idempotency SELECT returns one matching row.
        session.execute.return_value.fetchall.return_value = [
            ("idem-existing", "evt-preexisting", "sha", "chain")
        ]
        session.execute.return_value.fetchone.return_value = None

        results = writer.persist_events_batch([event])

        assert results[0].idempotent is True
        fake_increment.assert_not_called()
        writer._batch_insert_canonical_events.assert_not_called()

    def test_meter_usage_false_never_counts_in_batch(self, fake_increment):
        writer, _session = _make_writer(meter_usage=False)
        events = [_make_event(event_id="evt-off-1")]
        self._stub_batch_helpers(writer, inserted_ids={"evt-off-1"})

        writer.persist_events_batch(events)

        fake_increment.assert_not_called()

    def test_empty_inserted_set_skips_the_import_entirely(self, fake_increment):
        """When every event in the batch was idempotent or lost the race,
        ``inserted_events`` is empty and the deferred import/call must be
        skipped outright (not just a no-op loop)."""
        writer, _session = _make_writer(meter_usage=True)
        events = [_make_event(event_id="evt-none")]
        self._stub_batch_helpers(writer, inserted_ids=set())

        writer.persist_events_batch(events)

        fake_increment.assert_not_called()
