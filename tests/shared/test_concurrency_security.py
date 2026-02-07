"""
Tests for SEC-052: Concurrency Security.

Tests cover:
- Timeout locks
- Lock management
- Atomic counters
- Thread-safe collections
- Rate limiting
"""

import threading
import time
import pytest

from shared.concurrency_security import (
    # Enums
    ConcurrencyThreatType,
    LockStatus,
    # Data classes
    ConcurrencyConfig,
    LockInfo,
    # Classes
    TimeoutLock,
    LockManager,
    AtomicCounter,
    ThreadSafeDict,
    RateLimiter,
    ConcurrencySecurityService,
    synchronized,
    # Convenience functions
    get_concurrency_service,
    get_lock,
    get_counter,
    get_rate_limiter,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create concurrency config."""
    return ConcurrencyConfig()


@pytest.fixture
def lock():
    """Create timeout lock."""
    return TimeoutLock(name="test_lock", timeout=5.0)


@pytest.fixture
def lock_manager(config):
    """Create lock manager."""
    return LockManager(config)


@pytest.fixture
def counter():
    """Create atomic counter."""
    return AtomicCounter()


@pytest.fixture
def thread_safe_dict():
    """Create thread-safe dict."""
    return ThreadSafeDict()


@pytest.fixture
def rate_limiter():
    """Create rate limiter."""
    return RateLimiter(max_requests=10, window_seconds=1.0)


@pytest.fixture
def service(config):
    """Create service."""
    ConcurrencySecurityService._instance = None
    return ConcurrencySecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert ConcurrencyThreatType.RACE_CONDITION == "race_condition"
        assert ConcurrencyThreatType.DEADLOCK == "deadlock"
        assert ConcurrencyThreatType.TOCTOU == "toctou"
    
    def test_lock_status(self):
        """Should have expected lock status."""
        assert LockStatus.ACQUIRED == "acquired"
        assert LockStatus.RELEASED == "released"
        assert LockStatus.TIMEOUT == "timeout"


# =============================================================================
# Test: ConcurrencyConfig
# =============================================================================

class TestConcurrencyConfig:
    """Test ConcurrencyConfig class."""
    
    def test_default_values(self):
        """Should have reasonable defaults."""
        config = ConcurrencyConfig()
        
        assert config.default_lock_timeout == 30.0
        assert config.enable_deadlock_detection is True
        assert config.max_concurrent_locks == 100


# =============================================================================
# Test: TimeoutLock
# =============================================================================

class TestTimeoutLock:
    """Test TimeoutLock."""
    
    def test_acquires_lock(self, lock):
        """Should acquire lock."""
        result = lock.acquire()
        
        assert result is True
        assert lock.locked is True
        
        lock.release()
    
    def test_releases_lock(self, lock):
        """Should release lock."""
        lock.acquire()
        result = lock.release()
        
        assert result is True
        assert lock.locked is False
    
    def test_context_manager(self, lock):
        """Should work as context manager."""
        with lock:
            assert lock.locked is True
        
        assert lock.locked is False
    
    def test_reentrant(self, lock):
        """Should support reentrant acquisition."""
        lock.acquire()
        lock.acquire()  # Second acquire should succeed
        
        assert lock._count == 2
        
        lock.release()
        lock.release()
    
    def test_tracks_owner(self, lock):
        """Should track owner thread."""
        lock.acquire()
        
        assert lock.owner == threading.current_thread().ident
        
        lock.release()
    
    def test_timeout(self):
        """Should timeout if lock not available."""
        lock = TimeoutLock(timeout=0.1)
        
        # Hold lock in another thread
        def hold_lock():
            lock.acquire()
            time.sleep(0.5)
            lock.release()
        
        thread = threading.Thread(target=hold_lock)
        thread.start()
        
        time.sleep(0.05)  # Let other thread acquire
        
        result = lock.acquire(timeout=0.1)
        
        assert result is False
        
        thread.join()


# =============================================================================
# Test: LockManager
# =============================================================================

class TestLockManager:
    """Test LockManager."""
    
    def test_creates_lock(self, lock_manager):
        """Should create lock on demand."""
        lock = lock_manager.get_lock("test")
        
        assert lock is not None
        assert lock.name == "test"
    
    def test_returns_same_lock(self, lock_manager):
        """Should return same lock for same name."""
        lock1 = lock_manager.get_lock("test")
        lock2 = lock_manager.get_lock("test")
        
        assert lock1 is lock2
    
    def test_acquires_multiple(self, lock_manager):
        """Should acquire multiple locks."""
        result = lock_manager.acquire_multiple(["lock1", "lock2"])
        
        assert result is True
        
        lock_manager.release_multiple(["lock1", "lock2"])
    
    def test_context_manager_multiple(self, lock_manager):
        """Should work as context manager for multiple locks."""
        with lock_manager.acquire_locks(["lock1", "lock2"]):
            lock1 = lock_manager.get_lock("lock1")
            lock2 = lock_manager.get_lock("lock2")
            
            assert lock1.locked is True
            assert lock2.locked is True
    
    def test_counts_locks(self, lock_manager):
        """Should count managed locks."""
        lock_manager.get_lock("lock1")
        lock_manager.get_lock("lock2")
        
        assert lock_manager.get_lock_count() == 2


# =============================================================================
# Test: AtomicCounter
# =============================================================================

class TestAtomicCounter:
    """Test AtomicCounter."""
    
    def test_initial_value(self):
        """Should have initial value."""
        counter = AtomicCounter(10)
        
        assert counter.get() == 10
    
    def test_increment(self, counter):
        """Should increment."""
        result = counter.increment()
        
        assert result == 1
        assert counter.get() == 1
    
    def test_decrement(self, counter):
        """Should decrement."""
        counter.set(10)
        result = counter.decrement()
        
        assert result == 9
    
    def test_increment_amount(self, counter):
        """Should increment by amount."""
        result = counter.increment(5)
        
        assert result == 5
    
    def test_set(self, counter):
        """Should set value."""
        counter.set(42)
        
        assert counter.get() == 42
    
    def test_compare_and_swap_success(self, counter):
        """Should swap when value matches."""
        counter.set(10)
        
        result = counter.compare_and_swap(10, 20)
        
        assert result is True
        assert counter.get() == 20
    
    def test_compare_and_swap_failure(self, counter):
        """Should not swap when value differs."""
        counter.set(10)
        
        result = counter.compare_and_swap(5, 20)
        
        assert result is False
        assert counter.get() == 10
    
    def test_thread_safety(self, counter):
        """Should be thread-safe."""
        threads = []
        
        def increment_many():
            for _ in range(1000):
                counter.increment()
        
        for _ in range(10):
            t = threading.Thread(target=increment_many)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert counter.get() == 10000


# =============================================================================
# Test: ThreadSafeDict
# =============================================================================

class TestThreadSafeDict:
    """Test ThreadSafeDict."""
    
    def test_set_and_get(self, thread_safe_dict):
        """Should set and get values."""
        thread_safe_dict.set("key", "value")
        
        assert thread_safe_dict.get("key") == "value"
    
    def test_get_default(self, thread_safe_dict):
        """Should return default for missing key."""
        result = thread_safe_dict.get("missing", "default")
        
        assert result == "default"
    
    def test_delete(self, thread_safe_dict):
        """Should delete key."""
        thread_safe_dict.set("key", "value")
        
        result = thread_safe_dict.delete("key")
        
        assert result is True
        assert thread_safe_dict.get("key") is None
    
    def test_pop(self, thread_safe_dict):
        """Should pop value."""
        thread_safe_dict.set("key", "value")
        
        result = thread_safe_dict.pop("key")
        
        assert result == "value"
        assert "key" not in thread_safe_dict
    
    def test_setdefault(self, thread_safe_dict):
        """Should set default if not present."""
        result1 = thread_safe_dict.setdefault("key", "default")
        result2 = thread_safe_dict.setdefault("key", "other")
        
        assert result1 == "default"
        assert result2 == "default"
    
    def test_update(self, thread_safe_dict):
        """Should update with dict."""
        thread_safe_dict.update({"a": 1, "b": 2})
        
        assert thread_safe_dict.get("a") == 1
        assert thread_safe_dict.get("b") == 2
    
    def test_keys(self, thread_safe_dict):
        """Should return keys."""
        thread_safe_dict.set("a", 1)
        thread_safe_dict.set("b", 2)
        
        keys = thread_safe_dict.keys()
        
        assert set(keys) == {"a", "b"}
    
    def test_values(self, thread_safe_dict):
        """Should return values."""
        thread_safe_dict.set("a", 1)
        thread_safe_dict.set("b", 2)
        
        values = thread_safe_dict.values()
        
        assert set(values) == {1, 2}
    
    def test_items(self, thread_safe_dict):
        """Should return items."""
        thread_safe_dict.set("a", 1)
        
        items = thread_safe_dict.items()
        
        assert ("a", 1) in items
    
    def test_len(self, thread_safe_dict):
        """Should return length."""
        thread_safe_dict.set("a", 1)
        thread_safe_dict.set("b", 2)
        
        assert len(thread_safe_dict) == 2
    
    def test_contains(self, thread_safe_dict):
        """Should check contains."""
        thread_safe_dict.set("key", "value")
        
        assert "key" in thread_safe_dict
        assert "missing" not in thread_safe_dict


# =============================================================================
# Test: RateLimiter
# =============================================================================

class TestRateLimiter:
    """Test RateLimiter."""
    
    def test_allows_requests(self, rate_limiter):
        """Should allow requests within limit."""
        for _ in range(10):
            assert rate_limiter.allow() is True
    
    def test_blocks_excess(self, rate_limiter):
        """Should block requests over limit."""
        for _ in range(10):
            rate_limiter.allow()
        
        assert rate_limiter.allow() is False
    
    def test_resets_after_window(self):
        """Should reset after time window."""
        limiter = RateLimiter(max_requests=2, window_seconds=0.1)
        
        limiter.allow()
        limiter.allow()
        assert limiter.allow() is False
        
        time.sleep(0.15)
        
        assert limiter.allow() is True
    
    def test_get_remaining(self, rate_limiter):
        """Should report remaining requests."""
        assert rate_limiter.get_remaining() == 10
        
        rate_limiter.allow()
        rate_limiter.allow()
        
        assert rate_limiter.get_remaining() == 8


# =============================================================================
# Test: synchronized decorator
# =============================================================================

class TestSynchronized:
    """Test synchronized decorator."""
    
    def test_synchronizes_access(self):
        """Should synchronize method access."""
        results = []
        
        @synchronized()
        def append_items():
            for i in range(100):
                results.append(i)
                time.sleep(0.001)
        
        threads = [
            threading.Thread(target=append_items)
            for _ in range(3)
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Results should be in groups of 100 (not interleaved)
        assert len(results) == 300


# =============================================================================
# Test: ConcurrencySecurityService
# =============================================================================

class TestConcurrencySecurityService:
    """Test ConcurrencySecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        ConcurrencySecurityService._instance = None
        
        s1 = get_concurrency_service()
        s2 = get_concurrency_service()
        
        assert s1 is s2
    
    def test_get_lock(self, service):
        """Should get lock."""
        lock = service.get_lock("test")
        
        assert lock is not None
        assert isinstance(lock, TimeoutLock)
    
    def test_acquire_locks_context(self, service):
        """Should acquire multiple locks."""
        with service.acquire_locks(["lock1", "lock2"]):
            lock1 = service.get_lock("lock1")
            assert lock1.locked is True
    
    def test_get_counter(self, service):
        """Should get or create counter."""
        counter1 = service.get_counter("test")
        counter2 = service.get_counter("test")
        
        assert counter1 is counter2
    
    def test_get_counter_initial(self, service):
        """Should set initial value."""
        counter = service.get_counter("new", initial=10)
        
        assert counter.get() == 10
    
    def test_get_rate_limiter(self, service):
        """Should get or create rate limiter."""
        limiter1 = service.get_rate_limiter("test")
        limiter2 = service.get_rate_limiter("test")
        
        assert limiter1 is limiter2
    
    def test_create_thread_safe_dict(self, service):
        """Should create thread-safe dict."""
        d = service.create_thread_safe_dict()
        
        assert isinstance(d, ThreadSafeDict)


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_lock(self):
        """Should get lock."""
        ConcurrencySecurityService._instance = None
        
        lock = get_lock("test")
        
        assert isinstance(lock, TimeoutLock)
    
    def test_get_counter(self):
        """Should get counter."""
        ConcurrencySecurityService._instance = None
        
        counter = get_counter("test")
        
        assert isinstance(counter, AtomicCounter)
    
    def test_get_rate_limiter(self):
        """Should get rate limiter."""
        ConcurrencySecurityService._instance = None
        
        limiter = get_rate_limiter("test")
        
        assert isinstance(limiter, RateLimiter)
