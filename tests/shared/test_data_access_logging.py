"""
Tests for SEC-020: Data Access Logging.

Tests cover:
- Data access event creation
- Access type categorization
- Query sanitization
- Storage operations
- Alert triggering
- Convenience functions
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

from shared.data_access_logging import (
    # Enums
    AccessType,
    DataCategory,
    DataSource,
    AccessResult,
    # Data classes
    DataAccessEvent,
    AccessPolicy,
    DataAccessConfig,
    # Storage
    InMemoryDataAccessStorage,
    # Sanitizer
    QuerySanitizer,
    # Logger
    DataAccessLogger,
    # Functions
    get_data_access_logger,
    log_access,
    log_database_read,
    log_database_write,
    log_file_access,
    log_api_access,
    log_bulk_export,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create test config."""
    return DataAccessConfig(
        enabled=True,
        batch_enabled=False,  # Immediate storage for testing
        sample_rate=1.0,  # Log everything
    )


@pytest.fixture
def storage():
    """Create test storage."""
    return InMemoryDataAccessStorage()


@pytest.fixture
def logger(config, storage):
    """Create test logger."""
    return DataAccessLogger(config=config, storage=storage)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_access_type(self):
        """Should have expected access types."""
        assert AccessType.READ == "read"
        assert AccessType.WRITE == "write"
        assert AccessType.DELETE == "delete"
        assert AccessType.EXPORT == "export"
    
    def test_data_category(self):
        """Should have expected categories."""
        assert DataCategory.PERSONAL == "personal"
        assert DataCategory.FINANCIAL == "financial"
        assert DataCategory.HEALTH == "health"
        assert DataCategory.CREDENTIALS == "credentials"
    
    def test_data_source(self):
        """Should have expected sources."""
        assert DataSource.DATABASE == "database"
        assert DataSource.FILE_SYSTEM == "file_system"
        assert DataSource.API == "api"
    
    def test_access_result(self):
        """Should have expected results."""
        assert AccessResult.SUCCESS == "success"
        assert AccessResult.DENIED == "denied"


# =============================================================================
# Test: Data Access Event
# =============================================================================

class TestDataAccessEvent:
    """Test DataAccessEvent data class."""
    
    def test_creation(self):
        """Should create event with required fields."""
        event = DataAccessEvent(
            event_id="event-123",
            timestamp=datetime.now(timezone.utc),
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.PERSONAL,
        )
        
        assert event.event_id == "event-123"
        assert event.access_type == AccessType.READ
        assert event.result == AccessResult.SUCCESS
    
    def test_is_sensitive(self):
        """Should detect sensitive categories."""
        personal = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            data_category=DataCategory.PERSONAL,
        )
        system = DataAccessEvent(
            event_id="2",
            timestamp=datetime.now(timezone.utc),
            data_category=DataCategory.SYSTEM,
        )
        
        assert personal.is_sensitive() is True
        assert system.is_sensitive() is False
    
    def test_is_bulk_operation(self):
        """Should detect bulk operations."""
        bulk = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            access_type=AccessType.BULK_READ,
        )
        single = DataAccessEvent(
            event_id="2",
            timestamp=datetime.now(timezone.utc),
            access_type=AccessType.READ,
        )
        
        assert bulk.is_bulk_operation() is True
        assert single.is_bulk_operation() is False
    
    def test_is_destructive(self):
        """Should detect destructive operations."""
        delete = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            access_type=AccessType.DELETE,
        )
        read = DataAccessEvent(
            event_id="2",
            timestamp=datetime.now(timezone.utc),
            access_type=AccessType.READ,
        )
        
        assert delete.is_destructive() is True
        assert read.is_destructive() is False
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        event = DataAccessEvent(
            event_id="event-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            access_type=AccessType.WRITE,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.FINANCIAL,
            resource_type="transactions",
            records_affected=100,
            user_id="user-456",
        )
        
        data = event.to_dict()
        
        assert data["event_id"] == "event-123"
        assert data["access_type"] == "write"
        assert data["data_category"] == "financial"
        assert data["records_affected"] == 100
    
    def test_to_json(self):
        """Should convert to JSON."""
        event = DataAccessEvent(
            event_id="event-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.SYSTEM,
        )
        
        json_str = event.to_json()
        
        assert '"event_id": "event-123"' in json_str
        assert '"access_type": "read"' in json_str
    
    def test_query_hash(self):
        """Should hash query text."""
        event = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            query_text="SELECT * FROM users WHERE id = 123",
        )
        
        assert event.query_hash is not None
        assert len(event.query_hash) == 16


# =============================================================================
# Test: Access Policy
# =============================================================================

class TestAccessPolicy:
    """Test AccessPolicy."""
    
    def test_creation(self):
        """Should create policy with defaults."""
        policy = AccessPolicy(
            policy_id="policy-1",
            name="Test Policy",
            description="Test description",
        )
        
        assert policy.enabled is True
        assert policy.retention_days == 90
    
    def test_applies_to_category(self):
        """Should filter by data category."""
        policy = AccessPolicy(
            policy_id="policy-1",
            name="PII Policy",
            description="Track PII access",
            data_categories=[DataCategory.PERSONAL, DataCategory.HEALTH],
        )
        
        pii_event = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            data_category=DataCategory.PERSONAL,
        )
        system_event = DataAccessEvent(
            event_id="2",
            timestamp=datetime.now(timezone.utc),
            data_category=DataCategory.SYSTEM,
        )
        
        assert policy.applies_to(pii_event) is True
        assert policy.applies_to(system_event) is False
    
    def test_disabled_policy(self):
        """Should not apply when disabled."""
        policy = AccessPolicy(
            policy_id="policy-1",
            name="Disabled Policy",
            description="This is disabled",
            enabled=False,
        )
        
        event = DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
        )
        
        assert policy.applies_to(event) is False


# =============================================================================
# Test: Query Sanitizer
# =============================================================================

class TestQuerySanitizer:
    """Test QuerySanitizer."""
    
    def test_sanitize_password(self):
        """Should redact passwords."""
        query = "SELECT * FROM users WHERE password='secret123'"
        result = QuerySanitizer.sanitize(query)
        
        assert "secret123" not in result
        assert "[REDACTED]" in result
    
    def test_sanitize_api_key(self):
        """Should redact API keys."""
        query = "SELECT * FROM config WHERE api_key='sk-12345'"
        result = QuerySanitizer.sanitize(query)
        
        assert "sk-12345" not in result
        assert "[REDACTED]" in result
    
    def test_truncate_long_query(self):
        """Should truncate long queries."""
        query = "SELECT " + "a, " * 1000 + " FROM table"
        result = QuerySanitizer.sanitize(query, max_length=100)
        
        assert len(result) <= 120  # 100 + truncation message
        assert "[TRUNCATED]" in result
    
    def test_sanitize_params(self):
        """Should sanitize parameter dictionary."""
        params = {
            "user_id": "123",
            "password": "secret",
            "api_key": "sk-12345",
            "data": {"nested_secret": "value"},
        }
        
        result = QuerySanitizer.sanitize_params(params)
        
        assert result["user_id"] == "123"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"


# =============================================================================
# Test: In-Memory Storage
# =============================================================================

class TestInMemoryDataAccessStorage:
    """Test InMemoryDataAccessStorage."""
    
    @pytest.mark.asyncio
    async def test_store_and_query(self, storage):
        """Should store and retrieve events."""
        event = DataAccessEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.PERSONAL,
            resource_type="users",
        )
        
        await storage.store(event)
        
        results = await storage.query(user_id="user-123")
        assert len(results) == 1
        assert results[0].event_id == "event-1"
    
    @pytest.mark.asyncio
    async def test_batch_store(self, storage):
        """Should store multiple events."""
        events = [
            DataAccessEvent(
                event_id=f"event-{i}",
                timestamp=datetime.now(timezone.utc),
                user_id="user-123",
            )
            for i in range(5)
        ]
        
        await storage.store_batch(events)
        
        results = await storage.query(user_id="user-123")
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_query_filters(self, storage):
        """Should filter by multiple criteria."""
        # Create various events
        await storage.store(DataAccessEvent(
            event_id="1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-1",
            access_type=AccessType.READ,
            data_category=DataCategory.PERSONAL,
        ))
        await storage.store(DataAccessEvent(
            event_id="2",
            timestamp=datetime.now(timezone.utc),
            user_id="user-1",
            access_type=AccessType.WRITE,
            data_category=DataCategory.SYSTEM,
        ))
        await storage.store(DataAccessEvent(
            event_id="3",
            timestamp=datetime.now(timezone.utc),
            user_id="user-2",
            access_type=AccessType.READ,
            data_category=DataCategory.PERSONAL,
        ))
        
        # Filter by user
        user1_results = await storage.query(user_id="user-1")
        assert len(user1_results) == 2
        
        # Filter by access type
        reads = await storage.query(access_type=AccessType.READ)
        assert len(reads) == 2
        
        # Filter by category
        personal = await storage.query(data_category=DataCategory.PERSONAL)
        assert len(personal) == 2
    
    @pytest.mark.asyncio
    async def test_user_access_summary(self, storage):
        """Should calculate user summary."""
        # Create events for user
        for i in range(10):
            await storage.store(DataAccessEvent(
                event_id=f"event-{i}",
                timestamp=datetime.now(timezone.utc),
                user_id="user-123",
                access_type=AccessType.READ if i % 2 == 0 else AccessType.WRITE,
                data_category=DataCategory.PERSONAL,
                resource_type="users",
                records_affected=10,
                bytes_accessed=1000,
            ))
        
        summary = await storage.get_user_access_summary("user-123", days=30)
        
        assert summary["user_id"] == "user-123"
        assert summary["total_events"] == 10
        assert summary["total_records_accessed"] == 100
        assert summary["total_bytes_accessed"] == 10000
        assert "read" in summary["by_access_type"]


# =============================================================================
# Test: Data Access Logger
# =============================================================================

class TestDataAccessLogger:
    """Test DataAccessLogger."""
    
    @pytest.mark.asyncio
    async def test_log_access(self, logger):
        """Should log access event."""
        event = await logger.log_access(
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.PERSONAL,
            resource_type="users",
            user_id="user-123",
            records_affected=50,
        )
        
        assert event.event_id is not None
        assert event.user_id == "user-123"
        assert event.records_affected == 50
    
    @pytest.mark.asyncio
    async def test_log_disabled(self):
        """Should return empty event when disabled."""
        config = DataAccessConfig(enabled=False)
        logger = DataAccessLogger(config=config)
        
        event = await logger.log_access(
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.PERSONAL,
        )
        
        assert event.event_id is not None
        # Event created but not stored
    
    @pytest.mark.asyncio
    async def test_log_database_read(self, logger):
        """Should log database reads."""
        event = await logger.log_database_read(
            table="users",
            query="SELECT * FROM users WHERE active = true",
            records=100,
            user_id="user-123",
        )
        
        assert event.access_type == AccessType.READ
        assert event.data_source == DataSource.DATABASE
        assert event.resource_type == "users"
    
    @pytest.mark.asyncio
    async def test_log_database_write(self, logger):
        """Should log database writes."""
        event = await logger.log_database_write(
            table="users",
            operation="insert",
            records=1,
            user_id="user-123",
        )
        
        assert event.access_type == AccessType.WRITE
    
    @pytest.mark.asyncio
    async def test_log_database_delete(self, logger):
        """Should log database deletes."""
        event = await logger.log_database_write(
            table="users",
            operation="delete",
            records=5,
            user_id="admin",
        )
        
        assert event.access_type == AccessType.DELETE
    
    @pytest.mark.asyncio
    async def test_log_file_access(self, logger):
        """Should log file access."""
        event = await logger.log_file_access(
            file_path="/data/exports/users.csv",
            access_type=AccessType.READ,
            bytes_accessed=50000,
            user_id="user-123",
        )
        
        assert event.data_source == DataSource.FILE_SYSTEM
        assert event.bytes_accessed == 50000
    
    @pytest.mark.asyncio
    async def test_log_api_access(self, logger):
        """Should log API access."""
        event = await logger.log_api_access(
            endpoint="/api/users",
            method="GET",
            user_id="user-123",
            ip_address="192.168.1.100",
            records=25,
        )
        
        assert event.data_source == DataSource.API
        assert event.access_type == AccessType.READ
        assert event.ip_address == "192.168.1.100"
    
    @pytest.mark.asyncio
    async def test_log_bulk_export(self, logger):
        """Should log bulk exports."""
        event = await logger.log_bulk_export(
            resource_type="customers",
            records=10000,
            bytes_accessed=5_000_000,
            user_id="admin",
            reason="Monthly report generation",
        )
        
        assert event.access_type == AccessType.EXPORT
        assert event.records_affected == 10000
        assert event.reason == "Monthly report generation"
    
    @pytest.mark.asyncio
    async def test_query_events(self, logger):
        """Should query logged events."""
        # Log some events
        await logger.log_database_read(
            table="users",
            records=10,
            user_id="user-1",
        )
        await logger.log_database_read(
            table="orders",
            records=20,
            user_id="user-1",
        )
        await logger.log_database_read(
            table="users",
            records=5,
            user_id="user-2",
        )
        
        # Query by user
        user1_events = await logger.query_events(user_id="user-1")
        assert len(user1_events) == 2
        
        # Query by resource
        user_events = await logger.query_events(resource_type="users")
        assert len(user_events) == 2
    
    @pytest.mark.asyncio
    async def test_get_user_summary(self, logger):
        """Should get user access summary."""
        # Log some events
        for i in range(5):
            await logger.log_database_read(
                table="users",
                records=10,
                user_id="user-123",
            )
        
        summary = await logger.get_user_summary("user-123")
        
        assert summary["user_id"] == "user-123"
        assert summary["total_events"] == 5
    
    @pytest.mark.asyncio
    async def test_query_sanitization(self, logger):
        """Should sanitize queries when logging."""
        event = await logger.log_database_read(
            table="users",
            query="SELECT * FROM users WHERE password='secret123'",
            user_id="user-123",
        )
        
        assert "secret123" not in (event.query_text or "")
        assert "[REDACTED]" in (event.query_text or "")
    
    @pytest.mark.asyncio
    async def test_infer_category(self, logger):
        """Should infer data category from resource type."""
        # User data -> PERSONAL
        event = await logger.log_database_read(table="users", user_id="u1")
        assert event.data_category == DataCategory.PERSONAL
        
        # Payment data -> FINANCIAL
        event = await logger.log_database_read(table="payments", user_id="u1")
        assert event.data_category == DataCategory.FINANCIAL
        
        # Credential data -> CREDENTIALS
        event = await logger.log_database_read(table="api_secrets", user_id="u1")
        assert event.data_category == DataCategory.CREDENTIALS
    
    @pytest.mark.asyncio
    async def test_alert_callback(self, logger):
        """Should trigger alert callback for high-volume access."""
        alerts = []
        
        def alert_handler(event):
            alerts.append(event)
        
        logger.set_alert_callback(alert_handler)
        
        # Log a large export
        await logger.log_bulk_export(
            resource_type="customers",
            records=5000,  # Over threshold (1000)
            bytes_accessed=1_000_000,
            user_id="admin",
        )
        
        assert len(alerts) == 1
        assert alerts[0].records_affected == 5000


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_data_access_logger(self):
        """Should return singleton instance."""
        logger1 = get_data_access_logger()
        logger2 = get_data_access_logger()
        assert logger1 is logger2
    
    @pytest.mark.asyncio
    async def test_log_access_function(self):
        """Should log via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_access(
            access_type=AccessType.READ,
            data_source=DataSource.DATABASE,
            data_category=DataCategory.SYSTEM,
            user_id="test-user",
        )
        
        assert event.user_id == "test-user"
    
    @pytest.mark.asyncio
    async def test_log_database_read_function(self):
        """Should log database read via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_database_read(
            table="products",
            user_id="user-123",
            records=10,
        )
        
        assert event.resource_type == "products"
        assert event.access_type == AccessType.READ
    
    @pytest.mark.asyncio
    async def test_log_database_write_function(self):
        """Should log database write via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_database_write(
            table="orders",
            operation="insert",
            user_id="user-123",
            records=1,
        )
        
        assert event.resource_type == "orders"
        assert event.access_type == AccessType.WRITE
    
    @pytest.mark.asyncio
    async def test_log_file_access_function(self):
        """Should log file access via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_file_access(
            file_path="/data/reports/sales.pdf",
            access_type=AccessType.READ,
            bytes_accessed=10000,
        )
        
        assert event.data_source == DataSource.FILE_SYSTEM
    
    @pytest.mark.asyncio
    async def test_log_api_access_function(self):
        """Should log API access via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_api_access(
            endpoint="/api/orders/123",
            method="DELETE",
            user_id="admin",
        )
        
        assert event.access_type == AccessType.DELETE
        assert event.data_source == DataSource.API
    
    @pytest.mark.asyncio
    async def test_log_bulk_export_function(self):
        """Should log bulk export via convenience function."""
        DataAccessLogger.configure(config=DataAccessConfig(
            enabled=True,
            batch_enabled=False,
        ))
        
        event = await log_bulk_export(
            resource_type="invoices",
            records=1000,
            bytes_accessed=500000,
            user_id="accountant",
            reason="End of quarter reporting",
        )
        
        assert event.access_type == AccessType.EXPORT
        assert event.reason == "End of quarter reporting"


# =============================================================================
# Test: Sampling
# =============================================================================

class TestSampling:
    """Test sampling behavior."""
    
    @pytest.mark.asyncio
    async def test_always_log_sensitive(self):
        """Should always log sensitive data."""
        config = DataAccessConfig(
            enabled=True,
            sample_rate=0.0,  # Sample nothing
            always_log_sensitive=True,
            batch_enabled=False,  # Immediate storage for testing
        )
        storage = InMemoryDataAccessStorage()
        logger = DataAccessLogger(config=config, storage=storage)
        
        # Log sensitive data
        await logger.log_database_read(
            table="users",  # Will be categorized as PERSONAL (sensitive)
            user_id="user-123",
        )
        
        # Should be logged despite 0% sample rate
        results = await storage.query()
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_always_log_writes(self):
        """Should always log write operations."""
        config = DataAccessConfig(
            enabled=True,
            sample_rate=0.0,  # Sample nothing
            always_log_writes=True,
            batch_enabled=False,  # Immediate storage for testing
        )
        storage = InMemoryDataAccessStorage()
        logger = DataAccessLogger(config=config, storage=storage)
        
        # Log a write
        await logger.log_database_write(
            table="logs",
            operation="insert",
            user_id="service",
        )
        
        # Should be logged despite 0% sample rate
        results = await storage.query()
        assert len(results) == 1


# =============================================================================
# Test: Batching
# =============================================================================

class TestBatching:
    """Test batch behavior."""
    
    @pytest.mark.asyncio
    async def test_batch_accumulation(self):
        """Should accumulate events in batch."""
        config = DataAccessConfig(
            enabled=True,
            batch_enabled=True,
            batch_size=5,
        )
        storage = InMemoryDataAccessStorage()
        logger = DataAccessLogger(config=config, storage=storage)
        
        # Log fewer than batch size
        for i in range(3):
            await logger.log_database_read(table="test", user_id=f"user-{i}")
        
        # Nothing stored yet (batch not full)
        results = await storage.query()
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_batch_flush_on_full(self):
        """Should flush when batch is full."""
        config = DataAccessConfig(
            enabled=True,
            batch_enabled=True,
            batch_size=5,
        )
        storage = InMemoryDataAccessStorage()
        logger = DataAccessLogger(config=config, storage=storage)
        
        # Log exactly batch size
        for i in range(5):
            await logger.log_database_read(table="test", user_id=f"user-{i}")
        
        # Should be stored now
        results = await storage.query()
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_manual_flush(self):
        """Should flush on manual request."""
        config = DataAccessConfig(
            enabled=True,
            batch_enabled=True,
            batch_size=10,
        )
        storage = InMemoryDataAccessStorage()
        logger = DataAccessLogger(config=config, storage=storage)
        
        # Log a few events
        for i in range(3):
            await logger.log_database_read(table="test", user_id=f"user-{i}")
        
        # Manual flush
        await logger.flush_batch()
        
        results = await storage.query()
        assert len(results) == 3
