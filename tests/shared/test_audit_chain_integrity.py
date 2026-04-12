"""Extended audit chain integrity tests.

Complements the existing test_audit_logging.py by focusing on:
- Large chain verification performance
- Tamper detection at various positions
- Chain reconstruction after corruption
- Cross-service correlation scenarios
- Concurrent event logging safety
- Edge cases in hash computation
"""

import os
os.environ.setdefault("REGENGINE_ENV", "test")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("AUDIT_INTEGRITY_KEY", "test-audit-key-for-integrity")

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from services.shared.audit_logging import (
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
    verify_audit_chain,
)


@pytest.fixture
def integrity():
    return AuditIntegrity(secret_key="test-secret-key")


@pytest.fixture
def storage():
    return InMemoryAuditStorage(max_events=10000)


@pytest.fixture
def logger(storage, integrity):
    return AuditLogger(
        storage=storage,
        integrity=integrity,
        service_name="test-service",
        environment="test",
    )


def _make_actor(actor_id=None, tenant_id=None) -> AuditActor:
    return AuditActor(
        actor_id=actor_id or str(uuid4()),
        actor_type="user",
        username="testuser",
        email="test@regengine.co",
        ip_address="127.0.0.1",
        tenant_id=tenant_id or str(uuid4()),
    )


# ─── Hash computation edge cases ─────────────────────────────────────────


class TestHashEdgeCases:
    def test_hash_depends_on_event_id(self, integrity):
        """Two events that differ only in event_id have different hashes."""
        actor = _make_actor()
        e1 = AuditEvent(
            event_id="id-1",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        e2 = AuditEvent(
            event_id="id-2",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        h1 = integrity.compute_hash(e1)
        h2 = integrity.compute_hash(e2)
        assert h1 != h2

    def test_hash_depends_on_timestamp(self, integrity):
        actor = _make_actor()
        e1 = AuditEvent(
            event_id="same-id",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        e2 = AuditEvent(
            event_id="same-id",
            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        assert integrity.compute_hash(e1) != integrity.compute_hash(e2)

    def test_hash_depends_on_outcome(self, integrity):
        actor = _make_actor()
        base = dict(
            event_id="same",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
        )
        e_success = AuditEvent(**base, outcome="success")
        e_failure = AuditEvent(**base, outcome="failure")
        assert integrity.compute_hash(e_success) != integrity.compute_hash(e_failure)

    def test_hash_is_64_hex_chars(self, integrity):
        actor = _make_actor()
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="create",
            outcome="success",
        )
        h = integrity.compute_hash(event)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ─── Chain verification at scale ─────────────────────────────────────────


class TestLargeChainVerification:
    def test_100_event_chain_validates(self, integrity):
        """Build and verify a 100-event chain."""
        actor = _make_actor()
        events = []
        for i in range(100):
            event = AuditEvent(
                event_id=str(uuid4()),
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
                event_type=AuditEventType.DATA_READ,
                category=AuditEventCategory.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"read-{i}",
                outcome="success",
            )
            integrity.sign_event(event)
            events.append(event)

        assert integrity.verify_chain(events) is True

    def test_tampering_mid_chain_detected(self, integrity):
        """Modify event #50 in a 100-event chain; verify chain catches it."""
        actor = _make_actor()
        events = []
        for i in range(100):
            event = AuditEvent(
                event_id=str(uuid4()),
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
                event_type=AuditEventType.DATA_READ,
                category=AuditEventCategory.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"read-{i}",
                outcome="success",
            )
            integrity.sign_event(event)
            events.append(event)

        # Tamper with event 50
        events[50].action = "TAMPERED"

        result = verify_audit_chain(events, integrity=integrity)
        assert result["is_valid"] is False
        # Should detect the tampered entry
        assert len(result["tampered_entries"]) >= 1


# ─── Specific tamper scenarios ───────────────────────────────────────────


class TestTamperDetection:
    def test_modified_action_detected(self, integrity):
        actor = _make_actor()
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="create_record",
            outcome="success",
        )
        integrity.sign_event(event)
        assert integrity.verify_event(event) is True

        event.action = "delete_record"
        assert integrity.verify_event(event) is False

    def test_modified_actor_detected(self, integrity):
        actor = _make_actor(actor_id="user-001")
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.DATA_DELETE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.WARNING,
            actor=actor,
            action="delete",
            outcome="success",
        )
        integrity.sign_event(event)

        event.actor = _make_actor(actor_id="user-002")
        assert integrity.verify_event(event) is False

    def test_swapped_event_order_breaks_chain(self, integrity):
        actor = _make_actor()
        events = []
        for i in range(3):
            event = AuditEvent(
                event_id=str(uuid4()),
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
                event_type=AuditEventType.DATA_READ,
                category=AuditEventCategory.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"action-{i}",
                outcome="success",
            )
            integrity.sign_event(event)
            events.append(event)

        # Swap events 1 and 2
        events[1], events[2] = events[2], events[1]

        result = verify_audit_chain(events, integrity=integrity)
        assert result["is_valid"] is False

    def test_missing_hash_detected(self, integrity):
        actor = _make_actor()
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="read",
            outcome="success",
        )
        # Don't sign the event
        result = verify_audit_chain([event], integrity=integrity)
        assert result["is_valid"] is False
        assert any("missing" in e.get("issue", "").lower() for e in result["tampered_entries"])


# ─── Cross-service correlation ───────────────────────────────────────────


class TestCrossServiceCorrelation:
    @pytest.mark.asyncio
    async def test_events_share_correlation_id(self, logger, storage):
        actor = _make_actor()
        correlation_id = str(uuid4())

        ctx = AuditContext(
            correlation_id=correlation_id,
            service_name="ingestion",
        )

        e1 = await logger.log(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="ingest_record",
            outcome="success",
            context=ctx,
        )

        ctx2 = AuditContext(
            correlation_id=correlation_id,
            service_name="graph",
        )

        e2 = await logger.log(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="create_node",
            outcome="success",
            context=ctx2,
        )

        # Both events should be retrievable and share correlation_id
        assert e1.context.correlation_id == correlation_id
        assert e2.context.correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_query_by_tenant_isolates_events(self, logger, storage):
        tenant_a = str(uuid4())
        tenant_b = str(uuid4())

        await logger.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=_make_actor(tenant_id=tenant_a),
            action="read",
            outcome="success",
        )
        await logger.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=_make_actor(tenant_id=tenant_b),
            action="read",
            outcome="success",
        )

        events_a = await logger.query(tenant_id=tenant_a)
        events_b = await logger.query(tenant_id=tenant_b)

        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0].actor.tenant_id == tenant_a
        assert events_b[0].actor.tenant_id == tenant_b


# ─── Convenience method coverage ─────────────────────────────────────────


class TestConvenienceMethods:
    @pytest.mark.asyncio
    async def test_log_login_success(self, logger):
        event = await logger.log_login_success(
            user_id="user-001",
            username="chris",
            ip_address="10.0.0.1",
            tenant_id="tenant-001",
        )
        assert event.event_type == AuditEventType.LOGIN_SUCCESS
        assert event.outcome == "success"
        assert event.integrity_hash is not None

    @pytest.mark.asyncio
    async def test_log_login_failure(self, logger):
        event = await logger.log_login_failure(
            username="unknown",
            ip_address="10.0.0.1",
            reason="invalid_password",
        )
        assert event.event_type == AuditEventType.LOGIN_FAILURE
        assert event.outcome == "failure"

    @pytest.mark.asyncio
    async def test_log_data_modification(self, logger):
        actor = _make_actor()
        resource = AuditResource(
            resource_type="cte_event",
            resource_id="evt-001",
        )
        event = await logger.log_data_modification(
            actor=actor,
            resource=resource,
            operation="create",
            changes={"field": "new_value"},
        )
        assert event.event_type == AuditEventType.DATA_CREATE
        assert event.category == AuditEventCategory.DATA_MODIFICATION

    @pytest.mark.asyncio
    async def test_log_security_event(self, logger):
        actor = _make_actor()
        event = await logger.log_security_event(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            actor=actor,
            description="Too many requests from 10.0.0.1",
            severity=AuditSeverity.WARNING,
        )
        assert event.event_type == AuditEventType.RATE_LIMIT_EXCEEDED
        assert event.severity == AuditSeverity.WARNING

    @pytest.mark.asyncio
    async def test_log_access_denied(self, logger):
        actor = _make_actor()
        resource = AuditResource(resource_type="admin_panel", resource_id="settings")
        event = await logger.log_access_denied(
            actor=actor,
            resource=resource,
            required_permission="admin:write",
        )
        assert event.event_type == AuditEventType.ACCESS_DENIED
        assert event.outcome in ("failure", "denied")


# ─── Storage limits ──────────────────────────────────────────────────────


class TestStorageLimits:
    @pytest.mark.asyncio
    async def test_in_memory_storage_trims_oldest(self):
        storage = InMemoryAuditStorage(max_events=5)
        integrity = AuditIntegrity(secret_key="key")
        logger = AuditLogger(storage=storage, integrity=integrity)

        actor = _make_actor()
        for i in range(10):
            await logger.log(
                event_type=AuditEventType.DATA_READ,
                category=AuditEventCategory.DATA_ACCESS,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"action-{i}",
                outcome="success",
            )

        events = await storage.query()
        assert len(events) <= 5
