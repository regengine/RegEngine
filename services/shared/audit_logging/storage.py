"""
Audit storage backends.

Abstract base class and in-memory implementation for audit event storage.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from shared.audit_logging.schema import (
    AuditActor,
    AuditContext,
    AuditEvent,
    AuditEventCategory,
    AuditEventType,
    AuditResource,
    AuditSeverity,
)

logger = logging.getLogger(__name__)


class AuditStorageError(RuntimeError):
    """An audit event could not be durably persisted.

    Raised instead of returning ``False`` so a failed audit write can
    never read as success to a caller that does not check a return
    value. Compliance-critical callers must treat this as a failed
    operation, not a best-effort miss.
    """


class AuditStorageBackend(ABC):
    """Abstract base class for audit storage backends."""

    @abstractmethod
    async def store(self, event: AuditEvent) -> bool:
        """Store an audit event.

        Args:
            event: Event to store

        Returns:
            True if stored successfully

        Raises:
            AuditStorageError: If the event could not be persisted.
                Backends must raise rather than return False, and
                callers must not treat a quiet False as success.
        """
        pass

    @abstractmethod
    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events.

        Args:
            Various filter parameters

        Returns:
            List of matching events
        """
        pass

    @abstractmethod
    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get an event by ID.

        Args:
            event_id: Event ID

        Returns:
            Event if found
        """
        pass


class PostgresHashChainAuditStorage(AuditStorageBackend):
    """Persist shared audit events onto the tamper-evident ``audit_logs`` chain.

    #2854: ``AuditLogger.get_instance()`` used to default to
    ``InMemoryAuditStorage``, so GDPR erasure records and FSMA validation
    failures vanished on process restart. This backend delegates each write
    to ``services.admin.app.audit.AuditLogger.log_event`` so the events join
    the existing hash chain and survive deploys.
    """

    _EVENT_META_KEY = "_shared_audit_event"

    def __init__(self, session_factory=None):
        self._session_factory = session_factory

    def _sessions(self):
        if self._session_factory is not None:
            return self._session_factory
        from services.admin.app.database import SessionLocal

        return SessionLocal

    @staticmethod
    def _as_uuid(raw: Optional[str], *, namespace: str) -> Optional[uuid.UUID]:
        if not raw:
            return None
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            return uuid.uuid5(uuid.NAMESPACE_URL, f"regengine:{namespace}:{raw}")

    def _require_tenant_id(self, event: AuditEvent) -> uuid.UUID:
        raw = event.actor.tenant_id or (event.resource.tenant_id if event.resource else None)
        tenant_id = self._as_uuid(raw, namespace="audit-tenant")
        if tenant_id is None:
            raise ValueError("durable audit storage requires a tenant_id")
        return tenant_id

    async def store(self, event: AuditEvent) -> bool:
        from services.admin.app.audit import AuditLogger as ChainLogger

        tenant_id = self._require_tenant_id(event)
        actor_id = self._as_uuid(event.actor.actor_id, namespace="audit-actor")
        request_id = self._as_uuid(
            event.context.request_id if event.context else None,
            namespace="audit-request",
        )
        metadata = {
            self._EVENT_META_KEY: event.to_dict(),
            "event_id": event.event_id,
            "outcome": event.outcome,
            "message": event.message,
            "details": event.details,
            "tags": event.tags,
        }
        session_factory = self._sessions()
        db = session_factory()
        try:
            entry_id = ChainLogger.log_event(
                db,
                tenant_id=tenant_id,
                event_type=event.event_type.value,
                action=event.action,
                event_category=event.category.value,
                severity=event.severity.value,
                actor_id=actor_id,
                actor_email=event.actor.email or event.actor.username,
                actor_ip=event.actor.ip_address,
                actor_ua=event.actor.user_agent,
                resource_type=event.resource.resource_type if event.resource else None,
                resource_id=event.resource.resource_id if event.resource else None,
                endpoint=event.context.endpoint if event.context else None,
                metadata=metadata,
                request_id=request_id,
            )
        except Exception:
            db.rollback()
            raise
        else:
            # A None entry id means the chain writer swallowed its own
            # failure. Raising here (in `else`, outside the guarded
            # region above) surfaces it as an error instead of a quiet
            # False the caller could mistake for success.
            if entry_id is None:
                db.rollback()
                logger.error(
                    "audit_storage_write_failed event_id=%s event_type=%s action=%s",
                    event.event_id,
                    event.event_type.value,
                    event.action,
                )
                raise AuditStorageError(
                    f"audit event {event.event_id} was not persisted (chain writer returned no entry id)"
                )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            return True
        finally:
            db.close()

    def _event_from_row(self, row) -> Optional[AuditEvent]:
        payload = (row.metadata_ or {}).get(self._EVENT_META_KEY)
        if not isinstance(payload, dict):
            return None
        try:
            return _event_from_dict(payload)
        except (TypeError, ValueError, KeyError):
            return None

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        from sqlalchemy import select

        from services.admin.app.sqlalchemy_models import AuditLogModel

        session_factory = self._sessions()
        db = session_factory()
        try:
            stmt = select(AuditLogModel)
            if start_time is not None:
                stmt = stmt.where(AuditLogModel.timestamp >= start_time)
            if end_time is not None:
                stmt = stmt.where(AuditLogModel.timestamp <= end_time)
            if event_types:
                stmt = stmt.where(AuditLogModel.event_type.in_([t.value for t in event_types]))
            if actor_id:
                mapped_actor = self._as_uuid(actor_id, namespace="audit-actor")
                if mapped_actor is not None:
                    stmt = stmt.where(AuditLogModel.actor_id == mapped_actor)
            if resource_type:
                stmt = stmt.where(AuditLogModel.resource_type == resource_type)
            if resource_id:
                stmt = stmt.where(AuditLogModel.resource_id == resource_id)
            if tenant_id:
                mapped_tenant = self._as_uuid(tenant_id, namespace="audit-tenant")
                if mapped_tenant is not None:
                    stmt = stmt.where(AuditLogModel.tenant_id == mapped_tenant)
            if severity:
                stmt = stmt.where(AuditLogModel.severity == severity.value)
            stmt = stmt.order_by(AuditLogModel.id).offset(offset).limit(limit)
            rows = db.execute(stmt).scalars().all()
            events = []
            for row in rows:
                event = self._event_from_row(row)
                if event is not None:
                    events.append(event)
            return events
        finally:
            db.close()

    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        from sqlalchemy import select

        from services.admin.app.sqlalchemy_models import AuditLogModel

        session_factory = self._sessions()
        db = session_factory()
        try:
            stmt = select(AuditLogModel).where(
                AuditLogModel.metadata_["event_id"].astext == event_id
            )
            row = db.execute(stmt).scalars().first()
            if row is None:
                return None
            return self._event_from_row(row)
        except Exception:
            # SQLite / JSON operators differ; fall back to a small scan of
            # recent rows so tests and local backends still round-trip.
            stmt = select(AuditLogModel).order_by(AuditLogModel.id.desc()).limit(200)
            for row in db.execute(stmt).scalars():
                payload = (row.metadata_ or {})
                if payload.get("event_id") == event_id:
                    return self._event_from_row(row)
            return None
        finally:
            db.close()


def _event_from_dict(payload: Dict) -> AuditEvent:
    """Rehydrate an ``AuditEvent`` from the dict stored on ``audit_logs.metadata``."""
    actor_payload = payload.get("actor") or {}
    resource_payload = payload.get("resource")
    context_payload = payload.get("context")
    timestamp = payload["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    return AuditEvent(
        event_id=payload["event_id"],
        timestamp=timestamp,
        event_type=AuditEventType(payload["event_type"]),
        category=AuditEventCategory(payload["category"]),
        severity=AuditSeverity(payload["severity"]),
        actor=AuditActor(
            actor_id=actor_payload.get("actor_id", ""),
            actor_type=actor_payload.get("actor_type", "system"),
            username=actor_payload.get("username"),
            ip_address=actor_payload.get("ip_address"),
            user_agent=actor_payload.get("user_agent"),
            tenant_id=actor_payload.get("tenant_id"),
        ),
        action=payload["action"],
        outcome=payload["outcome"],
        resource=(
            AuditResource(
                resource_type=resource_payload["resource_type"],
                resource_id=resource_payload["resource_id"],
                resource_name=resource_payload.get("resource_name"),
                tenant_id=resource_payload.get("tenant_id"),
                attributes=resource_payload.get("attributes") or {},
            )
            if resource_payload
            else None
        ),
        context=(
            AuditContext(
                request_id=context_payload.get("request_id"),
                correlation_id=context_payload.get("correlation_id"),
                environment=context_payload.get("environment"),
                service_name=context_payload.get("service_name"),
                endpoint=context_payload.get("endpoint"),
            )
            if context_payload
            else None
        ),
        message=payload.get("message"),
        details=payload.get("details") or {},
        tags=payload.get("tags") or [],
        integrity_hash=payload.get("integrity_hash"),
        previous_hash=payload.get("previous_hash"),
    )


class InMemoryAuditStorage(AuditStorageBackend):
    """In-memory audit storage for testing."""

    def __init__(self, max_events: int = 10000):
        """Initialize in-memory storage.

        Args:
            max_events: Maximum events to store
        """
        self._events: List[AuditEvent] = []
        self._max_events = max_events
        self._events_by_id: Dict[str, AuditEvent] = {}

    async def store(self, event: AuditEvent) -> bool:
        """Store an event."""
        self._events.append(event)
        self._events_by_id[event.event_id] = event

        # Trim if needed
        if len(self._events) > self._max_events:
            removed = self._events.pop(0)
            del self._events_by_id[removed.event_id]

        return True

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query events with filters."""
        results = []

        for event in self._events:
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            if event_types and event.event_type not in event_types:
                continue
            if actor_id and event.actor.actor_id != actor_id:
                continue
            if resource_type and (not event.resource or event.resource.resource_type != resource_type):
                continue
            if resource_id and (not event.resource or event.resource.resource_id != resource_id):
                continue
            if tenant_id and event.actor.tenant_id != tenant_id:
                continue
            if severity and event.severity != severity:
                continue

            results.append(event)

        return results[offset : offset + limit]

    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get event by ID."""
        return self._events_by_id.get(event_id)

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
        self._events_by_id.clear()
