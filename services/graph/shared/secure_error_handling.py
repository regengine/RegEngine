"""
SEC-031: Secure Error Handling.

Provides secure error handling that prevents information disclosure:
- Error classification and sanitization
- Safe error messages for clients
- Detailed logging for debugging
- Error code mapping
- Stack trace protection
"""

import logging
import traceback
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class ErrorSeverity(str, Enum):
    """Error severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    CONFLICT = "conflict"
    INTERNAL = "internal"
    SERVICE_UNAVAILABLE = "service_unavailable"
    BAD_REQUEST = "bad_request"
    EXTERNAL_SERVICE = "external_service"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ErrorContext:
    """Context information for an error."""
    error_id: str
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    message: str  # Safe message for client
    internal_message: str  # Detailed message for logs
    details: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    
    def to_client_response(self) -> Dict[str, Any]:
        """Get safe response for client."""
        return {
            "error": {
                "code": self.error_id,
                "category": self.category.value,
                "message": self.message,
                "timestamp": self.timestamp.isoformat(),
            }
        }
    
    def to_log_entry(self) -> Dict[str, Any]:
        """Get detailed entry for logging."""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.internal_message,
            "details": self.details,
            "stack_trace": self.stack_trace,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
        }


@dataclass
class ErrorMapping:
    """Maps internal errors to safe client messages."""
    category: ErrorCategory
    http_status: int
    client_message: str
    severity: ErrorSeverity = ErrorSeverity.ERROR


# =============================================================================
# Error Messages
# =============================================================================

# Safe messages that don't leak internal details
SAFE_MESSAGES = {
    ErrorCategory.VALIDATION: "The request contains invalid data",
    ErrorCategory.AUTHENTICATION: "Authentication required",
    ErrorCategory.AUTHORIZATION: "You don't have permission to access this resource",
    ErrorCategory.NOT_FOUND: "The requested resource was not found",
    ErrorCategory.RATE_LIMIT: "Too many requests. Please try again later",
    ErrorCategory.CONFLICT: "The request conflicts with current state",
    ErrorCategory.INTERNAL: "An internal error occurred. Please try again later",
    ErrorCategory.SERVICE_UNAVAILABLE: "Service temporarily unavailable",
    ErrorCategory.BAD_REQUEST: "Invalid request",
    ErrorCategory.EXTERNAL_SERVICE: "External service error. Please try again later",
}

# HTTP status codes for categories
HTTP_STATUS_CODES = {
    ErrorCategory.VALIDATION: 400,
    ErrorCategory.AUTHENTICATION: 401,
    ErrorCategory.AUTHORIZATION: 403,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.RATE_LIMIT: 429,
    ErrorCategory.CONFLICT: 409,
    ErrorCategory.INTERNAL: 500,
    ErrorCategory.SERVICE_UNAVAILABLE: 503,
    ErrorCategory.BAD_REQUEST: 400,
    ErrorCategory.EXTERNAL_SERVICE: 502,
}


# =============================================================================
# Secure Error Handler
# =============================================================================

class SecureErrorHandler:
    """
    Handles errors securely without leaking information.
    
    Features:
    - Generates unique error IDs for tracking
    - Sanitizes error messages for clients
    - Logs detailed information for debugging
    - Prevents stack trace exposure
    """
    
    def __init__(
        self,
        include_error_id: bool = True,
        log_stack_traces: bool = True,
        custom_messages: Optional[Dict[ErrorCategory, str]] = None,
        enable_logging: bool = True,
    ):
        """Initialize handler."""
        self.include_error_id = include_error_id
        self.log_stack_traces = log_stack_traces
        self.messages = {**SAFE_MESSAGES, **(custom_messages or {})}
        self.enable_logging = enable_logging
        self._error_handlers: Dict[type, Callable] = {}
    
    def _generate_error_id(self) -> str:
        """Generate unique error ID."""
        return f"ERR-{secrets.token_hex(8).upper()}"
    
    def register_handler(
        self,
        exception_type: type,
        handler: Callable[[Exception], ErrorContext],
    ) -> None:
        """Register custom handler for exception type."""
        self._error_handlers[exception_type] = handler
    
    def handle(
        self,
        exception: Exception,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorContext:
        """
        Handle an exception securely.
        
        Args:
            exception: The exception to handle
            request_id: Request identifier
            user_id: User identifier
            endpoint: API endpoint
            context: Additional context
            
        Returns:
            ErrorContext with safe client message
        """
        error_id = self._generate_error_id()
        timestamp = datetime.now(timezone.utc)
        
        # Check for custom handler
        for exc_type, handler in self._error_handlers.items():
            if isinstance(exception, exc_type):
                error_context = handler(exception)
                error_context.error_id = error_id
                error_context.timestamp = timestamp
                error_context.request_id = request_id
                error_context.user_id = user_id
                error_context.endpoint = endpoint
                return error_context
        
        # Classify the error
        category = self._classify_error(exception)
        severity = self._get_severity(category)
        
        # Get safe message
        safe_message = self.messages.get(category, SAFE_MESSAGES[ErrorCategory.INTERNAL])
        
        # Get internal message (for logging only)
        internal_message = str(exception) if str(exception) else type(exception).__name__
        
        # Capture stack trace for logging
        stack_trace = None
        if self.log_stack_traces:
            stack_trace = traceback.format_exc()
        
        error_context = ErrorContext(
            error_id=error_id,
            timestamp=timestamp,
            category=category,
            severity=severity,
            message=safe_message,
            internal_message=internal_message,
            details=context or {},
            stack_trace=stack_trace,
            request_id=request_id,
            user_id=user_id,
            endpoint=endpoint,
        )
        
        # Log the error
        if self.enable_logging:
            self._log_error(error_context)
        
        return error_context
    
    def _classify_error(self, exception: Exception) -> ErrorCategory:
        """Classify exception into category."""
        exc_type = type(exception).__name__.lower()
        exc_str = str(exception).lower()
        
        # Check exception type names
        if "validation" in exc_type or "invalid" in exc_type:
            return ErrorCategory.VALIDATION
        if "auth" in exc_type or "credentials" in exc_type:
            return ErrorCategory.AUTHENTICATION
        if "permission" in exc_type or "forbidden" in exc_type or "authorization" in exc_type:
            return ErrorCategory.AUTHORIZATION
        if "notfound" in exc_type or "not found" in exc_str:
            return ErrorCategory.NOT_FOUND
        if "ratelimit" in exc_type or "rate limit" in exc_str:
            return ErrorCategory.RATE_LIMIT
        if "conflict" in exc_type:
            return ErrorCategory.CONFLICT
        if "timeout" in exc_type or "connection" in exc_type:
            return ErrorCategory.EXTERNAL_SERVICE
        
        # Check common Python exceptions
        if isinstance(exception, ValueError):
            return ErrorCategory.VALIDATION
        if isinstance(exception, PermissionError):
            return ErrorCategory.AUTHORIZATION
        if isinstance(exception, FileNotFoundError):
            return ErrorCategory.NOT_FOUND
        if isinstance(exception, KeyError):
            return ErrorCategory.NOT_FOUND
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return ErrorCategory.EXTERNAL_SERVICE
        
        return ErrorCategory.INTERNAL
    
    def _get_severity(self, category: ErrorCategory) -> ErrorSeverity:
        """Get severity for category."""
        severity_map = {
            ErrorCategory.VALIDATION: ErrorSeverity.WARNING,
            ErrorCategory.AUTHENTICATION: ErrorSeverity.WARNING,
            ErrorCategory.AUTHORIZATION: ErrorSeverity.WARNING,
            ErrorCategory.NOT_FOUND: ErrorSeverity.INFO,
            ErrorCategory.RATE_LIMIT: ErrorSeverity.WARNING,
            ErrorCategory.CONFLICT: ErrorSeverity.WARNING,
            ErrorCategory.INTERNAL: ErrorSeverity.ERROR,
            ErrorCategory.SERVICE_UNAVAILABLE: ErrorSeverity.ERROR,
            ErrorCategory.BAD_REQUEST: ErrorSeverity.WARNING,
            ErrorCategory.EXTERNAL_SERVICE: ErrorSeverity.ERROR,
        }
        return severity_map.get(category, ErrorSeverity.ERROR)
    
    def _log_error(self, error_context: ErrorContext) -> None:
        """Log error with appropriate level."""
        log_entry = error_context.to_log_entry()
        
        log_func = {
            ErrorSeverity.DEBUG: logger.debug,
            ErrorSeverity.INFO: logger.info,
            ErrorSeverity.WARNING: logger.warning,
            ErrorSeverity.ERROR: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }.get(error_context.severity, logger.error)
        
        log_func(f"Error {error_context.error_id}: {error_context.internal_message}", extra=log_entry)
    
    def get_http_status(self, category: ErrorCategory) -> int:
        """Get HTTP status code for category."""
        return HTTP_STATUS_CODES.get(category, 500)


# =============================================================================
# Error Response Builder
# =============================================================================

class ErrorResponseBuilder:
    """
    Builds consistent error responses.
    """
    
    def __init__(
        self,
        include_timestamp: bool = True,
        include_error_id: bool = True,
        include_details: bool = False,  # Careful - may leak info
    ):
        """Initialize builder."""
        self.include_timestamp = include_timestamp
        self.include_error_id = include_error_id
        self.include_details = include_details
    
    def build(
        self,
        error_context: ErrorContext,
        include_validation_errors: bool = False,
    ) -> Dict[str, Any]:
        """
        Build error response.
        
        Args:
            error_context: Error context
            include_validation_errors: Include field-level validation errors
            
        Returns:
            Response dictionary
        """
        response = {
            "error": {
                "category": error_context.category.value,
                "message": error_context.message,
            }
        }
        
        if self.include_error_id:
            response["error"]["code"] = error_context.error_id
        
        if self.include_timestamp:
            response["error"]["timestamp"] = error_context.timestamp.isoformat()
        
        if include_validation_errors and error_context.category == ErrorCategory.VALIDATION:
            if "validation_errors" in error_context.details:
                response["error"]["details"] = error_context.details["validation_errors"]
        
        return response
    
    def build_validation_error(
        self,
        field_errors: Dict[str, List[str]],
        error_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build validation error response."""
        return {
            "error": {
                "code": error_id or "VALIDATION_ERROR",
                "category": ErrorCategory.VALIDATION.value,
                "message": "Validation failed",
                "details": {
                    "fields": field_errors,
                },
            }
        }


# =============================================================================
# Exception Classes
# =============================================================================

class SecureException(Exception):
    """Base exception that supports secure handling."""
    
    category: ErrorCategory = ErrorCategory.INTERNAL
    http_status: int = 500
    safe_message: str = "An error occurred"
    
    def __init__(
        self,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize exception."""
        super().__init__(message)
        self.details = details or {}


class ValidationException(SecureException):
    """Validation error."""
    category = ErrorCategory.VALIDATION
    http_status = 400
    safe_message = "Validation failed"


class AuthenticationException(SecureException):
    """Authentication error."""
    category = ErrorCategory.AUTHENTICATION
    http_status = 401
    safe_message = "Authentication required"


class AuthorizationException(SecureException):
    """Authorization error."""
    category = ErrorCategory.AUTHORIZATION
    http_status = 403
    safe_message = "Access denied"


class NotFoundException(SecureException):
    """Resource not found."""
    category = ErrorCategory.NOT_FOUND
    http_status = 404
    safe_message = "Resource not found"


class RateLimitException(SecureException):
    """Rate limit exceeded."""
    category = ErrorCategory.RATE_LIMIT
    http_status = 429
    safe_message = "Rate limit exceeded"


class ConflictException(SecureException):
    """Resource conflict."""
    category = ErrorCategory.CONFLICT
    http_status = 409
    safe_message = "Resource conflict"


# =============================================================================
# Error Service
# =============================================================================

class ErrorService:
    """
    High-level error handling service.
    """
    
    _instance: Optional["ErrorService"] = None
    
    def __init__(self):
        """Initialize service."""
        self.handler = SecureErrorHandler()
        self.response_builder = ErrorResponseBuilder()
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up handlers for SecureException subclasses."""
        def handle_secure_exception(exc: SecureException) -> ErrorContext:
            return ErrorContext(
                error_id="",
                timestamp=datetime.now(timezone.utc),
                category=exc.category,
                severity=ErrorSeverity.WARNING,
                message=exc.safe_message,
                internal_message=str(exc),
                details=exc.details,
            )
        
        for exc_class in [
            ValidationException,
            AuthenticationException,
            AuthorizationException,
            NotFoundException,
            RateLimitException,
            ConflictException,
        ]:
            self.handler.register_handler(exc_class, handle_secure_exception)
    
    @classmethod
    def get_instance(cls) -> "ErrorService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def handle_error(
        self,
        exception: Exception,
        **kwargs,
    ) -> tuple[Dict[str, Any], int]:
        """
        Handle error and return response.
        
        Returns:
            Tuple of (response_dict, http_status)
        """
        context = self.handler.handle(exception, **kwargs)
        response = self.response_builder.build(context)
        status = self.handler.get_http_status(context.category)
        return response, status


# =============================================================================
# Convenience Functions
# =============================================================================

def get_error_service() -> ErrorService:
    """Get the global error service."""
    return ErrorService.get_instance()


def handle_error(exception: Exception, **kwargs) -> tuple[Dict[str, Any], int]:
    """Handle an error and return response."""
    return get_error_service().handle_error(exception, **kwargs)


def safe_error_message(exception: Exception) -> str:
    """Get safe error message for exception."""
    handler = SecureErrorHandler()
    category = handler._classify_error(exception)
    return SAFE_MESSAGES.get(category, SAFE_MESSAGES[ErrorCategory.INTERNAL])
