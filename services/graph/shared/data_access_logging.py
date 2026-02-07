"""
SEC-020: Data Access Logging.

Comprehensive logging for all data access operations including:
- Database queries (read/write/delete)
- File access operations
- API data access
- Bulk data exports
- Sensitive data access tracking

This module provides detailed audit trails for compliance and security.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class AccessType(str, Enum):
    """Types of data access operations."""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    EXPORT = "export"
    BULK_READ = "bulk_read"
    BULK_WRITE = "bulk_write"
    BULK_DELETE = "bulk_delete"


class DataCategory(str, Enum):
    """Categories of data being accessed."""
    PERSONAL = "personal"  # PII
    FINANCIAL = "financial"  # Financial data
    HEALTH = "health"  # PHI/HIPAA
    CONFIDENTIAL = "confidential"  # Business confidential
    REGULATORY = "regulatory"  # Regulatory documents
    CREDENTIALS = "credentials"  # Authentication/secrets
    SYSTEM = "system"  # System configuration
    AUDIT = "audit"  # Audit logs themselves
    PUBLIC = "public"  # Non-sensitive


class DataSource(str, Enum):
    """Sources/types of data storage."""
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    OBJECT_STORAGE = "object_storage"  # S3, GCS, etc.
    CACHE = "cache"  # Redis, Memcached
    MESSAGE_QUEUE = "message_queue"
    API = "api"
    EXTERNAL_SERVICE = "external_service"


class AccessResult(str, Enum):
    """Result of the access operation."""
    SUCCESS = "success"
    DENIED = "denied"
    PARTIAL = "partial"  # Some data accessible, some denied
    ERROR = "error"
    NOT_FOUND = "not_found"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DataAccessEvent:
    """
    Record of a data access operation.
    
    Captures comprehensive details about what data was accessed,
    by whom, when, and from where.
    """
    # Identity
    event_id: str
    timestamp: datetime
    
    # Actor information
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    service_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Tenant context
    tenant_id: Optional[str] = None
    
    # Operation details
    access_type: AccessType = AccessType.READ
    data_source: DataSource = DataSource.DATABASE
    data_category: DataCategory = DataCategory.SYSTEM
    
    # Resource identification
    resource_type: Optional[str] = None  # e.g., "user", "document", "regulation"
    resource_id: Optional[str] = None  # Primary key or identifier
    resource_path: Optional[str] = None  # Full path or table name
    
    # Query details (if applicable)
    query_text: Optional[str] = None  # Sanitized query
    query_hash: Optional[str] = None  # Hash of query for dedup
    query_params: Optional[Dict[str, Any]] = None  # Sanitized parameters
    
    # Results
    result: AccessResult = AccessResult.SUCCESS
    records_affected: int = 0
    bytes_accessed: int = 0
    
    # Additional context
    fields_accessed: List[str] = field(default_factory=list)
    reason: Optional[str] = None  # Business reason if required
    correlation_id: Optional[str] = None  # For request tracing
    parent_event_id: Optional[str] = None  # For nested operations
    
    # Timing
    duration_ms: Optional[float] = None
    
    # Extra metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and sanitize on creation."""
        # Hash query if provided
        if self.query_text and not self.query_hash:
            self.query_hash = self._hash_query(self.query_text)
    
    def _hash_query(self, query: str) -> str:
        """Create deterministic hash of query."""
        return hashlib.sha256(query.encode()).hexdigest()[:16]
    
    def is_sensitive(self) -> bool:
        """Check if this accesses sensitive data."""
        return self.data_category in {
            DataCategory.PERSONAL,
            DataCategory.FINANCIAL,
            DataCategory.HEALTH,
            DataCategory.CREDENTIALS,
            DataCategory.CONFIDENTIAL,
        }
    
    def is_bulk_operation(self) -> bool:
        """Check if this is a bulk operation."""
        return self.access_type in {
            AccessType.BULK_READ,
            AccessType.BULK_WRITE,
            AccessType.BULK_DELETE,
            AccessType.EXPORT,
        }
    
    def is_destructive(self) -> bool:
        """Check if this is a destructive operation."""
        return self.access_type in {
            AccessType.DELETE,
            AccessType.BULK_DELETE,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "access_type": self.access_type.value,
            "data_source": self.data_source.value,
            "data_category": self.data_category.value,
            "result": self.result.value,
            "records_affected": self.records_affected,
            "bytes_accessed": self.bytes_accessed,
        }
        
        # Add optional fields if present
        for field_name in [
            "user_id", "session_id", "service_name", "ip_address",
            "user_agent", "tenant_id", "resource_type", "resource_id",
            "resource_path", "query_hash", "reason",
            "correlation_id", "parent_event_id", "duration_ms",
        ]:
            value = getattr(self, field_name, None)
            if value is not None:
                result[field_name] = value
        
        if self.fields_accessed:
            result["fields_accessed"] = self.fields_accessed
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class AccessPolicy:
    """
    Policy for data access logging requirements.
    
    Defines what should be logged for specific data categories or resources.
    """
    policy_id: str
    name: str
    description: str
    enabled: bool = True
    
    # What data this policy applies to
    data_categories: List[DataCategory] = field(default_factory=list)
    resource_types: List[str] = field(default_factory=list)
    resource_patterns: List[str] = field(default_factory=list)  # Regex patterns
    
    # What operations to log
    access_types: List[AccessType] = field(default_factory=list)
    
    # Logging requirements
    require_reason: bool = False  # Must provide business reason
    log_query_text: bool = True  # Include sanitized query
    log_query_params: bool = False  # Include query parameters
    log_fields_accessed: bool = True  # Track specific fields
    
    # Retention
    retention_days: int = 90
    
    # Alerting
    alert_on_bulk: bool = True
    alert_on_sensitive: bool = True
    alert_threshold_records: int = 1000  # Alert if > this many records
    
    def applies_to(self, event: DataAccessEvent) -> bool:
        """Check if this policy applies to an event."""
        if not self.enabled:
            return False
        
        # Check data category
        if self.data_categories and event.data_category not in self.data_categories:
            return False
        
        # Check resource type
        if self.resource_types and event.resource_type not in self.resource_types:
            return False
        
        # Check access type
        if self.access_types and event.access_type not in self.access_types:
            return False
        
        return True


@dataclass
class DataAccessConfig:
    """Configuration for data access logging."""
    enabled: bool = True
    
    # What to log
    log_reads: bool = True
    log_writes: bool = True
    log_queries: bool = True
    log_bulk_operations: bool = True
    
    # What categories to log
    logged_categories: Set[DataCategory] = field(
        default_factory=lambda: set(DataCategory)
    )
    
    # Query sanitization
    sanitize_queries: bool = True
    max_query_length: int = 10000
    
    # Sampling (for high-volume scenarios)
    sample_rate: float = 1.0  # 1.0 = log all, 0.1 = log 10%
    always_log_sensitive: bool = True  # Always log sensitive regardless of sample
    always_log_writes: bool = True  # Always log writes regardless of sample
    
    # Batching
    batch_enabled: bool = True
    batch_size: int = 100
    batch_flush_interval_seconds: int = 5
    
    # Alerts
    alert_threshold_records: int = 1000
    alert_threshold_bytes: int = 10 * 1024 * 1024  # 10MB
    
    # Retention
    retention_days: int = 90


# =============================================================================
# Storage Backend
# =============================================================================

class DataAccessStorage(ABC):
    """Abstract base class for data access log storage."""
    
    @abstractmethod
    async def store(self, event: DataAccessEvent) -> None:
        """Store a single access event."""
        pass
    
    @abstractmethod
    async def store_batch(self, events: List[DataAccessEvent]) -> None:
        """Store multiple access events."""
        pass
    
    @abstractmethod
    async def query(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        data_category: Optional[DataCategory] = None,
        access_type: Optional[AccessType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DataAccessEvent]:
        """Query access events."""
        pass
    
    @abstractmethod
    async def get_user_access_summary(
        self,
        user_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get summary of user's data access."""
        pass


class InMemoryDataAccessStorage(DataAccessStorage):
    """In-memory storage for development/testing."""
    
    def __init__(self, max_events: int = 100000):
        self._events: List[DataAccessEvent] = []
        self._max_events = max_events
        self._lock = asyncio.Lock()
    
    async def store(self, event: DataAccessEvent) -> None:
        """Store a single event."""
        async with self._lock:
            self._events.append(event)
            # Trim if over limit
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
    
    async def store_batch(self, events: List[DataAccessEvent]) -> None:
        """Store multiple events."""
        async with self._lock:
            self._events.extend(events)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
    
    async def query(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        data_category: Optional[DataCategory] = None,
        access_type: Optional[AccessType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DataAccessEvent]:
        """Query events with filters."""
        async with self._lock:
            results = []
            
            for event in reversed(self._events):
                if len(results) >= limit:
                    break
                
                if user_id and event.user_id != user_id:
                    continue
                if resource_type and event.resource_type != resource_type:
                    continue
                if data_category and event.data_category != data_category:
                    continue
                if access_type and event.access_type != access_type:
                    continue
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp > end_time:
                    continue
                
                results.append(event)
            
            return results
    
    async def get_user_access_summary(
        self,
        user_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get summary of user's data access."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        async with self._lock:
            user_events = [
                e for e in self._events
                if e.user_id == user_id and e.timestamp >= cutoff
            ]
        
        # Compute statistics
        by_type: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        by_resource: Dict[str, int] = {}
        total_records = 0
        total_bytes = 0
        
        for event in user_events:
            by_type[event.access_type.value] = by_type.get(event.access_type.value, 0) + 1
            by_category[event.data_category.value] = by_category.get(event.data_category.value, 0) + 1
            if event.resource_type:
                by_resource[event.resource_type] = by_resource.get(event.resource_type, 0) + 1
            total_records += event.records_affected
            total_bytes += event.bytes_accessed
        
        return {
            "user_id": user_id,
            "period_days": days,
            "total_events": len(user_events),
            "total_records_accessed": total_records,
            "total_bytes_accessed": total_bytes,
            "by_access_type": by_type,
            "by_data_category": by_category,
            "by_resource_type": by_resource,
        }


# =============================================================================
# Query Sanitizer
# =============================================================================

class QuerySanitizer:
    """Sanitize queries to remove sensitive data."""
    
    # Common patterns to redact
    SENSITIVE_PATTERNS = [
        (r"password\s*=\s*'[^']*'", "password='[REDACTED]'"),
        (r"password\s*=\s*\"[^\"]*\"", 'password="[REDACTED]"'),
        (r"secret\s*=\s*'[^']*'", "secret='[REDACTED]'"),
        (r"api_key\s*=\s*'[^']*'", "api_key='[REDACTED]'"),
        (r"token\s*=\s*'[^']*'", "token='[REDACTED]'"),
        (r"ssn\s*=\s*'[^']*'", "ssn='[REDACTED]'"),
        (r"credit_card\s*=\s*'[^']*'", "credit_card='[REDACTED]'"),
    ]
    
    @classmethod
    def sanitize(cls, query: str, max_length: int = 10000) -> str:
        """
        Sanitize a query string.
        
        - Redacts sensitive values
        - Truncates to max length
        - Normalizes whitespace
        """
        import re
        
        result = query
        
        # Apply redaction patterns
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        # Normalize whitespace
        result = " ".join(result.split())
        
        # Truncate if needed
        if len(result) > max_length:
            result = result[:max_length] + "...[TRUNCATED]"
        
        return result
    
    @classmethod
    def sanitize_params(
        cls,
        params: Dict[str, Any],
        sensitive_keys: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Sanitize query parameters.
        
        Redacts values for sensitive parameter names.
        """
        if sensitive_keys is None:
            sensitive_keys = {
                "password", "secret", "api_key", "token",
                "ssn", "credit_card", "auth", "credential",
            }
        
        result = {}
        for key, value in params.items():
            key_lower = key.lower()
            if any(sk in key_lower for sk in sensitive_keys):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = cls.sanitize_params(value, sensitive_keys)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize_params(v, sensitive_keys) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                result[key] = value
        
        return result


# =============================================================================
# Data Access Logger
# =============================================================================

class DataAccessLogger:
    """
    Central manager for data access logging.
    
    Provides methods to log different types of data access operations
    with appropriate context and sanitization.
    """
    
    _instance: Optional["DataAccessLogger"] = None
    
    def __init__(
        self,
        config: Optional[DataAccessConfig] = None,
        storage: Optional[DataAccessStorage] = None,
    ):
        self._config = config or DataAccessConfig()
        self._storage = storage or InMemoryDataAccessStorage()
        self._policies: List[AccessPolicy] = []
        self._batch: List[DataAccessEvent] = []
        self._batch_lock = asyncio.Lock()
        self._alert_callback: Optional[Callable[[DataAccessEvent], None]] = None
        self._sanitizer = QuerySanitizer()
    
    @classmethod
    def configure(
        cls,
        config: Optional[DataAccessConfig] = None,
        storage: Optional[DataAccessStorage] = None,
    ) -> "DataAccessLogger":
        """Configure the singleton instance."""
        cls._instance = cls(config=config, storage=storage)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "DataAccessLogger":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def add_policy(self, policy: AccessPolicy) -> None:
        """Add an access policy."""
        self._policies.append(policy)
    
    def set_alert_callback(
        self,
        callback: Callable[[DataAccessEvent], None],
    ) -> None:
        """Set callback for alert-worthy events."""
        self._alert_callback = callback
    
    async def log_access(
        self,
        access_type: AccessType,
        data_source: DataSource,
        data_category: DataCategory,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_path: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        service_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        tenant_id: Optional[str] = None,
        query_text: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None,
        result: AccessResult = AccessResult.SUCCESS,
        records_affected: int = 0,
        bytes_accessed: int = 0,
        fields_accessed: Optional[List[str]] = None,
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataAccessEvent:
        """
        Log a data access event.
        
        Returns the created event.
        """
        if not self._config.enabled:
            # Return empty event when disabled
            return DataAccessEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                access_type=access_type,
                data_source=data_source,
                data_category=data_category,
            )
        
        # Check if we should log this (sampling)
        if not self._should_log(access_type, data_category):
            return DataAccessEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                access_type=access_type,
                data_source=data_source,
                data_category=data_category,
            )
        
        # Sanitize query if configured
        sanitized_query = None
        if query_text and self._config.sanitize_queries:
            sanitized_query = self._sanitizer.sanitize(
                query_text,
                self._config.max_query_length,
            )
        elif query_text:
            sanitized_query = query_text
        
        # Sanitize params
        sanitized_params = None
        if query_params:
            sanitized_params = self._sanitizer.sanitize_params(query_params)
        
        # Create event
        event = DataAccessEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=session_id,
            service_name=service_name,
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=tenant_id,
            access_type=access_type,
            data_source=data_source,
            data_category=data_category,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_path=resource_path,
            query_text=sanitized_query,
            query_params=sanitized_params,
            result=result,
            records_affected=records_affected,
            bytes_accessed=bytes_accessed,
            fields_accessed=fields_accessed or [],
            reason=reason,
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        
        # Check for alerts
        await self._check_alerts(event)
        
        # Store (batched or immediate)
        if self._config.batch_enabled:
            await self._add_to_batch(event)
        else:
            await self._storage.store(event)
        
        return event
    
    async def log_database_read(
        self,
        table: str,
        query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        records: int = 0,
        fields: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> DataAccessEvent:
        """Convenience method for logging database reads."""
        return await self.log_access(
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=self._infer_category(table),
            resource_type=table,
            resource_path=table,
            query_text=query,
            query_params=params,
            records_affected=records,
            fields_accessed=fields,
            user_id=user_id,
            **kwargs,
        )
    
    async def log_database_write(
        self,
        table: str,
        operation: str = "insert",  # insert, update, delete
        query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        records: int = 0,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> DataAccessEvent:
        """Convenience method for logging database writes."""
        access_type = {
            "insert": AccessType.WRITE,
            "update": AccessType.UPDATE,
            "delete": AccessType.DELETE,
        }.get(operation, AccessType.WRITE)
        
        return await self.log_access(
            access_type=access_type,
            data_source=DataSource.DATABASE,
            data_category=self._infer_category(table),
            resource_type=table,
            resource_path=table,
            query_text=query,
            query_params=params,
            records_affected=records,
            user_id=user_id,
            **kwargs,
        )
    
    async def log_file_access(
        self,
        file_path: str,
        access_type: AccessType,
        bytes_accessed: int = 0,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> DataAccessEvent:
        """Convenience method for logging file access."""
        return await self.log_access(
            access_type=access_type,
            data_source=DataSource.FILE_SYSTEM,
            data_category=self._infer_category_from_path(file_path),
            resource_path=file_path,
            bytes_accessed=bytes_accessed,
            user_id=user_id,
            **kwargs,
        )
    
    async def log_api_access(
        self,
        endpoint: str,
        method: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        records: int = 0,
        bytes_accessed: int = 0,
        **kwargs,
    ) -> DataAccessEvent:
        """Convenience method for logging API data access."""
        access_type = {
            "GET": AccessType.READ,
            "POST": AccessType.WRITE,
            "PUT": AccessType.UPDATE,
            "PATCH": AccessType.UPDATE,
            "DELETE": AccessType.DELETE,
        }.get(method.upper(), AccessType.READ)
        
        return await self.log_access(
            access_type=access_type,
            data_source=DataSource.API,
            data_category=self._infer_category_from_path(endpoint),
            resource_path=endpoint,
            user_id=user_id,
            ip_address=ip_address,
            records_affected=records,
            bytes_accessed=bytes_accessed,
            **kwargs,
        )
    
    async def log_bulk_export(
        self,
        resource_type: str,
        records: int,
        bytes_accessed: int,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs,
    ) -> DataAccessEvent:
        """Log a bulk data export."""
        return await self.log_access(
            access_type=AccessType.EXPORT,
            data_source=DataSource.DATABASE,
            data_category=self._infer_category(resource_type),
            resource_type=resource_type,
            records_affected=records,
            bytes_accessed=bytes_accessed,
            user_id=user_id,
            reason=reason,
            **kwargs,
        )
    
    async def query_events(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        data_category: Optional[DataCategory] = None,
        access_type: Optional[AccessType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DataAccessEvent]:
        """Query logged events."""
        return await self._storage.query(
            user_id=user_id,
            resource_type=resource_type,
            data_category=data_category,
            access_type=access_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    
    async def get_user_summary(
        self,
        user_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get summary of user's data access."""
        return await self._storage.get_user_access_summary(user_id, days)
    
    async def flush_batch(self) -> None:
        """Flush the current batch to storage."""
        async with self._batch_lock:
            if self._batch:
                await self._storage.store_batch(self._batch)
                self._batch = []
    
    def _should_log(
        self,
        access_type: AccessType,
        data_category: DataCategory,
    ) -> bool:
        """Determine if this access should be logged."""
        import random
        
        # Always log sensitive data if configured
        if self._config.always_log_sensitive:
            if data_category in {
                DataCategory.PERSONAL,
                DataCategory.FINANCIAL,
                DataCategory.HEALTH,
                DataCategory.CREDENTIALS,
            }:
                return True
        
        # Always log writes if configured
        if self._config.always_log_writes:
            if access_type in {
                AccessType.WRITE,
                AccessType.UPDATE,
                AccessType.DELETE,
                AccessType.BULK_WRITE,
                AccessType.BULK_DELETE,
            }:
                return True
        
        # Check category filter
        if data_category not in self._config.logged_categories:
            return False
        
        # Apply sampling
        if self._config.sample_rate < 1.0:
            return random.random() < self._config.sample_rate
        
        return True
    
    def _infer_category(self, resource_type: str) -> DataCategory:
        """Infer data category from resource type."""
        resource_lower = resource_type.lower()
        
        if any(w in resource_lower for w in ["user", "profile", "person", "customer"]):
            return DataCategory.PERSONAL
        if any(w in resource_lower for w in ["payment", "transaction", "invoice", "billing"]):
            return DataCategory.FINANCIAL
        if any(w in resource_lower for w in ["health", "medical", "patient", "diagnosis"]):
            return DataCategory.HEALTH
        if any(w in resource_lower for w in ["secret", "credential", "password", "key", "token"]):
            return DataCategory.CREDENTIALS
        if any(w in resource_lower for w in ["regulation", "compliance", "audit", "policy"]):
            return DataCategory.REGULATORY
        
        return DataCategory.SYSTEM
    
    def _infer_category_from_path(self, path: str) -> DataCategory:
        """Infer data category from file or API path."""
        path_lower = path.lower()
        
        if any(w in path_lower for w in ["/user", "/profile", "/customer"]):
            return DataCategory.PERSONAL
        if any(w in path_lower for w in ["/payment", "/billing", "/invoice"]):
            return DataCategory.FINANCIAL
        if any(w in path_lower for w in ["/health", "/patient", "/medical"]):
            return DataCategory.HEALTH
        if any(w in path_lower for w in ["/secret", "/credential", "/auth"]):
            return DataCategory.CREDENTIALS
        if any(w in path_lower for w in ["/admin", "/config", "/system"]):
            return DataCategory.CONFIDENTIAL
        
        return DataCategory.SYSTEM
    
    async def _add_to_batch(self, event: DataAccessEvent) -> None:
        """Add event to batch, flushing if full."""
        async with self._batch_lock:
            self._batch.append(event)
            
            if len(self._batch) >= self._config.batch_size:
                await self._storage.store_batch(self._batch)
                self._batch = []
    
    async def _check_alerts(self, event: DataAccessEvent) -> None:
        """Check if event warrants an alert."""
        should_alert = False
        
        # Check record threshold
        if event.records_affected > self._config.alert_threshold_records:
            should_alert = True
        
        # Check bytes threshold
        if event.bytes_accessed > self._config.alert_threshold_bytes:
            should_alert = True
        
        # Check bulk operations on sensitive data
        if event.is_bulk_operation() and event.is_sensitive():
            should_alert = True
        
        # Check destructive operations on sensitive data
        if event.is_destructive() and event.is_sensitive():
            should_alert = True
        
        if should_alert and self._alert_callback:
            try:
                self._alert_callback(event)
            except Exception as e:
                logger.error("Alert callback error: %s", e)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_data_access_logger() -> DataAccessLogger:
    """Get the singleton data access logger."""
    return DataAccessLogger.get_instance()


async def log_access(
    access_type: AccessType,
    data_source: DataSource,
    data_category: DataCategory,
    **kwargs,
) -> DataAccessEvent:
    """Log a data access event."""
    logger = get_data_access_logger()
    return await logger.log_access(
        access_type=access_type,
        data_source=data_source,
        data_category=data_category,
        **kwargs,
    )


async def log_database_read(table: str, **kwargs) -> DataAccessEvent:
    """Log a database read operation."""
    logger = get_data_access_logger()
    return await logger.log_database_read(table, **kwargs)


async def log_database_write(table: str, **kwargs) -> DataAccessEvent:
    """Log a database write operation."""
    logger = get_data_access_logger()
    return await logger.log_database_write(table, **kwargs)


async def log_file_access(
    file_path: str,
    access_type: AccessType,
    **kwargs,
) -> DataAccessEvent:
    """Log a file access operation."""
    logger = get_data_access_logger()
    return await logger.log_file_access(file_path, access_type, **kwargs)


async def log_api_access(
    endpoint: str,
    method: str,
    **kwargs,
) -> DataAccessEvent:
    """Log an API data access operation."""
    logger = get_data_access_logger()
    return await logger.log_api_access(endpoint, method, **kwargs)


async def log_bulk_export(
    resource_type: str,
    records: int,
    bytes_accessed: int,
    **kwargs,
) -> DataAccessEvent:
    """Log a bulk data export operation."""
    logger = get_data_access_logger()
    return await logger.log_bulk_export(
        resource_type,
        records,
        bytes_accessed,
        **kwargs,
    )
