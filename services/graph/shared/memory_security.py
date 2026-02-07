"""
SEC-051: Memory Safety.

Memory safety controls including buffer limits,
resource tracking, and memory leak prevention.
"""

import gc
import sys
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class MemoryThreatType(str, Enum):
    """Types of memory threats."""
    BUFFER_OVERFLOW = "buffer_overflow"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    RESOURCE_LEAK = "resource_leak"
    UNBOUNDED_GROWTH = "unbounded_growth"
    ALLOCATION_LIMIT = "allocation_limit"


class MemoryCheckResult(str, Enum):
    """Memory check result types."""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MemorySecurityConfig:
    """Configuration for memory security."""
    
    # Buffer limits
    max_buffer_size: int = 104857600  # 100MB
    max_string_length: int = 10485760  # 10MB
    max_list_length: int = 1000000
    max_dict_keys: int = 100000
    
    # Resource limits
    max_open_resources: int = 1000
    max_allocations: int = 10000
    
    # Monitoring
    track_allocations: bool = True
    warn_threshold_mb: int = 500
    critical_threshold_mb: int = 1000


@dataclass
class MemoryReport:
    """Memory usage report."""
    
    status: MemoryCheckResult
    current_usage_bytes: int
    peak_usage_bytes: int
    allocation_count: int
    warnings: list = field(default_factory=list)
    threats_detected: list = field(default_factory=list)


class BufferLimiter:
    """Limits buffer and collection sizes."""
    
    def __init__(self, config: Optional[MemorySecurityConfig] = None):
        self.config = config or MemorySecurityConfig()
    
    def check_buffer_size(self, size: int) -> tuple[bool, Optional[str]]:
        """Check if buffer size is within limits."""
        if size > self.config.max_buffer_size:
            return False, f"Buffer size {size} exceeds limit {self.config.max_buffer_size}"
        return True, None
    
    def check_string_length(self, s: str) -> tuple[bool, Optional[str]]:
        """Check if string length is within limits."""
        length = len(s)
        if length > self.config.max_string_length:
            return False, f"String length {length} exceeds limit {self.config.max_string_length}"
        return True, None
    
    def check_list_length(self, lst: list) -> tuple[bool, Optional[str]]:
        """Check if list length is within limits."""
        length = len(lst)
        if length > self.config.max_list_length:
            return False, f"List length {length} exceeds limit {self.config.max_list_length}"
        return True, None
    
    def check_dict_size(self, d: dict) -> tuple[bool, Optional[str]]:
        """Check if dict size is within limits."""
        size = len(d)
        if size > self.config.max_dict_keys:
            return False, f"Dict keys {size} exceeds limit {self.config.max_dict_keys}"
        return True, None
    
    def limit_string(self, s: str, max_length: Optional[int] = None) -> str:
        """Limit string to maximum length."""
        limit = max_length or self.config.max_string_length
        if len(s) > limit:
            return s[:limit]
        return s
    
    def limit_list(self, lst: list, max_length: Optional[int] = None) -> list:
        """Limit list to maximum length."""
        limit = max_length or self.config.max_list_length
        if len(lst) > limit:
            return lst[:limit]
        return lst


class ResourceTracker:
    """Tracks open resources for leak detection."""
    
    def __init__(self, config: Optional[MemorySecurityConfig] = None):
        self.config = config or MemorySecurityConfig()
        self._resources: dict[int, weakref.ref] = {}
        self._resource_count = 0
        self._leaked_count = 0
    
    def track(self, resource: Any, name: Optional[str] = None) -> int:
        """Track a resource and return its ID."""
        resource_id = id(resource)
        self._resources[resource_id] = weakref.ref(resource)
        self._resource_count += 1
        return resource_id
    
    def untrack(self, resource_id: int) -> bool:
        """Untrack a resource."""
        if resource_id in self._resources:
            del self._resources[resource_id]
            return True
        return False
    
    def get_open_count(self) -> int:
        """Get count of still-open resources."""
        # Clean up dead references
        dead = [
            rid for rid, ref in self._resources.items()
            if ref() is None
        ]
        for rid in dead:
            del self._resources[rid]
            self._leaked_count += 1
        
        return len(self._resources)
    
    def get_leaked_count(self) -> int:
        """Get count of leaked resources."""
        self.get_open_count()  # Trigger cleanup
        return self._leaked_count
    
    def check_limits(self) -> tuple[bool, Optional[str]]:
        """Check if resource limits are exceeded."""
        count = self.get_open_count()
        if count > self.config.max_open_resources:
            return False, f"Open resources {count} exceeds limit {self.config.max_open_resources}"
        return True, None
    
    def clear(self) -> None:
        """Clear all tracked resources."""
        self._resources.clear()
        self._resource_count = 0
        self._leaked_count = 0


class AllocationTracker:
    """Tracks memory allocations."""
    
    def __init__(self, config: Optional[MemorySecurityConfig] = None):
        self.config = config or MemorySecurityConfig()
        self._allocation_count = 0
        self._total_allocated = 0
        self._peak_allocated = 0
    
    def record_allocation(self, size: int) -> bool:
        """Record an allocation. Returns False if limit exceeded."""
        if self._allocation_count >= self.config.max_allocations:
            return False
        
        self._allocation_count += 1
        self._total_allocated += size
        
        if self._total_allocated > self._peak_allocated:
            self._peak_allocated = self._total_allocated
        
        return True
    
    def record_deallocation(self, size: int) -> None:
        """Record a deallocation."""
        self._total_allocated = max(0, self._total_allocated - size)
    
    def get_stats(self) -> dict:
        """Get allocation statistics."""
        return {
            "count": self._allocation_count,
            "total": self._total_allocated,
            "peak": self._peak_allocated,
        }
    
    def check_limits(self) -> tuple[bool, Optional[str]]:
        """Check if allocation limits are exceeded."""
        if self._allocation_count > self.config.max_allocations:
            return False, f"Allocations {self._allocation_count} exceeds limit"
        return True, None
    
    def reset(self) -> None:
        """Reset allocation tracking."""
        self._allocation_count = 0
        self._total_allocated = 0
        self._peak_allocated = 0


class MemoryMonitor:
    """Monitors memory usage."""
    
    def __init__(self, config: Optional[MemorySecurityConfig] = None):
        self.config = config or MemorySecurityConfig()
    
    def get_current_usage(self) -> int:
        """Get current memory usage in bytes."""
        # Use gc to get more accurate memory info
        gc.collect()
        
        # Get tracked objects size
        total = 0
        for obj in gc.get_objects():
            try:
                total += sys.getsizeof(obj)
            except (TypeError, RuntimeError):
                pass
        
        return total
    
    def get_process_memory(self) -> int:
        """Get process memory usage (if available)."""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss * 1024  # Convert to bytes
        except (ImportError, AttributeError):
            return 0
    
    def check_usage(self) -> MemoryReport:
        """Check memory usage and return report."""
        current = self.get_process_memory()
        current_mb = current / (1024 * 1024)
        
        warnings = []
        threats = []
        
        if current_mb > self.config.critical_threshold_mb:
            status = MemoryCheckResult.CRITICAL
            threats.append(MemoryThreatType.MEMORY_EXHAUSTION)
            warnings.append(f"Memory usage critical: {current_mb:.1f}MB")
        elif current_mb > self.config.warn_threshold_mb:
            status = MemoryCheckResult.WARNING
            warnings.append(f"Memory usage high: {current_mb:.1f}MB")
        else:
            status = MemoryCheckResult.OK
        
        return MemoryReport(
            status=status,
            current_usage_bytes=current,
            peak_usage_bytes=current,  # Simplified
            allocation_count=0,
            warnings=warnings,
            threats_detected=threats,
        )


class BoundedBuffer:
    """A bounded buffer that prevents overflow."""
    
    def __init__(
        self,
        max_size: int = 1048576,  # 1MB default
        on_overflow: Optional[Callable] = None,
    ):
        self.max_size = max_size
        self.on_overflow = on_overflow
        self._buffer = bytearray()
    
    def write(self, data: bytes) -> int:
        """Write data to buffer. Returns bytes written."""
        available = self.max_size - len(self._buffer)
        
        if available <= 0:
            if self.on_overflow:
                self.on_overflow()
            return 0
        
        to_write = min(len(data), available)
        self._buffer.extend(data[:to_write])
        
        return to_write
    
    def read(self, size: int = -1) -> bytes:
        """Read data from buffer."""
        if size < 0:
            data = bytes(self._buffer)
            self._buffer.clear()
            return data
        
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data
    
    def size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)
    
    def available(self) -> int:
        """Get available space."""
        return self.max_size - len(self._buffer)
    
    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()


class MemorySecurityService:
    """Comprehensive memory security service."""
    
    _instance: Optional["MemorySecurityService"] = None
    
    def __init__(self, config: Optional[MemorySecurityConfig] = None):
        self.config = config or MemorySecurityConfig()
        self.buffer_limiter = BufferLimiter(self.config)
        self.resource_tracker = ResourceTracker(self.config)
        self.allocation_tracker = AllocationTracker(self.config)
        self.monitor = MemoryMonitor(self.config)
    
    @classmethod
    def get_instance(cls) -> "MemorySecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: MemorySecurityConfig) -> "MemorySecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def check_buffer(self, size: int) -> tuple[bool, Optional[str]]:
        """Check buffer size."""
        return self.buffer_limiter.check_buffer_size(size)
    
    def check_string(self, s: str) -> tuple[bool, Optional[str]]:
        """Check string length."""
        return self.buffer_limiter.check_string_length(s)
    
    def check_collection(self, collection: Any) -> tuple[bool, Optional[str]]:
        """Check collection size."""
        if isinstance(collection, list):
            return self.buffer_limiter.check_list_length(collection)
        elif isinstance(collection, dict):
            return self.buffer_limiter.check_dict_size(collection)
        return True, None
    
    def track_resource(self, resource: Any) -> int:
        """Track a resource."""
        return self.resource_tracker.track(resource)
    
    def untrack_resource(self, resource_id: int) -> bool:
        """Untrack a resource."""
        return self.resource_tracker.untrack(resource_id)
    
    def get_memory_report(self) -> MemoryReport:
        """Get memory usage report."""
        return self.monitor.check_usage()
    
    def create_bounded_buffer(
        self,
        max_size: Optional[int] = None,
    ) -> BoundedBuffer:
        """Create a bounded buffer."""
        size = max_size or self.config.max_buffer_size
        return BoundedBuffer(max_size=size)
    
    @contextmanager
    def track_scope(self):
        """Context manager for tracking resources in a scope."""
        initial_count = self.resource_tracker.get_open_count()
        try:
            yield
        finally:
            final_count = self.resource_tracker.get_open_count()
            if final_count > initial_count:
                leaked = final_count - initial_count
                print(f"Warning: {leaked} resources may have leaked")


# Convenience functions
def get_memory_service() -> MemorySecurityService:
    """Get memory service instance."""
    return MemorySecurityService.get_instance()


def check_buffer_size(size: int) -> tuple[bool, Optional[str]]:
    """Check buffer size."""
    return get_memory_service().check_buffer(size)


def check_string_length(s: str) -> tuple[bool, Optional[str]]:
    """Check string length."""
    return get_memory_service().check_string(s)


def create_bounded_buffer(max_size: int = 1048576) -> BoundedBuffer:
    """Create a bounded buffer."""
    return BoundedBuffer(max_size=max_size)
