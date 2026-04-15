"""
Audit storage backends.

Abstract base class and in-memory implementation for audit event storage.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from shared.audit_logging.schema import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
)


class AuditStorageBackend(ABC):
    """Abstract base class for audit storage backends."""

    @abstractmethod
    async def store(self, event: AuditEvent) -> bool:
        """Store an audit event.

        Args:
            event: Event to store

        Returns:
            True if stored successfully
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
            if resource_type and (
                not event.resource or
                event.resource.resource_type != resource_type
            ):
                continue
            if resource_id and (
                not event.resource or
                event.resource.resource_id != resource_id
            ):
                continue
            if tenant_id and event.actor.tenant_id != tenant_id:
                continue
            if severity and event.severity != severity:
                continue

            results.append(event)

        return results[offset:offset + limit]

    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get event by ID."""
        return self._events_by_id.get(event_id)

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
        self._events_by_id.clear()
