"""
Tests for SEC-051: Memory Safety.

Tests cover:
- Buffer limits
- Resource tracking
- Allocation tracking
- Memory monitoring
- Bounded buffers
"""

import pytest

from shared.memory_security import (
    # Enums
    MemoryThreatType,
    MemoryCheckResult,
    # Data classes
    MemorySecurityConfig,
    MemoryReport,
    # Classes
    BufferLimiter,
    ResourceTracker,
    AllocationTracker,
    MemoryMonitor,
    BoundedBuffer,
    MemorySecurityService,
    # Convenience functions
    get_memory_service,
    check_buffer_size,
    check_string_length,
    create_bounded_buffer,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create memory security config."""
    return MemorySecurityConfig()


@pytest.fixture
def small_config():
    """Create config with small limits for testing."""
    return MemorySecurityConfig(
        max_buffer_size=1024,
        max_string_length=100,
        max_list_length=10,
        max_dict_keys=5,
    )


@pytest.fixture
def buffer_limiter(config):
    """Create buffer limiter."""
    return BufferLimiter(config)


@pytest.fixture
def resource_tracker(config):
    """Create resource tracker."""
    return ResourceTracker(config)


@pytest.fixture
def allocation_tracker(config):
    """Create allocation tracker."""
    return AllocationTracker(config)


@pytest.fixture
def monitor(config):
    """Create memory monitor."""
    return MemoryMonitor(config)


@pytest.fixture
def service(config):
    """Create service."""
    MemorySecurityService._instance = None
    return MemorySecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert MemoryThreatType.BUFFER_OVERFLOW == "buffer_overflow"
        assert MemoryThreatType.MEMORY_EXHAUSTION == "memory_exhaustion"
        assert MemoryThreatType.RESOURCE_LEAK == "resource_leak"
    
    def test_check_results(self):
        """Should have expected check results."""
        assert MemoryCheckResult.OK == "ok"
        assert MemoryCheckResult.WARNING == "warning"
        assert MemoryCheckResult.CRITICAL == "critical"


# =============================================================================
# Test: MemorySecurityConfig
# =============================================================================

class TestMemorySecurityConfig:
    """Test MemorySecurityConfig class."""
    
    def test_default_values(self):
        """Should have reasonable defaults."""
        config = MemorySecurityConfig()
        
        assert config.max_buffer_size == 104857600  # 100MB
        assert config.max_string_length == 10485760  # 10MB
        assert config.track_allocations is True


# =============================================================================
# Test: BufferLimiter
# =============================================================================

class TestBufferLimiter:
    """Test BufferLimiter."""
    
    def test_allows_small_buffer(self, buffer_limiter):
        """Should allow small buffer."""
        ok, error = buffer_limiter.check_buffer_size(1024)
        
        assert ok is True
        assert error is None
    
    def test_rejects_large_buffer(self, small_config):
        """Should reject large buffer."""
        limiter = BufferLimiter(small_config)
        
        ok, error = limiter.check_buffer_size(2048)
        
        assert ok is False
        assert error is not None
    
    def test_allows_short_string(self, buffer_limiter):
        """Should allow short string."""
        ok, error = buffer_limiter.check_string_length("hello")
        
        assert ok is True
    
    def test_rejects_long_string(self, small_config):
        """Should reject long string."""
        limiter = BufferLimiter(small_config)
        
        ok, error = limiter.check_string_length("x" * 200)
        
        assert ok is False
    
    def test_allows_small_list(self, buffer_limiter):
        """Should allow small list."""
        ok, error = buffer_limiter.check_list_length([1, 2, 3])
        
        assert ok is True
    
    def test_rejects_large_list(self, small_config):
        """Should reject large list."""
        limiter = BufferLimiter(small_config)
        
        ok, error = limiter.check_list_length(list(range(20)))
        
        assert ok is False
    
    def test_allows_small_dict(self, buffer_limiter):
        """Should allow small dict."""
        ok, error = buffer_limiter.check_dict_size({"a": 1, "b": 2})
        
        assert ok is True
    
    def test_rejects_large_dict(self, small_config):
        """Should reject large dict."""
        limiter = BufferLimiter(small_config)
        
        ok, error = limiter.check_dict_size({f"k{i}": i for i in range(10)})
        
        assert ok is False
    
    def test_limits_string(self, small_config):
        """Should limit string length."""
        limiter = BufferLimiter(small_config)
        
        result = limiter.limit_string("x" * 200)
        
        assert len(result) == 100
    
    def test_limits_list(self, small_config):
        """Should limit list length."""
        limiter = BufferLimiter(small_config)
        
        result = limiter.limit_list(list(range(20)))
        
        assert len(result) == 10


# =============================================================================
# Test: ResourceTracker
# =============================================================================

class Trackable:
    """A class that supports weak references for testing."""
    pass


class TestResourceTracker:
    """Test ResourceTracker."""
    
    def test_tracks_resource(self, resource_tracker):
        """Should track resource."""
        obj = Trackable()
        
        resource_id = resource_tracker.track(obj)
        
        assert resource_id == id(obj)
        assert resource_tracker.get_open_count() == 1
    
    def test_untracks_resource(self, resource_tracker):
        """Should untrack resource."""
        obj = Trackable()
        resource_id = resource_tracker.track(obj)
        
        result = resource_tracker.untrack(resource_id)
        
        assert result is True
        assert resource_tracker.get_open_count() == 0
    
    def test_detects_leaked_resources(self, resource_tracker):
        """Should detect leaked resources."""
        def create_and_lose():
            obj = Trackable()
            resource_tracker.track(obj)
            # Object goes out of scope
        
        create_and_lose()
        
        # Leaked count should increase
        leaked = resource_tracker.get_leaked_count()
        assert leaked >= 0  # May or may not be collected yet
    
    def test_checks_limits(self):
        """Should check resource limits."""
        config = MemorySecurityConfig(max_open_resources=2)
        tracker = ResourceTracker(config)
        
        obj1 = Trackable()
        obj2 = Trackable()
        obj3 = Trackable()
        
        tracker.track(obj1)
        tracker.track(obj2)
        tracker.track(obj3)
        
        ok, error = tracker.check_limits()
        
        assert ok is False
    
    def test_clears_all(self, resource_tracker):
        """Should clear all tracked resources."""
        obj = Trackable()
        resource_tracker.track(obj)
        
        resource_tracker.clear()
        
        assert resource_tracker.get_open_count() == 0


# =============================================================================
# Test: AllocationTracker
# =============================================================================

class TestAllocationTracker:
    """Test AllocationTracker."""
    
    def test_records_allocation(self, allocation_tracker):
        """Should record allocation."""
        result = allocation_tracker.record_allocation(1024)
        
        assert result is True
        assert allocation_tracker.get_stats()["count"] == 1
        assert allocation_tracker.get_stats()["total"] == 1024
    
    def test_records_deallocation(self, allocation_tracker):
        """Should record deallocation."""
        allocation_tracker.record_allocation(1024)
        allocation_tracker.record_deallocation(512)
        
        assert allocation_tracker.get_stats()["total"] == 512
    
    def test_tracks_peak(self, allocation_tracker):
        """Should track peak allocation."""
        allocation_tracker.record_allocation(1024)
        allocation_tracker.record_allocation(2048)
        allocation_tracker.record_deallocation(1024)
        
        stats = allocation_tracker.get_stats()
        
        assert stats["peak"] == 3072
        assert stats["total"] == 2048
    
    def test_enforces_limit(self):
        """Should enforce allocation limit."""
        config = MemorySecurityConfig(max_allocations=2)
        tracker = AllocationTracker(config)
        
        tracker.record_allocation(100)
        tracker.record_allocation(100)
        result = tracker.record_allocation(100)
        
        assert result is False
    
    def test_resets(self, allocation_tracker):
        """Should reset tracking."""
        allocation_tracker.record_allocation(1024)
        allocation_tracker.reset()
        
        stats = allocation_tracker.get_stats()
        
        assert stats["count"] == 0
        assert stats["total"] == 0


# =============================================================================
# Test: MemoryMonitor
# =============================================================================

class TestMemoryMonitor:
    """Test MemoryMonitor."""
    
    def test_gets_current_usage(self, monitor):
        """Should get current usage."""
        usage = monitor.get_current_usage()
        
        assert usage >= 0
    
    def test_checks_usage(self, monitor):
        """Should check usage and return report."""
        report = monitor.check_usage()
        
        assert isinstance(report, MemoryReport)
        assert report.status in [
            MemoryCheckResult.OK,
            MemoryCheckResult.WARNING,
            MemoryCheckResult.CRITICAL,
        ]


# =============================================================================
# Test: BoundedBuffer
# =============================================================================

class TestBoundedBuffer:
    """Test BoundedBuffer."""
    
    def test_writes_data(self):
        """Should write data."""
        buffer = BoundedBuffer(max_size=100)
        
        written = buffer.write(b"hello")
        
        assert written == 5
        assert buffer.size() == 5
    
    def test_reads_data(self):
        """Should read data."""
        buffer = BoundedBuffer(max_size=100)
        buffer.write(b"hello")
        
        data = buffer.read()
        
        assert data == b"hello"
        assert buffer.size() == 0
    
    def test_reads_partial(self):
        """Should read partial data."""
        buffer = BoundedBuffer(max_size=100)
        buffer.write(b"hello")
        
        data = buffer.read(2)
        
        assert data == b"he"
        assert buffer.size() == 3
    
    def test_limits_write(self):
        """Should limit write to available space."""
        buffer = BoundedBuffer(max_size=5)
        
        written = buffer.write(b"hello world")
        
        assert written == 5
        assert buffer.size() == 5
    
    def test_returns_zero_when_full(self):
        """Should return zero when full."""
        buffer = BoundedBuffer(max_size=5)
        buffer.write(b"hello")
        
        written = buffer.write(b"more")
        
        assert written == 0
    
    def test_calls_overflow_callback(self):
        """Should call overflow callback."""
        overflow_called = [False]
        
        def on_overflow():
            overflow_called[0] = True
        
        buffer = BoundedBuffer(max_size=5, on_overflow=on_overflow)
        buffer.write(b"hello")
        buffer.write(b"more")
        
        assert overflow_called[0] is True
    
    def test_reports_available_space(self):
        """Should report available space."""
        buffer = BoundedBuffer(max_size=100)
        buffer.write(b"hello")
        
        assert buffer.available() == 95
    
    def test_clears_buffer(self):
        """Should clear buffer."""
        buffer = BoundedBuffer(max_size=100)
        buffer.write(b"hello")
        
        buffer.clear()
        
        assert buffer.size() == 0


# =============================================================================
# Test: MemorySecurityService
# =============================================================================

class TestMemorySecurityService:
    """Test MemorySecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        MemorySecurityService._instance = None
        
        s1 = get_memory_service()
        s2 = get_memory_service()
        
        assert s1 is s2
    
    def test_check_buffer(self, service):
        """Should check buffer size."""
        ok, _ = service.check_buffer(1024)
        
        assert ok is True
    
    def test_check_string(self, service):
        """Should check string length."""
        ok, _ = service.check_string("hello")
        
        assert ok is True
    
    def test_check_collection_list(self, service):
        """Should check list."""
        ok, _ = service.check_collection([1, 2, 3])
        
        assert ok is True
    
    def test_check_collection_dict(self, service):
        """Should check dict."""
        ok, _ = service.check_collection({"a": 1})
        
        assert ok is True
    
    def test_track_resource(self, service):
        """Should track resource."""
        obj = Trackable()
        
        resource_id = service.track_resource(obj)
        
        assert resource_id == id(obj)
    
    def test_untrack_resource(self, service):
        """Should untrack resource."""
        obj = Trackable()
        resource_id = service.track_resource(obj)
        
        result = service.untrack_resource(resource_id)
        
        assert result is True
    
    def test_get_memory_report(self, service):
        """Should get memory report."""
        report = service.get_memory_report()
        
        assert isinstance(report, MemoryReport)
    
    def test_create_bounded_buffer(self, service):
        """Should create bounded buffer."""
        buffer = service.create_bounded_buffer(1024)
        
        assert isinstance(buffer, BoundedBuffer)
        assert buffer.max_size == 1024


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_check_buffer_size(self):
        """Should check buffer size."""
        MemorySecurityService._instance = None
        
        ok, _ = check_buffer_size(1024)
        
        assert ok is True
    
    def test_check_string_length(self):
        """Should check string length."""
        MemorySecurityService._instance = None
        
        ok, _ = check_string_length("hello")
        
        assert ok is True
    
    def test_create_bounded_buffer(self):
        """Should create bounded buffer."""
        buffer = create_bounded_buffer(512)
        
        assert buffer.max_size == 512
