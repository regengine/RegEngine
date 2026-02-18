"""
SEC-052: Concurrency Security.

Secure concurrency controls including race condition prevention,
deadlock detection, and thread-safe operations.
"""

import asyncio
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar


T = TypeVar("T")


class ConcurrencyThreatType(str, Enum):
    """Types of concurrency threats."""
    RACE_CONDITION = "race_condition"
    DEADLOCK = "deadlock"
    STARVATION = "starvation"
    RESOURCE_CONTENTION = "resource_contention"
    TOCTOU = "toctou"  # Time-of-check to time-of-use


class LockStatus(str, Enum):
    """Lock status types."""
    ACQUIRED = "acquired"
    RELEASED = "released"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass
class ConcurrencyConfig:
    """Configuration for concurrency security."""
    
    # Timeouts
    default_lock_timeout: float = 30.0
    deadlock_detection_timeout: float = 60.0
    
    # Limits
    max_concurrent_locks: int = 100
    max_lock_wait_time: float = 60.0
    max_reentrant_depth: int = 10
    
    # Features
    enable_deadlock_detection: bool = True
    enable_lock_ordering: bool = True
    track_lock_history: bool = True


@dataclass
class LockInfo:
    """Information about a lock."""
    
    name: str
    thread_id: int
    acquired_at: float
    timeout: float
    reentrant_count: int = 1
    status: LockStatus = LockStatus.ACQUIRED


class TimeoutLock:
    """A lock with timeout support."""
    
    def __init__(
        self,
        name: str = "",
        timeout: float = 30.0,
    ):
        self.name = name or f"lock_{id(self)}"
        self.timeout = timeout
        self._lock = threading.RLock()
        self._owner: Optional[int] = None
        self._count = 0
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire the lock with timeout."""
        timeout = timeout or self.timeout
        
        acquired = self._lock.acquire(timeout=timeout)
        
        if acquired:
            self._owner = threading.current_thread().ident
            self._count += 1
        
        return acquired
    
    def release(self) -> bool:
        """Release the lock."""
        if self._owner != threading.current_thread().ident:
            return False
        
        self._count -= 1
        if self._count == 0:
            self._owner = None
        
        self._lock.release()
        return True
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
    
    @property
    def locked(self) -> bool:
        """Check if lock is held."""
        return self._owner is not None
    
    @property
    def owner(self) -> Optional[int]:
        """Get owner thread ID."""
        return self._owner


class LockManager:
    """Manages multiple locks with deadlock prevention."""
    
    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        self.config = config or ConcurrencyConfig()
        self._locks: dict[str, TimeoutLock] = {}
        self._lock_order: dict[str, int] = {}
        self._order_counter = 0
        self._manager_lock = threading.Lock()
        self._lock_history: list[LockInfo] = []
    
    def get_lock(self, name: str, timeout: Optional[float] = None) -> TimeoutLock:
        """Get or create a lock by name."""
        with self._manager_lock:
            if name not in self._locks:
                self._locks[name] = TimeoutLock(
                    name=name,
                    timeout=timeout or self.config.default_lock_timeout,
                )
                self._lock_order[name] = self._order_counter
                self._order_counter += 1
            
            return self._locks[name]
    
    def acquire_multiple(
        self,
        lock_names: list[str],
        timeout: Optional[float] = None,
    ) -> bool:
        """Acquire multiple locks in consistent order to prevent deadlock."""
        # Sort locks by their order to prevent deadlock
        if self.config.enable_lock_ordering:
            sorted_names = sorted(
                lock_names,
                key=lambda n: self._lock_order.get(n, float("inf")),
            )
        else:
            sorted_names = lock_names
        
        acquired = []
        try:
            for name in sorted_names:
                lock = self.get_lock(name, timeout)
                if not lock.acquire(timeout):
                    # Release already acquired locks
                    for acq_name in reversed(acquired):
                        self._locks[acq_name].release()
                    return False
                acquired.append(name)
            return True
        except Exception:
            # Release on any exception
            for acq_name in reversed(acquired):
                self._locks[acq_name].release()
            raise
    
    def release_multiple(self, lock_names: list[str]) -> None:
        """Release multiple locks."""
        for name in reversed(lock_names):
            if name in self._locks:
                self._locks[name].release()
    
    @contextmanager
    def acquire_locks(
        self,
        lock_names: list[str],
        timeout: Optional[float] = None,
    ):
        """Context manager for acquiring multiple locks."""
        if not self.acquire_multiple(lock_names, timeout):
            raise TimeoutError(f"Could not acquire locks: {lock_names}")
        try:
            yield
        finally:
            self.release_multiple(lock_names)
    
    def get_lock_count(self) -> int:
        """Get number of managed locks."""
        return len(self._locks)


class AtomicCounter:
    """Thread-safe counter."""
    
    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()
    
    def increment(self, amount: int = 1) -> int:
        """Increment and return new value."""
        with self._lock:
            self._value += amount
            return self._value
    
    def decrement(self, amount: int = 1) -> int:
        """Decrement and return new value."""
        with self._lock:
            self._value -= amount
            return self._value
    
    def get(self) -> int:
        """Get current value."""
        with self._lock:
            return self._value
    
    def set(self, value: int) -> None:
        """Set value."""
        with self._lock:
            self._value = value
    
    def compare_and_swap(self, expected: int, new_value: int) -> bool:
        """Atomically compare and swap if value matches expected."""
        with self._lock:
            if self._value == expected:
                self._value = new_value
                return True
            return False


class ThreadSafeDict:
    """Thread-safe dictionary."""
    
    def __init__(self):
        self._dict: dict = {}
        self._lock = threading.RLock()
    
    def get(self, key: Any, default: Any = None) -> Any:
        """Get value by key."""
        with self._lock:
            return self._dict.get(key, default)
    
    def set(self, key: Any, value: Any) -> None:
        """Set value by key."""
        with self._lock:
            self._dict[key] = value
    
    def delete(self, key: Any) -> bool:
        """Delete key. Returns True if existed."""
        with self._lock:
            if key in self._dict:
                del self._dict[key]
                return True
            return False
    
    def pop(self, key: Any, default: Any = None) -> Any:
        """Pop and return value."""
        with self._lock:
            return self._dict.pop(key, default)
    
    def setdefault(self, key: Any, default: Any = None) -> Any:
        """Set default if key not present."""
        with self._lock:
            return self._dict.setdefault(key, default)
    
    def update(self, other: dict) -> None:
        """Update with another dict."""
        with self._lock:
            self._dict.update(other)
    
    def keys(self) -> list:
        """Get keys as list."""
        with self._lock:
            return list(self._dict.keys())
    
    def values(self) -> list:
        """Get values as list."""
        with self._lock:
            return list(self._dict.values())
    
    def items(self) -> list:
        """Get items as list."""
        with self._lock:
            return list(self._dict.items())
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._dict)
    
    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._dict


class RateLimiter:
    """Thread-safe rate limiter."""
    
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: OrderedDict[float, int] = OrderedDict()
        self._lock = threading.Lock()
    
    def allow(self) -> bool:
        """Check if request is allowed."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        with self._lock:
            # Remove old entries
            old_keys = [k for k in self._requests.keys() if k < cutoff]
            for k in old_keys:
                del self._requests[k]
            
            # Count current requests
            total = sum(self._requests.values())
            
            if total >= self.max_requests:
                return False
            
            # Add this request
            self._requests[now] = self._requests.get(now, 0) + 1
            return True
    
    def get_remaining(self) -> int:
        """Get remaining requests in window."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        with self._lock:
            total = sum(
                count for ts, count in self._requests.items()
                if ts >= cutoff
            )
            return max(0, self.max_requests - total)


def synchronized(lock: Optional[threading.Lock] = None):
    """Decorator for synchronized method execution."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        _lock = lock or threading.Lock()
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with _lock:
                return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


class ConcurrencySecurityService:
    """Comprehensive concurrency security service."""
    
    _instance: Optional["ConcurrencySecurityService"] = None
    
    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        self.config = config or ConcurrencyConfig()
        self.lock_manager = LockManager(self.config)
        self._counters: dict[str, AtomicCounter] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._service_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> "ConcurrencySecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: ConcurrencyConfig) -> "ConcurrencySecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def get_lock(self, name: str) -> TimeoutLock:
        """Get a named lock."""
        return self.lock_manager.get_lock(name)
    
    @contextmanager
    def acquire_locks(self, lock_names: list[str]):
        """Context manager for multiple locks."""
        with self.lock_manager.acquire_locks(lock_names):
            yield
    
    def get_counter(self, name: str, initial: int = 0) -> AtomicCounter:
        """Get or create a named counter."""
        with self._service_lock:
            if name not in self._counters:
                self._counters[name] = AtomicCounter(initial)
            return self._counters[name]
    
    def get_rate_limiter(
        self,
        name: str,
        max_requests: int = 100,
        window_seconds: float = 60.0,
    ) -> RateLimiter:
        """Get or create a named rate limiter."""
        with self._service_lock:
            if name not in self._rate_limiters:
                self._rate_limiters[name] = RateLimiter(
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                )
            return self._rate_limiters[name]
    
    def create_thread_safe_dict(self) -> ThreadSafeDict:
        """Create a new thread-safe dictionary."""
        return ThreadSafeDict()


# Convenience functions
def get_concurrency_service() -> ConcurrencySecurityService:
    """Get concurrency service instance."""
    return ConcurrencySecurityService.get_instance()


def get_lock(name: str) -> TimeoutLock:
    """Get a named lock."""
    return get_concurrency_service().get_lock(name)


def get_counter(name: str, initial: int = 0) -> AtomicCounter:
    """Get or create a named counter."""
    return get_concurrency_service().get_counter(name, initial)


def get_rate_limiter(
    name: str,
    max_requests: int = 100,
    window_seconds: float = 60.0,
) -> RateLimiter:
    """Get or create a named rate limiter."""
    return get_concurrency_service().get_rate_limiter(
        name, max_requests, window_seconds
    )
