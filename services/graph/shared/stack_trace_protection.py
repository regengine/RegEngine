"""
SEC-033: Stack Trace Protection.

Provides stack trace protection to prevent information disclosure:
- Stack trace filtering
- Frame sanitization
- Production vs development modes
- Safe exception representation
"""

import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from types import TracebackType

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class EnvironmentMode(str, Enum):
    """Environment modes."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class FrameVisibility(str, Enum):
    """Frame visibility in stack trace."""
    VISIBLE = "visible"
    HIDDEN = "hidden"
    SUMMARIZED = "summarized"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FrameInfo:
    """Information about a stack frame."""
    filename: str
    lineno: int
    name: str
    line: Optional[str] = None
    locals: Dict[str, Any] = field(default_factory=dict)
    visibility: FrameVisibility = FrameVisibility.VISIBLE
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "filename": self.filename,
            "lineno": self.lineno,
            "name": self.name,
            "line": self.line,
        }
    
    def to_safe_string(self) -> str:
        """Get safe string representation."""
        if self.visibility == FrameVisibility.HIDDEN:
            return ""
        if self.visibility == FrameVisibility.SUMMARIZED:
            return f"  ... in {self.name}"
        return f'  File "{self.filename}", line {self.lineno}, in {self.name}'


@dataclass
class ProtectedStackTrace:
    """Protected stack trace representation."""
    exception_type: str
    exception_message: str
    frames: List[FrameInfo] = field(default_factory=list)
    cause: Optional["ProtectedStackTrace"] = None
    context: Optional["ProtectedStackTrace"] = None
    
    def to_safe_string(self, max_frames: int = 10) -> str:
        """Get safe string representation."""
        lines = ["Traceback (most recent call last):"]
        
        visible_frames = [f for f in self.frames if f.visibility != FrameVisibility.HIDDEN]
        
        # Limit frames
        if len(visible_frames) > max_frames:
            lines.append(f"  ... {len(visible_frames) - max_frames} frames hidden ...")
            visible_frames = visible_frames[-max_frames:]
        
        for frame in visible_frames:
            frame_str = frame.to_safe_string()
            if frame_str:
                lines.append(frame_str)
                if frame.line and frame.visibility == FrameVisibility.VISIBLE:
                    lines.append(f"    {frame.line}")
        
        lines.append(f"{self.exception_type}: {self.exception_message}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "frames": [f.to_dict() for f in self.frames if f.visibility != FrameVisibility.HIDDEN],
        }


@dataclass
class StackTraceConfig:
    """Stack trace protection configuration."""
    mode: EnvironmentMode = EnvironmentMode.PRODUCTION
    max_frames: int = 10
    include_line_content: bool = False
    include_locals: bool = False
    hidden_paths: List[str] = field(default_factory=list)
    visible_paths: List[str] = field(default_factory=list)
    sanitize_messages: bool = True


# =============================================================================
# Stack Trace Protector
# =============================================================================

class StackTraceProtector:
    """
    Protects stack traces from exposing sensitive information.
    
    Features:
    - Frame filtering
    - Path-based visibility
    - Local variable removal
    - Message sanitization
    """
    
    def __init__(self, config: Optional[StackTraceConfig] = None):
        """Initialize protector."""
        self.config = config or StackTraceConfig()
        self._frame_filters: List[Callable[[FrameInfo], FrameVisibility]] = []
        self._setup_default_hidden_paths()
    
    def _setup_default_hidden_paths(self) -> None:
        """Set up default paths to hide."""
        # Standard library paths
        stdlib_path = os.path.dirname(os.__file__)
        self.config.hidden_paths.extend([
            stdlib_path,
            "site-packages",
            "<frozen",
        ])
    
    def add_frame_filter(
        self,
        filter_func: Callable[[FrameInfo], FrameVisibility],
    ) -> None:
        """Add custom frame filter."""
        self._frame_filters.append(filter_func)
    
    def add_hidden_path(self, path: str) -> None:
        """Add path to hide from stack traces."""
        self.config.hidden_paths.append(path)
    
    def add_visible_path(self, path: str) -> None:
        """Add path to always show in stack traces."""
        self.config.visible_paths.append(path)
    
    def protect(
        self,
        exception: BaseException,
        tb: Optional[TracebackType] = None,
    ) -> ProtectedStackTrace:
        """
        Protect a stack trace.
        
        Args:
            exception: The exception
            tb: Optional traceback (uses exception's if not provided)
            
        Returns:
            ProtectedStackTrace
        """
        if tb is None:
            tb = exception.__traceback__
        
        # Extract frames
        frames = self._extract_frames(tb)
        
        # Apply visibility rules
        for frame in frames:
            frame.visibility = self._determine_visibility(frame)
        
        # Sanitize exception message if configured
        message = str(exception)
        if self.config.sanitize_messages:
            message = self._sanitize_message(message)
        
        protected = ProtectedStackTrace(
            exception_type=type(exception).__name__,
            exception_message=message,
            frames=frames,
        )
        
        # Handle exception chains
        if exception.__cause__:
            protected.cause = self.protect(exception.__cause__)
        if exception.__context__ and exception.__context__ is not exception.__cause__:
            protected.context = self.protect(exception.__context__)
        
        return protected
    
    def _extract_frames(self, tb: Optional[TracebackType]) -> List[FrameInfo]:
        """Extract frame information from traceback."""
        frames = []
        
        if tb is None:
            return frames
        
        for frame_info in traceback.extract_tb(tb):
            frame = FrameInfo(
                filename=frame_info.filename,
                lineno=frame_info.lineno,
                name=frame_info.name,
                line=frame_info.line if self.config.include_line_content else None,
            )
            frames.append(frame)
        
        return frames
    
    def _determine_visibility(self, frame: FrameInfo) -> FrameVisibility:
        """Determine frame visibility."""
        # Check custom filters first
        for filter_func in self._frame_filters:
            visibility = filter_func(frame)
            if visibility != FrameVisibility.VISIBLE:
                return visibility
        
        # Check explicit visible paths
        for path in self.config.visible_paths:
            if path in frame.filename:
                return FrameVisibility.VISIBLE
        
        # Check hidden paths
        for path in self.config.hidden_paths:
            if path in frame.filename:
                if self.config.mode == EnvironmentMode.PRODUCTION:
                    return FrameVisibility.HIDDEN
                return FrameVisibility.SUMMARIZED
        
        return FrameVisibility.VISIBLE
    
    def _sanitize_message(self, message: str) -> str:
        """Sanitize exception message."""
        # Import here to avoid circular dependency
        try:
            from shared.exception_sanitization import MessageSanitizer
            sanitizer = MessageSanitizer()
            return sanitizer.sanitize(message).sanitized_message
        except ImportError:
            return message
    
    def format_safe(
        self,
        exception: BaseException,
        tb: Optional[TracebackType] = None,
    ) -> str:
        """Format exception as safe string."""
        protected = self.protect(exception, tb)
        return protected.to_safe_string(self.config.max_frames)
    
    def format_for_logging(
        self,
        exception: BaseException,
        tb: Optional[TracebackType] = None,
    ) -> str:
        """
        Format exception for internal logging.
        
        Includes more details than client-facing format.
        """
        if self.config.mode == EnvironmentMode.DEVELOPMENT:
            # In development, show full traceback
            if tb:
                return "".join(traceback.format_exception(type(exception), exception, tb))
            return traceback.format_exc()
        
        # In production, use protected format
        return self.format_safe(exception, tb)


# =============================================================================
# Exception Formatter
# =============================================================================

class ExceptionFormatter:
    """
    Formats exceptions for different audiences.
    """
    
    def __init__(
        self,
        protector: Optional[StackTraceProtector] = None,
    ):
        """Initialize formatter."""
        self.protector = protector or StackTraceProtector()
    
    def format_for_client(
        self,
        exception: BaseException,
        include_type: bool = True,
    ) -> str:
        """
        Format exception for client response.
        
        Minimal information, no stack trace.
        """
        exc_type = type(exception).__name__ if include_type else ""
        
        # Use generic messages for internal errors
        if self._is_internal_error(exception):
            message = "An internal error occurred"
        else:
            message = self.protector._sanitize_message(str(exception))
        
        if exc_type:
            return f"{exc_type}: {message}"
        return message
    
    def format_for_log(
        self,
        exception: BaseException,
        include_trace: bool = True,
    ) -> str:
        """
        Format exception for logging.
        
        Includes protected stack trace.
        """
        parts = [f"{type(exception).__name__}: {exception}"]
        
        if include_trace:
            parts.append(self.protector.format_for_logging(exception))
        
        return "\n".join(parts)
    
    def format_for_debug(
        self,
        exception: BaseException,
    ) -> str:
        """
        Format exception for debugging.
        
        Includes full information (development only).
        """
        if self.protector.config.mode != EnvironmentMode.DEVELOPMENT:
            return self.format_for_log(exception)
        
        return traceback.format_exc()
    
    def _is_internal_error(self, exception: BaseException) -> bool:
        """Check if exception is an internal error."""
        internal_types = (
            RuntimeError,
            SystemError,
            MemoryError,
            RecursionError,
        )
        return isinstance(exception, internal_types)


# =============================================================================
# Production Exception Hook
# =============================================================================

class ProductionExceptionHook:
    """
    Exception hook for production environments.
    
    Replaces sys.excepthook to protect stack traces.
    """
    
    def __init__(
        self,
        protector: Optional[StackTraceProtector] = None,
        log_full_trace: bool = True,
    ):
        """Initialize hook."""
        self.protector = protector or StackTraceProtector()
        self.log_full_trace = log_full_trace
        self._original_hook = sys.excepthook
    
    def install(self) -> None:
        """Install the exception hook."""
        sys.excepthook = self._hook
    
    def uninstall(self) -> None:
        """Restore original exception hook."""
        sys.excepthook = self._original_hook
    
    def _hook(
        self,
        exc_type: type,
        exc_value: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        """Custom exception hook."""
        # Log full trace internally
        if self.log_full_trace:
            logger.error(
                "Unhandled exception",
                exc_info=(exc_type, exc_value, exc_tb),
            )
        
        # Print protected trace
        protected = self.protector.format_safe(exc_value, exc_tb)
        print(protected, file=sys.stderr)


# =============================================================================
# Stack Trace Service
# =============================================================================

class StackTraceService:
    """
    High-level stack trace protection service.
    """
    
    _instance: Optional["StackTraceService"] = None
    
    def __init__(self, mode: EnvironmentMode = EnvironmentMode.PRODUCTION):
        """Initialize service."""
        config = StackTraceConfig(mode=mode)
        self.protector = StackTraceProtector(config)
        self.formatter = ExceptionFormatter(self.protector)
        self.hook = ProductionExceptionHook(self.protector)
    
    @classmethod
    def get_instance(cls) -> "StackTraceService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, mode: EnvironmentMode) -> "StackTraceService":
        """Configure the service."""
        cls._instance = cls(mode)
        return cls._instance
    
    def protect(self, exception: BaseException) -> ProtectedStackTrace:
        """Protect a stack trace."""
        return self.protector.protect(exception)
    
    def format_safe(self, exception: BaseException) -> str:
        """Format exception safely."""
        return self.protector.format_safe(exception)
    
    def format_for_client(self, exception: BaseException) -> str:
        """Format exception for client."""
        return self.formatter.format_for_client(exception)
    
    def install_hook(self) -> None:
        """Install production exception hook."""
        self.hook.install()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_stack_trace_service() -> StackTraceService:
    """Get the global stack trace service."""
    return StackTraceService.get_instance()


def protect_stack_trace(exception: BaseException) -> ProtectedStackTrace:
    """Protect a stack trace."""
    return get_stack_trace_service().protect(exception)


def format_safe_exception(exception: BaseException) -> str:
    """Format exception safely."""
    return get_stack_trace_service().format_safe(exception)


def format_client_exception(exception: BaseException) -> str:
    """Format exception for client response."""
    return get_stack_trace_service().format_for_client(exception)
