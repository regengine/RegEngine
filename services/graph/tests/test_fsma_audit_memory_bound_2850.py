"""#2850 — the in-process FSMAAuditLog must not grow without bound.

``get_audit_log()`` returns a process-global singleton. In the consolidated
monolith that process is long-lived (Railway never recycles it), and every
``KDE_READ`` on a traceability route appends an entry that retains its full
``diff`` payload. Unbounded, the entry list and the two index dicts are
monotonic heap growth proportional to lifetime audit volume — and reads
amplify it, since ``get_by_target``/``get_by_tenant`` log a READ entry of
their own before querying.

Postgres is the source of truth for every query path, so bounding the
in-memory copy costs nothing a working deployment relies on. These tests pin
three things the fix has to get right at once:

1. the entry container is capped;
2. the ``_by_target``/``_by_tenant`` indexes are evicted *with* it (bounding
   only the entries would leave the dicts growing forever);
3. the checksum chain still links across an eviction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.fsma_audit as fsma_audit  # noqa: E402
from app.fsma_audit import FSMAAuditAction, FSMAAuditActorType, FSMAAuditDiff, FSMAAuditLog  # noqa: E402


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Keep these tests hermetic and fast — no audit DB, no persistence."""
    monkeypatch.setattr(fsma_audit, "_get_audit_db_engine", lambda: None)
    monkeypatch.setattr(fsma_audit, "_persist_audit_entry", lambda _entry: False)


def _log_n(log: FSMAAuditLog, n: int, *, target_prefix: str = "LOT-", tenant: str = "tenant-a") -> None:
    for i in range(n):
        log.log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id=f"{target_prefix}{i:04d}",
            tenant_id=tenant,
            diff=[FSMAAuditDiff("record_ids", None, [f"{target_prefix}{i:04d}"])],
            actor_type=FSMAAuditActorType.API,
        )


def _index_size(index) -> int:
    return sum(len(ids) for ids in index.values())


def test_entries_are_capped(monkeypatch):
    """Logging far past the cap keeps only the most recent window."""
    log = FSMAAuditLog(max_entries=10)

    _log_n(log, 250)

    assert log.count() == 10, f"in-memory audit log grew to {log.count()} entries with a cap of 10"
    retained = [e.target_id for e in log.get_all()]
    assert retained[0] == "LOT-0240"
    assert retained[-1] == "LOT-0249"


def test_plain_constructor_is_bounded_by_env(monkeypatch):
    """Purely behavioural: no new constructor argument, no new helper.

    A default-constructed log — the shape every existing caller uses — must
    stop growing. Before the fix this reached 250 entries and kept climbing.
    The env var is spelled out rather than read off the module so this test
    fails on its assertion, not on a missing attribute.
    """
    monkeypatch.setenv("FSMA_AUDIT_MEMORY_MAX_ENTRIES", "10")
    log = FSMAAuditLog()

    _log_n(log, 250)

    assert log.count() == 10, f"unbounded in-memory audit log: {log.count()} entries retained"


def test_target_index_is_evicted_with_the_entries():
    """Bounding the entries alone is not enough — the indexes must shrink too.

    Each event has a distinct target, so an index that is never evicted keeps
    one key *and* one event_id per event logged, forever.
    """
    log = FSMAAuditLog(max_entries=10)

    _log_n(log, 250)

    assert len(log._by_target) == 10, f"_by_target holds {len(log._by_target)} keys for a 10-entry cap"
    assert _index_size(log._by_target) == 10
    assert "LOT-0000" not in log._by_target, "evicted target key was left behind"
    assert "LOT-0249" in log._by_target, "most recent target is missing from the index"


def test_tenant_index_is_evicted_with_the_entries():
    """``_by_tenant`` shares one key across many events, so the *ids* are what
    grow there. They must be evicted alongside the entries."""
    log = FSMAAuditLog(max_entries=10)

    _log_n(log, 250, tenant="tenant-a")

    assert _index_size(log._by_tenant) == 10, (
        f"_by_tenant retained {_index_size(log._by_tenant)} event ids for a 10-entry cap"
    )
    live_ids = {e.event_id for e in log.get_all()}
    assert set(log._by_tenant["tenant-a"]) == live_ids, "index references entries that were already evicted"


def test_index_ids_always_reference_live_entries():
    """No index entry may outlive the entry it points at, for any key shape."""
    log = FSMAAuditLog(max_entries=25)

    # Repeat a small set of targets so keys are shared and re-added after
    # eviction, and spread across tenants.
    for i in range(400):
        log.log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id=f"LOT-{i % 7}",
            tenant_id=f"tenant-{i % 3}",
        )

    live_ids = {e.event_id for e in log.get_all()}
    assert len(live_ids) == 25

    for index_name, index in (("_by_target", log._by_target), ("_by_tenant", log._by_tenant)):
        indexed = [event_id for ids in index.values() for event_id in ids]
        assert len(indexed) == len(live_ids), f"{index_name} holds {len(indexed)} ids for {len(live_ids)} entries"
        assert set(indexed) == live_ids, f"{index_name} references evicted entries"
        assert all(ids for ids in index.values()), f"{index_name} kept an emptied key"


def test_checksum_chain_survives_eviction():
    """Eviction trims the front of the window; the chain must still link."""
    log = FSMAAuditLog(max_entries=10)

    _log_n(log, 250)

    entries = log.get_all()
    for previous, current in zip(entries, entries[1:]):
        assert current.previous_checksum == previous.checksum, "chain broke across the retained window"

    result = log.verify_chain_integrity()
    assert result["is_valid"], result["violations"]
    assert result["total_entries"] == 10


def test_clear_still_empties_everything():
    log = FSMAAuditLog(max_entries=10)
    _log_n(log, 30)

    log.clear()

    assert log.count() == 0
    assert not log._by_target
    assert not log._by_tenant


class TestCapResolution:
    """``FSMA_AUDIT_MEMORY_MAX_ENTRIES`` overrides the default; bad values do
    not silently disable the log."""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(fsma_audit._MEMORY_MAX_ENTRIES_ENV, raising=False)
        assert fsma_audit._resolve_max_memory_entries() == fsma_audit._DEFAULT_MEMORY_MAX_ENTRIES

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(fsma_audit._MEMORY_MAX_ENTRIES_ENV, "42")
        assert fsma_audit._resolve_max_memory_entries() == 42
        assert FSMAAuditLog()._entries.maxlen == 42

    def test_explicit_argument_wins(self, monkeypatch):
        monkeypatch.setenv(fsma_audit._MEMORY_MAX_ENTRIES_ENV, "42")
        assert fsma_audit._resolve_max_memory_entries(7) == 7

    @pytest.mark.parametrize("bad", ["0", "-5", "not-a-number", "  "])
    def test_bad_values_fall_back_to_the_default(self, monkeypatch, bad):
        """``maxlen=0`` would drop every entry and break both the checksum
        chain and the DB-outage fallback — never accept it."""
        monkeypatch.setenv(fsma_audit._MEMORY_MAX_ENTRIES_ENV, bad)
        assert fsma_audit._resolve_max_memory_entries() == fsma_audit._DEFAULT_MEMORY_MAX_ENTRIES

    def test_default_singleton_is_bounded(self, monkeypatch):
        """The process-global instance — the one #2850 is about — is capped."""
        monkeypatch.delenv(fsma_audit._MEMORY_MAX_ENTRIES_ENV, raising=False)
        fsma_audit.reset_audit_log()
        try:
            maxlen = fsma_audit.get_audit_log()._entries.maxlen
        finally:
            fsma_audit.reset_audit_log()
        assert maxlen == fsma_audit._DEFAULT_MEMORY_MAX_ENTRIES
