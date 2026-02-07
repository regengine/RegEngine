"""
Tests for SEC-031: Secure Error Handling.

Tests cover:
- Error classification
- Safe message generation
- Error ID generation
- Stack trace protection
- HTTP status mapping
- Custom exception handling
"""

import pytest
from datetime import datetime, timezone

from shared.secure_error_handling import (
    # Enums
    ErrorSeverity,
    ErrorCategory,
    # Data classes
    ErrorContext,
    ErrorMapping,
    # Constants
    SAFE_MESSAGES,
    HTTP_STATUS_CODES,
    # Classes
    SecureErrorHandler,
    ErrorResponseBuilder,
    ErrorService,
    # Exceptions
    SecureException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    NotFoundException,
    RateLimitException,
    ConflictException,
    # Convenience functions
    get_error_service,
    handle_error,
    safe_error_message,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def handler():
    """Create secure error handler."""
    return SecureErrorHandler(enable_logging=False)


@pytest.fixture
def response_builder():
    """Create error response builder."""
    return ErrorResponseBuilder()


@pytest.fixture
def service():
    """Create error service."""
    svc = ErrorService()
    svc.handler.enable_logging = False
    return svc


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_error_severities(self):
        """Should have expected severities."""
        assert ErrorSeverity.DEBUG == "debug"
        assert ErrorSeverity.INFO == "info"
        assert ErrorSeverity.WARNING == "warning"
        assert ErrorSeverity.ERROR == "error"
        assert ErrorSeverity.CRITICAL == "critical"
    
    def test_error_categories(self):
        """Should have expected categories."""
        assert ErrorCategory.VALIDATION == "validation"
        assert ErrorCategory.AUTHENTICATION == "authentication"
        assert ErrorCategory.AUTHORIZATION == "authorization"
        assert ErrorCategory.INTERNAL == "internal"


# =============================================================================
# Test: ErrorContext
# =============================================================================

class TestErrorContext:
    """Test ErrorContext class."""
    
    def test_to_client_response(self):
        """Should generate safe client response."""
        context = ErrorContext(
            error_id="ERR-12345678",
            timestamp=datetime.now(timezone.utc),
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            message="Invalid input",
            internal_message="Field 'email' failed regex validation",
            stack_trace="Traceback...",
        )
        
        response = context.to_client_response()
        
        assert response["error"]["code"] == "ERR-12345678"
        assert response["error"]["message"] == "Invalid input"
        # Should NOT include internal message or stack trace
        assert "internal_message" not in str(response)
        assert "Traceback" not in str(response)
    
    def test_to_log_entry(self):
        """Should include full details for logging."""
        context = ErrorContext(
            error_id="ERR-12345678",
            timestamp=datetime.now(timezone.utc),
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.ERROR,
            message="An error occurred",
            internal_message="Database connection failed: timeout",
            stack_trace="Traceback...",
            request_id="req-123",
            user_id="user-456",
        )
        
        log_entry = context.to_log_entry()
        
        assert log_entry["error_id"] == "ERR-12345678"
        assert log_entry["message"] == "Database connection failed: timeout"
        assert log_entry["stack_trace"] == "Traceback..."
        assert log_entry["request_id"] == "req-123"


# =============================================================================
# Test: SecureErrorHandler
# =============================================================================

class TestSecureErrorHandler:
    """Test SecureErrorHandler."""
    
    def test_generates_error_id(self, handler):
        """Should generate unique error IDs."""
        context1 = handler.handle(ValueError("test"))
        context2 = handler.handle(ValueError("test"))
        
        assert context1.error_id.startswith("ERR-")
        assert context2.error_id.startswith("ERR-")
        assert context1.error_id != context2.error_id
    
    def test_classifies_validation_error(self, handler):
        """Should classify validation errors."""
        context = handler.handle(ValueError("invalid input"))
        
        assert context.category == ErrorCategory.VALIDATION
    
    def test_classifies_permission_error(self, handler):
        """Should classify permission errors."""
        context = handler.handle(PermissionError("access denied"))
        
        assert context.category == ErrorCategory.AUTHORIZATION
    
    def test_classifies_not_found(self, handler):
        """Should classify not found errors."""
        context = handler.handle(FileNotFoundError("file missing"))
        
        assert context.category == ErrorCategory.NOT_FOUND
    
    def test_classifies_connection_error(self, handler):
        """Should classify connection errors."""
        context = handler.handle(ConnectionError("connection failed"))
        
        assert context.category == ErrorCategory.EXTERNAL_SERVICE
    
    def test_classifies_unknown_as_internal(self, handler):
        """Should classify unknown errors as internal."""
        context = handler.handle(RuntimeError("something went wrong"))
        
        assert context.category == ErrorCategory.INTERNAL
    
    def test_safe_message_no_internal_details(self, handler):
        """Should not expose internal details in message."""
        context = handler.handle(
            Exception("Database password: secret123, host: internal.db.local")
        )
        
        # Safe message should NOT contain internal details
        assert "secret123" not in context.message
        assert "internal.db" not in context.message
        assert context.message == SAFE_MESSAGES[ErrorCategory.INTERNAL]
    
    def test_captures_stack_trace_for_logging(self, handler):
        """Should capture stack trace for logging only."""
        try:
            raise ValueError("test error")
        except ValueError as e:
            context = handler.handle(e)
        
        # Stack trace in log entry, not client response
        assert context.stack_trace is not None
        assert "ValueError" in context.stack_trace
        
        client_response = context.to_client_response()
        assert "stack_trace" not in str(client_response)
    
    def test_includes_request_context(self, handler):
        """Should include request context."""
        context = handler.handle(
            ValueError("test"),
            request_id="req-123",
            user_id="user-456",
            endpoint="/api/users",
        )
        
        assert context.request_id == "req-123"
        assert context.user_id == "user-456"
        assert context.endpoint == "/api/users"
    
    def test_custom_handler_registration(self, handler):
        """Should use custom handlers."""
        class CustomError(Exception):
            pass
        
        def custom_handler(exc):
            return ErrorContext(
                error_id="",
                timestamp=datetime.now(timezone.utc),
                category=ErrorCategory.BAD_REQUEST,
                severity=ErrorSeverity.WARNING,
                message="Custom error occurred",
                internal_message=str(exc),
            )
        
        handler.register_handler(CustomError, custom_handler)
        
        context = handler.handle(CustomError("test"))
        
        assert context.category == ErrorCategory.BAD_REQUEST
        assert context.message == "Custom error occurred"
    
    def test_get_http_status(self, handler):
        """Should return correct HTTP status."""
        assert handler.get_http_status(ErrorCategory.VALIDATION) == 400
        assert handler.get_http_status(ErrorCategory.AUTHENTICATION) == 401
        assert handler.get_http_status(ErrorCategory.AUTHORIZATION) == 403
        assert handler.get_http_status(ErrorCategory.NOT_FOUND) == 404
        assert handler.get_http_status(ErrorCategory.RATE_LIMIT) == 429
        assert handler.get_http_status(ErrorCategory.INTERNAL) == 500


# =============================================================================
# Test: ErrorResponseBuilder
# =============================================================================

class TestErrorResponseBuilder:
    """Test ErrorResponseBuilder."""
    
    def test_build_basic_response(self, response_builder):
        """Should build basic error response."""
        context = ErrorContext(
            error_id="ERR-12345",
            timestamp=datetime.now(timezone.utc),
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            message="Invalid input",
            internal_message="internal",
        )
        
        response = response_builder.build(context)
        
        assert "error" in response
        assert response["error"]["message"] == "Invalid input"
        assert response["error"]["category"] == "validation"
    
    def test_build_validation_error_with_fields(self, response_builder):
        """Should include field errors for validation."""
        field_errors = {
            "email": ["Invalid email format"],
            "password": ["Too short", "Missing special character"],
        }
        
        response = response_builder.build_validation_error(field_errors)
        
        assert response["error"]["category"] == "validation"
        assert "email" in response["error"]["details"]["fields"]
    
    def test_excludes_internal_details(self, response_builder):
        """Should not include internal details."""
        context = ErrorContext(
            error_id="ERR-12345",
            timestamp=datetime.now(timezone.utc),
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.ERROR,
            message="An error occurred",
            internal_message="Database error: connection refused to 192.168.1.100",
            stack_trace="Traceback (most recent call last)...",
        )
        
        response = response_builder.build(context)
        
        assert "192.168.1.100" not in str(response)
        assert "Traceback" not in str(response)


# =============================================================================
# Test: Custom Exceptions
# =============================================================================

class TestCustomExceptions:
    """Test custom secure exceptions."""
    
    def test_validation_exception(self):
        """Should have correct attributes."""
        exc = ValidationException("Invalid email")
        
        assert exc.category == ErrorCategory.VALIDATION
        assert exc.http_status == 400
        assert exc.safe_message == "Validation failed"
    
    def test_authentication_exception(self):
        """Should have correct attributes."""
        exc = AuthenticationException("Token expired")
        
        assert exc.category == ErrorCategory.AUTHENTICATION
        assert exc.http_status == 401
    
    def test_authorization_exception(self):
        """Should have correct attributes."""
        exc = AuthorizationException("No access to resource")
        
        assert exc.category == ErrorCategory.AUTHORIZATION
        assert exc.http_status == 403
    
    def test_not_found_exception(self):
        """Should have correct attributes."""
        exc = NotFoundException("User not found")
        
        assert exc.category == ErrorCategory.NOT_FOUND
        assert exc.http_status == 404
    
    def test_rate_limit_exception(self):
        """Should have correct attributes."""
        exc = RateLimitException("Too many requests")
        
        assert exc.category == ErrorCategory.RATE_LIMIT
        assert exc.http_status == 429
    
    def test_exception_with_details(self):
        """Should support additional details."""
        exc = ValidationException(
            "Validation failed",
            details={"field": "email", "value": "invalid"},
        )
        
        assert exc.details["field"] == "email"


# =============================================================================
# Test: ErrorService
# =============================================================================

class TestErrorService:
    """Test ErrorService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        s1 = get_error_service()
        s2 = get_error_service()
        
        assert s1 is s2
    
    def test_handle_error_returns_tuple(self, service):
        """Should return response and status."""
        response, status = service.handle_error(ValueError("test"))
        
        assert isinstance(response, dict)
        assert isinstance(status, int)
        assert status == 400  # ValueError -> validation -> 400
    
    def test_handles_secure_exception(self, service):
        """Should handle SecureException subclasses."""
        response, status = service.handle_error(
            AuthenticationException("Invalid token")
        )
        
        assert status == 401
        assert response["error"]["category"] == "authentication"
    
    def test_handles_standard_exception(self, service):
        """Should handle standard exceptions."""
        response, status = service.handle_error(
            RuntimeError("Unknown error")
        )
        
        assert status == 500
        assert response["error"]["category"] == "internal"


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_handle_error(self, service):
        """Should handle error via service."""
        response, status = service.handle_error(ValueError("test"))
        
        assert isinstance(response, dict)
        assert status == 400
    
    def test_safe_error_message(self):
        """Should return safe message."""
        message = safe_error_message(ValueError("secret database error"))
        
        assert "secret" not in message
        assert "database" not in message
        assert message == SAFE_MESSAGES[ErrorCategory.VALIDATION]


# =============================================================================
# Test: Information Disclosure Prevention
# =============================================================================

class TestInformationDisclosure:
    """Test that sensitive information is not disclosed."""
    
    def test_no_database_details(self, handler):
        """Should not expose database details."""
        context = handler.handle(
            Exception("PostgreSQL error: FATAL password authentication failed for user 'admin'")
        )
        
        response = context.to_client_response()
        response_str = str(response)
        
        assert "PostgreSQL" not in response_str
        assert "password" not in response_str
        assert "admin" not in response_str
    
    def test_no_file_paths(self, handler):
        """Should not expose file paths."""
        context = handler.handle(
            Exception("Error reading /etc/secrets/database.conf")
        )
        
        response = context.to_client_response()
        
        assert "/etc/secrets" not in str(response)
    
    def test_no_ip_addresses(self, handler):
        """Should not expose IP addresses."""
        context = handler.handle(
            Exception("Connection failed to 192.168.1.100:5432")
        )
        
        response = context.to_client_response()
        
        assert "192.168" not in str(response)
    
    def test_no_api_keys(self, handler):
        """Should not expose API keys."""
        context = handler.handle(
            Exception("API call failed with key: sk_live_1234567890abcdef")
        )
        
        response = context.to_client_response()
        
        assert "sk_live" not in str(response)
        assert "1234567890" not in str(response)
