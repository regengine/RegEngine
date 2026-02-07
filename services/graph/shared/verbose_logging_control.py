"""
SEC-035: Verbose Logging Control.

Provides secure logging controls:
- Log level management
- Sensitive data filtering in logs
- Logging suppression for sensitive operations
- Audit log protection
"""

import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Pattern, Set, TypeVar, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SensitivityLevel(str, Enum):
    """Data sensitivity levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"


class LogDestination(str, Enum):
    """Log destinations."""
    CONSOLE = "console"
    FILE = "file"
    SYSLOG = "syslog"
    CLOUD = "cloud"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: LogLevel = LogLevel.INFO
    environment: str = "production"
    allowed_levels: Dict[str, LogLevel] = field(default_factory=lambda: {
        "local": LogLevel.DEBUG,
        "development": LogLevel.DEBUG,
        "testing": LogLevel.INFO,
        "staging": LogLevel.INFO,
        "production": LogLevel.WARNING,
    })
    sensitive_fields: Set[str] = field(default_factory=lambda: {
        "password", "secret", "token", "api_key", "apikey",
        "authorization", "auth", "credential", "private_key",
        "ssn", "social_security", "credit_card", "card_number",
        "cvv", "pin", "bank_account", "routing_number",
    })
    redaction_placeholder: str = "[REDACTED]"
    log_request_body: bool = False
    log_response_body: bool = False
    max_log_length: int = 1000
    
    def get_allowed_level(self) -> LogLevel:
        """Get allowed level for current environment."""
        return self.allowed_levels.get(self.environment, LogLevel.WARNING)


@dataclass
class FilteredLogRecord:
    """A log record with sensitive data filtered."""
    level: str
    message: str
    timestamp: str
    logger_name: str
    filtered_fields: List[str] = field(default_factory=list)
    original_length: int = 0
    truncated: bool = False


@dataclass
class LoggingContext:
    """Context for logging operations."""
    operation: str
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC
    suppress_details: bool = False
    correlation_id: Optional[str] = None


# =============================================================================
# Log Filter
# =============================================================================

class SensitiveDataLogFilter(logging.Filter):
    """
    Logging filter that removes sensitive data.
    
    Features:
    - Pattern-based filtering
    - Field name filtering
    - Contextual filtering
    """
    
    # Patterns for sensitive data
    SENSITIVE_PATTERNS: List[tuple[str, Pattern]] = [
        ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
        ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
        ("credit_card", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")),
        ("phone", re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")),
        ("ip_address", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
        ("api_key", re.compile(r"(?:api[_-]?key|apikey)[=:\s]+['\"]?[\w-]{20,}['\"]?", re.I)),
        ("bearer_token", re.compile(r"Bearer\s+[\w-]+\.[\w-]+\.[\w-]+", re.I)),
        ("password", re.compile(r"(?:password|passwd|pwd)[=:\s]+['\"]?[^\s'\"]{3,}['\"]?", re.I)),
        ("secret", re.compile(r"(?:secret|private)[=:\s]+['\"]?[^\s'\"]{3,}['\"]?", re.I)),
    ]
    
    def __init__(
        self,
        config: Optional[LoggingConfig] = None,
        enabled: bool = True,
    ):
        """Initialize filter."""
        super().__init__()
        self.config = config or LoggingConfig()
        self.enabled = enabled
        self._filtered_count = 0
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record, redacting sensitive data."""
        if not self.enabled:
            return True
        
        # Filter the message
        if hasattr(record, "msg") and record.msg:
            record.msg = self._filter_message(str(record.msg))
        
        # Filter args if present
        if record.args:
            record.args = self._filter_args(record.args)
        
        return True
    
    def _filter_message(self, message: str) -> str:
        """Filter sensitive data from message."""
        filtered = message
        
        for name, pattern in self.SENSITIVE_PATTERNS:
            if pattern.search(filtered):
                filtered = pattern.sub(self.config.redaction_placeholder, filtered)
                self._filtered_count += 1
        
        # Filter key=value patterns for sensitive fields
        for field_name in self.config.sensitive_fields:
            pattern = re.compile(
                rf"{field_name}[=:\s]+['\"]?[^\s'\"]+['\"]?",
                re.IGNORECASE,
            )
            filtered = pattern.sub(
                f"{field_name}={self.config.redaction_placeholder}",
                filtered,
            )
        
        # Truncate if too long
        if len(filtered) > self.config.max_log_length:
            filtered = filtered[: self.config.max_log_length] + "...[TRUNCATED]"
        
        return filtered
    
    def _filter_args(self, args: Any) -> Any:
        """Filter sensitive data from args."""
        if isinstance(args, dict):
            return {
                k: self.config.redaction_placeholder
                if k.lower() in self.config.sensitive_fields
                else self._filter_args(v)
                for k, v in args.items()
            }
        elif isinstance(args, (list, tuple)):
            filtered_list = [self._filter_args(a) for a in args]
            return type(args)(filtered_list)
        elif isinstance(args, str):
            return self._filter_message(args)
        return args
    
    def get_filtered_count(self) -> int:
        """Get count of filtered items."""
        return self._filtered_count


# =============================================================================
# Log Level Controller
# =============================================================================

class LogLevelController:
    """
    Controls log levels based on environment and context.
    
    Features:
    - Environment-based level management
    - Runtime level adjustment
    - Level enforcement
    """
    
    LEVEL_HIERARCHY = {
        LogLevel.DEBUG: 10,
        LogLevel.INFO: 20,
        LogLevel.WARNING: 30,
        LogLevel.ERROR: 40,
        LogLevel.CRITICAL: 50,
    }
    
    def __init__(self, config: Optional[LoggingConfig] = None):
        """Initialize controller."""
        self.config = config or LoggingConfig()
        self._original_levels: Dict[str, int] = {}
    
    def get_effective_level(self) -> LogLevel:
        """Get effective log level for current environment."""
        allowed = self.config.get_allowed_level()
        
        # In production, never go below WARNING
        if self.config.environment == "production":
            if self.LEVEL_HIERARCHY.get(self.config.level, 0) < 30:
                return LogLevel.WARNING
        
        return max(
            self.config.level,
            allowed,
            key=lambda x: self.LEVEL_HIERARCHY.get(x, 0),
        )
    
    def apply_level(self, logger_name: Optional[str] = None) -> None:
        """Apply effective level to logger."""
        level = self.get_effective_level()
        numeric_level = getattr(logging, level.value, logging.INFO)
        
        if logger_name:
            target_logger = logging.getLogger(logger_name)
        else:
            target_logger = logging.getLogger()
        
        # Store original level
        self._original_levels[logger_name or "root"] = target_logger.level
        target_logger.setLevel(numeric_level)
    
    def restore_level(self, logger_name: Optional[str] = None) -> None:
        """Restore original level."""
        key = logger_name or "root"
        if key in self._original_levels:
            if logger_name:
                target_logger = logging.getLogger(logger_name)
            else:
                target_logger = logging.getLogger()
            target_logger.setLevel(self._original_levels[key])
    
    def is_level_allowed(self, level: LogLevel) -> bool:
        """Check if a log level is allowed."""
        effective = self.get_effective_level()
        return (
            self.LEVEL_HIERARCHY.get(level, 0)
            >= self.LEVEL_HIERARCHY.get(effective, 0)
        )
    
    def enforce_minimum_level(self, level: LogLevel) -> None:
        """Enforce minimum log level."""
        min_level = self.LEVEL_HIERARCHY.get(level, 0)
        
        # Apply to all handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if handler.level < min_level:
                handler.setLevel(min_level)


# =============================================================================
# Logging Suppressor
# =============================================================================

class LoggingSuppressor:
    """
    Suppresses logging during sensitive operations.
    
    Features:
    - Context-based suppression
    - Temporary suppression
    - Selective suppression
    """
    
    def __init__(self, config: Optional[LoggingConfig] = None):
        """Initialize suppressor."""
        self.config = config or LoggingConfig()
        self._suppressed_loggers: Dict[str, int] = {}
        self._active_suppressions: Set[str] = set()
    
    def suppress(
        self,
        logger_names: Optional[List[str]] = None,
        context: Optional[LoggingContext] = None,
    ) -> "SuppressionContext":
        """
        Create suppression context.
        
        Args:
            logger_names: Specific loggers to suppress
            context: Logging context
            
        Returns:
            Context manager for suppression
        """
        return SuppressionContext(self, logger_names, context)
    
    def _start_suppression(
        self,
        logger_names: Optional[List[str]] = None,
    ) -> str:
        """Start suppressing loggers."""
        import uuid
        suppression_id = str(uuid.uuid4())
        
        if logger_names:
            loggers = [logging.getLogger(name) for name in logger_names]
        else:
            loggers = [logging.getLogger()]
        
        for lg in loggers:
            key = lg.name or "root"
            if key not in self._suppressed_loggers:
                self._suppressed_loggers[key] = lg.level
            lg.setLevel(logging.CRITICAL + 10)  # Suppress all
        
        self._active_suppressions.add(suppression_id)
        return suppression_id
    
    def _end_suppression(self, suppression_id: str) -> None:
        """End suppression."""
        if suppression_id not in self._active_suppressions:
            return
        
        self._active_suppressions.remove(suppression_id)
        
        # Only restore if no other suppressions active
        if not self._active_suppressions:
            for key, level in self._suppressed_loggers.items():
                if key == "root":
                    lg = logging.getLogger()
                else:
                    lg = logging.getLogger(key)
                lg.setLevel(level)
            self._suppressed_loggers.clear()
    
    def is_suppressed(self, logger_name: Optional[str] = None) -> bool:
        """Check if logging is suppressed."""
        key = logger_name or "root"
        return key in self._suppressed_loggers


class SuppressionContext:
    """Context manager for log suppression."""
    
    def __init__(
        self,
        suppressor: LoggingSuppressor,
        logger_names: Optional[List[str]],
        context: Optional[LoggingContext],
    ):
        """Initialize context."""
        self.suppressor = suppressor
        self.logger_names = logger_names
        self.context = context
        self._suppression_id: Optional[str] = None
    
    def __enter__(self) -> "SuppressionContext":
        """Enter suppression context."""
        self._suppression_id = self.suppressor._start_suppression(
            self.logger_names
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit suppression context."""
        if self._suppression_id:
            self.suppressor._end_suppression(self._suppression_id)


# =============================================================================
# Secure Logger
# =============================================================================

class SecureLogger:
    """
    Secure logging wrapper.
    
    Features:
    - Automatic sensitive data filtering
    - Context-aware logging
    - Level enforcement
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[LoggingConfig] = None,
    ):
        """Initialize secure logger."""
        self.name = name
        self.config = config or LoggingConfig()
        self._logger = logging.getLogger(name)
        self._filter = SensitiveDataLogFilter(config)
        self._context: Optional[LoggingContext] = None
        
        # Add filter
        self._logger.addFilter(self._filter)
    
    def set_context(self, context: LoggingContext) -> None:
        """Set logging context."""
        self._context = context
    
    def clear_context(self) -> None:
        """Clear logging context."""
        self._context = None
    
    def _should_log(self, level: LogLevel) -> bool:
        """Check if should log at level."""
        if self._context and self._context.suppress_details:
            return level in (LogLevel.ERROR, LogLevel.CRITICAL)
        return True
    
    def _format_message(self, message: str) -> str:
        """Format message with context."""
        if self._context and self._context.correlation_id:
            return f"[{self._context.correlation_id}] {message}"
        return message
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log debug message."""
        if self._should_log(LogLevel.DEBUG):
            self._logger.debug(self._format_message(message), *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Log info message."""
        if self._should_log(LogLevel.INFO):
            self._logger.info(self._format_message(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log warning message."""
        if self._should_log(LogLevel.WARNING):
            self._logger.warning(self._format_message(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Log error message."""
        self._logger.error(self._format_message(message), *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs) -> None:
        """Log critical message."""
        self._logger.critical(self._format_message(message), *args, **kwargs)
    
    def log_sensitive(
        self,
        level: LogLevel,
        message: str,
        sensitivity: SensitivityLevel,
        *args,
        **kwargs,
    ) -> None:
        """
        Log with sensitivity awareness.
        
        In production, logs above INTERNAL are suppressed.
        """
        if self.config.environment == "production":
            if sensitivity in (
                SensitivityLevel.CONFIDENTIAL,
                SensitivityLevel.RESTRICTED,
                SensitivityLevel.SECRET,
            ):
                return  # Don't log sensitive data in production
        
        log_method = getattr(self._logger, level.value.lower())
        log_method(self._format_message(message), *args, **kwargs)


# =============================================================================
# Verbose Logging Control Service
# =============================================================================

class VerboseLoggingService:
    """
    High-level service for verbose logging control.
    """
    
    _instance: Optional["VerboseLoggingService"] = None
    
    def __init__(self, config: Optional[LoggingConfig] = None):
        """Initialize service."""
        self.config = config or LoggingConfig()
        self.filter = SensitiveDataLogFilter(self.config)
        self.level_controller = LogLevelController(self.config)
        self.suppressor = LoggingSuppressor(self.config)
        self._loggers: Dict[str, SecureLogger] = {}
    
    @classmethod
    def get_instance(cls) -> "VerboseLoggingService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: LoggingConfig) -> "VerboseLoggingService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def get_logger(self, name: str) -> SecureLogger:
        """Get a secure logger."""
        if name not in self._loggers:
            self._loggers[name] = SecureLogger(name, self.config)
        return self._loggers[name]
    
    def apply_production_settings(self) -> None:
        """Apply production-safe logging settings."""
        # Set minimum level to WARNING
        self.level_controller.enforce_minimum_level(LogLevel.WARNING)
        
        # Apply filter to root logger
        root = logging.getLogger()
        root.addFilter(self.filter)
    
    def suppress_for_operation(
        self,
        operation: str,
        logger_names: Optional[List[str]] = None,
    ) -> SuppressionContext:
        """Suppress logging for an operation."""
        context = LoggingContext(operation=operation, suppress_details=True)
        return self.suppressor.suppress(logger_names, context)
    
    def filter_message(self, message: str) -> str:
        """Filter sensitive data from a message."""
        return self.filter._filter_message(message)
    
    def is_verbose_allowed(self) -> bool:
        """Check if verbose logging is allowed."""
        return self.config.environment in ("local", "development", "testing")


# =============================================================================
# Decorators
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def suppress_logging(
    logger_names: Optional[List[str]] = None,
) -> Callable[[F], F]:
    """Decorator to suppress logging during function execution."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            service = VerboseLoggingService.get_instance()
            with service.suppress_for_operation(func.__name__, logger_names):
                return func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


def log_with_filter(
    level: LogLevel = LogLevel.INFO,
) -> Callable[[F], F]:
    """Decorator to log function calls with filtering."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            service = VerboseLoggingService.get_instance()
            log = service.get_logger(func.__module__)
            
            # Log entry (filtered)
            filtered_args = service.filter_message(str(args))
            log.info(f"Calling {func.__name__} with args: {filtered_args}")
            
            try:
                result = func(*args, **kwargs)
                log.info(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                log.error(f"{func.__name__} failed: {type(e).__name__}")
                raise
        return wrapper  # type: ignore
    return decorator


# =============================================================================
# Convenience Functions
# =============================================================================

def get_logging_service() -> VerboseLoggingService:
    """Get the global logging service."""
    return VerboseLoggingService.get_instance()


def get_secure_logger(name: str) -> SecureLogger:
    """Get a secure logger."""
    return get_logging_service().get_logger(name)


def filter_sensitive_data(message: str) -> str:
    """Filter sensitive data from a message."""
    return get_logging_service().filter_message(message)


def is_verbose_allowed() -> bool:
    """Check if verbose logging is allowed."""
    return get_logging_service().is_verbose_allowed()
