"""Deep QA for shared audit logging: integrity, storage filters, writer seams.

Covers untested behavior in ``shared.audit_logging`` with an emphasis on
tamper-evidence, tenant scoping, and error handling. Tests are fast and
deterministic: no sleeps, no network, no database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from shared.audit_logging import (
    AuditActor,
    AuditContext,
    AuditEvent,
    AuditEventCategory,
    AuditEventType,
    AuditIntegrity,
    AuditLogger,
    AuditResource,
    AuditSeverity,
    InMemoryAuditStorage,
    audit_action,
    verify_audit_chain,
)


@pytest.fixture(autouse=True)
def _audit_key(monkeypatch):
    monkeypatch.setenv("AUDIT_INTEGRITY_KEY", "qa-deep-key")


@pytest.fixture
def actor():
    return AuditActor(actor_id="u-1", actor_type="user", tenant_id="tenant-a")


@pytest.fixture
def restore_singleton():
    saved = AuditLogger._instance
    yield
    AuditLogger._instance = saved


def _event(actor, **overrides):
    params = {
        "event_id": "e-1",
        "timestamp": datetime.now(timezone.utc),
        "event_type": AuditEventType.DATA_READ,
        "category": AuditEventCategory.DATA_ACCESS,
        "severity": AuditSeverity.INFO,
        "actor": actor,
        "action": "read",
        "outcome": "success",
    }
    params.update(overrides)
    return AuditEvent(**params)


class TestIntegrityBasics:
    def test_same_event_hashes_identically_across_instances(self, actor):
        event = _event(actor)
        assert AuditIntegrity().compute_hash(event) == AuditIntegrity().compute_hash(event)

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("AUDIT_INTEGRITY_KEY", raising=False)
        with pytest.raises(ValueError, match="AUDIT_INTEGRITY_KEY"):
            AuditIntegrity()

    def test_unsigned_event_does_not_verify(self, actor):
        assert AuditIntegrity().verify_event(_event(actor)) is False

    def test_sign_threads_previous_hash(self, actor):
        integrity = AuditIntegrity()
        first = integrity.sign_event(_event(actor, event_id="e-1"))
        second = integrity.sign_event(_event(actor, event_id="e-2"))
        assert first.previous_hash is None
        assert second.previous_hash == first.integrity_hash
        assert integrity.verify_chain([first, second]) is True


@pytest.mark.xfail(
    strict=True,
    reason="BUG integrity.py:compute_hash omits severity/message/tags/context, "
    "so tampering with those fields still verifies",
)
@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: setattr(e, "severity", AuditSeverity.DEBUG),
        lambda e: setattr(e, "message", "rewritten by attacker"),
        lambda e: e.tags.append("evil"),
        lambda e: setattr(e, "context", AuditContext(request_id="r-evil")),
    ],
    ids=["severity", "message", "tags", "context"],
)
def test_tampering_with_unsigned_fields_is_detected(actor, mutate):
    integrity = AuditIntegrity()
    event = integrity.sign_event(
        _event(
            actor,
            event_id="e-9",
            severity=AuditSeverity.CRITICAL,
            message="original",
            tags=["a"],
            context=AuditContext(request_id="r-1"),
        )
    )
    assert integrity.verify_event(event) is True
    mutate(event)
    assert integrity.verify_event(event) is False


class TestVerifyAuditChainReport:
    def test_empty_chain_is_valid(self):
        assert verify_audit_chain([], integrity=AuditIntegrity()) == {
            "total_entries": 0,
            "is_valid": True,
            "tampered_entries": [],
        }

    def test_tampered_action_reports_hash_mismatch(self, actor):
        integrity = AuditIntegrity()
        events = [integrity.sign_event(_event(actor, event_id=f"e-{i}")) for i in range(2)]
        events[1].action = "changed"
        report = verify_audit_chain(events, integrity=integrity)
        assert report["is_valid"] is False
        assert report["tampered_entries"] == [{"event_id": "e-1", "index": 1, "issue": "hash_mismatch"}]

    def test_missing_hash_is_reported_with_index(self, actor):
        event = _event(actor)
        report = verify_audit_chain([event], integrity=AuditIntegrity())
        assert report["is_valid"] is False
        (entry,) = report["tampered_entries"]
        assert entry["issue"] == "missing_integrity_hash"
        assert entry["index"] == 0
        assert entry["event_id"] == "e-1"

    def test_swapped_order_breaks_chain_link(self, actor):
        integrity = AuditIntegrity()
        first = integrity.sign_event(_event(actor, event_id="e-1"))
        second = integrity.sign_event(_event(actor, event_id="e-2"))
        report = verify_audit_chain([second, first], integrity=integrity)
        assert report["is_valid"] is False
        assert any(e["issue"] == "chain_link_broken" for e in report["tampered_entries"])


class TestInMemoryQueryFilters:
    async def test_time_bounds_are_inclusive(self, actor):
        storage = InMemoryAuditStorage()
        moment = datetime.now(timezone.utc)
        await storage.store(_event(actor, timestamp=moment))
        await storage.store(_event(actor, event_id="e-2", timestamp=moment + timedelta(seconds=1)))
        found = await storage.query(start_time=moment, end_time=moment)
        assert [e.event_id for e in found] == ["e-1"]

    async def test_severity_and_resource_filters(self, actor):
        storage = InMemoryAuditStorage()
        await storage.store(
            _event(
                actor,
                severity=AuditSeverity.ERROR,
                resource=AuditResource(resource_type="doc", resource_id="d-1"),
            )
        )
        await storage.store(_event(actor, event_id="e-2", severity=AuditSeverity.INFO))
        assert len(await storage.query(severity=AuditSeverity.ERROR)) == 1
        assert len(await storage.query(resource_type="doc")) == 1
        assert len(await storage.query(resource_id="d-1")) == 1
        assert await storage.query(resource_id="nope") == []

    async def test_offset_and_limit_slice(self, actor):
        storage = InMemoryAuditStorage()
        for i in range(5):
            await storage.store(_event(actor, event_id=f"e-{i}"))
        page = await storage.query(limit=2, offset=1)
        assert [e.event_id for e in page] == ["e-1", "e-2"]

    async def test_trim_evicts_oldest_from_by_id_index(self, actor):
        storage = InMemoryAuditStorage(max_events=2)
        for i in range(3):
            await storage.store(_event(actor, event_id=f"e-{i}"))
        assert await storage.get_by_id("e-0") is None
        assert (await storage.get_by_id("e-2")) is not None
        assert len(await storage.query()) == 2

    @pytest.mark.xfail(
        strict=True,
        reason="BUG storage.py:InMemoryAuditStorage.query filters tenant_id by actor "
        "only, so a resource-tenant-only event is invisible although "
        "PostgresHashChainAuditStorage would persist it under the resource tenant",
    )
    async def test_resource_tenant_only_event_is_queryable_by_tenant(self):
        storage = InMemoryAuditStorage()
        await storage.store(
            _event(
                AuditActor(actor_id="u-9", tenant_id=None),
                resource=AuditResource(resource_type="doc", resource_id="d-9", tenant_id="tenant-b"),
            )
        )
        found = await storage.query(tenant_id="tenant-b")
        assert [e.event_id for e in found] == ["e-1"]


class TestWriterSeams:
    async def test_hook_exception_does_not_lose_event(self, actor, restore_singleton):
        storage = InMemoryAuditStorage()
        logger = AuditLogger.configure(storage=storage)

        def bad_hook(event):
            raise RuntimeError("hook boom")

        logger.add_hook(bad_hook)
        event = await logger.log_login_failure(username="u", ip_address="1.2.3.4", reason="bad password")
        assert event.outcome == "failure"
        assert await storage.get_by_id(event.event_id) is not None

    async def test_unknown_modification_operation_maps_to_update(self, actor, restore_singleton):
        logger = AuditLogger.configure(storage=InMemoryAuditStorage())
        resource = AuditResource(resource_type="doc", resource_id="d-1")
        event = await logger.log_data_modification(actor, resource, operation="merge")
        assert event.event_type == AuditEventType.DATA_UPDATE
        assert event.action == "merge"

    async def test_login_failure_marks_unknown_actor(self, restore_singleton):
        logger = AuditLogger.configure(storage=InMemoryAuditStorage())
        event = await logger.log_login_failure(username="ghost", ip_address="9.9.9.9", reason="no such user")
        assert event.actor.actor_id == "unknown:ghost"
        assert event.outcome == "failure"

    async def test_decorator_defaults_to_system_actor(self, restore_singleton):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)

        @audit_action(
            event_type=AuditEventType.API_CALL,
            category=AuditEventCategory.API,
            action="call",
        )
        async def call():
            return "ok"

        assert await call() == "ok"
        (logged,) = await storage.query()
        assert logged.actor.actor_id == "system"
        assert logged.outcome == "success"

    @pytest.mark.xfail(
        strict=True,
        reason="BUG writer.py:audit_action awaits every function, so decorating a sync function raises TypeError",
    )
    async def test_decorator_supports_sync_functions(self, restore_singleton):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)

        @audit_action(
            event_type=AuditEventType.API_CALL,
            category=AuditEventCategory.API,
            action="call",
        )
        def sync_call():
            return "ok"

        assert await sync_call() == "ok"
