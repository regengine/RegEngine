"""Focused tests for services/shared/audit_logging/writer.py.

Covers the AuditLogger public surface (log, query, get_event, hooks,
convenience methods, singleton handling) and the audit_action decorator,
including edge and error cases. Storage, integrity and schema internals
are covered by tests/shared/test_audit_logging.py.
"""

import pytest
from shared.audit_logging import (
    AuditActor,
    AuditEventCategory,
    AuditEventType,
    AuditLogger,
    AuditResource,
    AuditSeverity,
    AuditStorageBackend,
    AuditStorageError,
    InMemoryAuditStorage,
    audit_action,
    get_audit_logger,
)


@pytest.fixture(autouse=True)
def _set_audit_key(monkeypatch):
    """Ensure AUDIT_INTEGRITY_KEY is set for all tests."""
    monkeypatch.setenv("AUDIT_INTEGRITY_KEY", "test-audit-key")


@pytest.fixture
def actor():
    return AuditActor(actor_id="user-123", actor_type="user", username="testuser")


@pytest.fixture
def resource():
    return AuditResource(resource_type="document", resource_id="doc-123")


@pytest.fixture
def logger():
    return AuditLogger(storage=InMemoryAuditStorage(), service_name="svc", environment="test")


@pytest.fixture
def _isolated_singleton():
    """Save and restore the global AuditLogger instance around each test."""
    previous = AuditLogger._instance
    AuditLogger._instance = None
    try:
        yield
    finally:
        AuditLogger._instance = previous


class _FailingStorage(AuditStorageBackend):
    """Backend that reports failure by returning False."""

    async def store(self, event):
        return False

    async def query(self, **kwargs):
        return []

    async def get_by_id(self, event_id):
        return None


def _log_kwargs(actor, **overrides):
    kwargs = dict(
        event_type=AuditEventType.DATA_READ,
        category=AuditEventCategory.DATA_ACCESS,
        severity=AuditSeverity.INFO,
        actor=actor,
        action="read",
        outcome="success",
    )
    kwargs.update(overrides)
    return kwargs


class TestLog:
    async def test_log_stamps_service_and_environment(self, logger, actor):
        event = await logger.log(**_log_kwargs(actor))
        assert event.context.service_name == "svc"
        assert event.context.environment == "test"

    async def test_log_signs_event(self, logger, actor):
        event = await logger.log(**_log_kwargs(actor))
        assert event.event_id
        assert event.integrity_hash

    async def test_log_defaults_details_and_tags(self, logger, actor):
        event = await logger.log(**_log_kwargs(actor))
        assert event.details == {}
        assert event.tags == []

    async def test_logged_event_is_retrievable(self, logger, actor):
        logged = await logger.log(**_log_kwargs(actor))
        assert (await logger.get_event(logged.event_id)).event_id == logged.event_id
        assert len(await logger.query()) == 1

    async def test_get_event_returns_none_for_unknown_id(self, logger):
        assert await logger.get_event("no-such-event") is None

    async def test_hook_exception_does_not_fail_log(self, logger, actor):
        seen = []

        def bad_hook(event):
            raise RuntimeError("hook blew up")

        logger.add_hook(bad_hook)
        logger.add_hook(seen.append)
        event = await logger.log(**_log_kwargs(actor))
        assert event.event_id
        assert seen == [event]

    async def test_storage_false_raises_audit_storage_error(self, actor):
        failing = AuditLogger(storage=_FailingStorage())
        with pytest.raises(AuditStorageError):
            await failing.log(**_log_kwargs(actor))


class TestConvenienceMethods:
    async def test_unknown_modification_falls_back_to_update(self, logger, actor, resource):
        event = await logger.log_data_modification(
            actor=actor, resource=resource, operation="archive", changes={"a": 1}
        )
        assert event.event_type == AuditEventType.DATA_UPDATE
        assert event.action == "archive"

    async def test_login_failure_marks_unknown_actor(self, logger):
        event = await logger.log_login_failure(username="ghost", ip_address="10.0.0.1", reason="bad password")
        assert event.outcome == "failure"
        assert event.actor.actor_id == "unknown:ghost"


class TestAuditActionDecorator:
    async def test_decorator_defaults_to_system_actor(self, _isolated_singleton):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)

        @audit_action(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="create_item",
        )
        async def create_item(data: dict):
            return {"ok": True}

        assert await create_item({"name": "x"}) == {"ok": True}
        (logged,) = await storage.query()
        assert logged.actor.actor_id == "system"
        assert logged.outcome == "success"

    async def test_decorator_builds_resource_from_id_kwarg(self, _isolated_singleton):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)

        @audit_action(
            event_type=AuditEventType.DATA_UPDATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="rename",
            resource_type="document",
        )
        async def rename(document_id: str, actor: AuditActor):
            return "renamed"

        actor = AuditActor(actor_id="user-9", actor_type="user")
        assert await rename(document_id="doc-9", actor=actor) == "renamed"
        (logged,) = await storage.query()
        assert logged.resource.resource_type == "document"
        assert logged.resource.resource_id == "doc-9"

    async def test_decorator_records_error_detail_on_failure(self, _isolated_singleton):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)

        @audit_action(
            event_type=AuditEventType.DATA_DELETE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="remove",
        )
        async def remove(actor: AuditActor):
            raise ValueError("gone")

        with pytest.raises(ValueError, match="gone"):
            await remove(actor=AuditActor(actor_id="u", actor_type="user"))
        (logged,) = await storage.query()
        assert logged.outcome == "failure"
        assert logged.details["error"] == "gone"


class TestSingleton:
    def test_configure_then_get_instance_returns_configured(self, _isolated_singleton):
        configured = AuditLogger.configure(service_name="custom", environment="prod")
        assert AuditLogger.get_instance() is configured
        assert get_audit_logger() is configured

    async def test_decorator_uses_configured_service_context(self, _isolated_singleton, actor):
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage, service_name="custom", environment="prod")

        @audit_action(
            event_type=AuditEventType.API_CALL,
            category=AuditEventCategory.API,
            action="ping",
        )
        async def ping(actor: AuditActor):
            return "pong"

        assert await ping(actor=actor) == "pong"
        (logged,) = await storage.query()
        assert logged.context.service_name == "custom"
        assert logged.context.environment == "prod"
