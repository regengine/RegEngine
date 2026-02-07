"""
Tests for SEC-027: Request Validation.

Tests cover:
- Field validation
- Body validation
- Query parameter validation
- Content-Type validation
- Schema builder
- Request validation service
"""

import pytest
import json

from shared.request_validation import (
    # Enums
    ContentType,
    ParameterLocation,
    FieldType,
    # Exceptions
    RequestValidationError,
    InvalidContentTypeError,
    RequestSizeLimitError,
    # Data classes
    FieldRule,
    ValidationError,
    ValidationResult,
    RequestLimits,
    # Classes
    FieldValidator,
    RequestValidator,
    SchemaBuilder,
    RequestValidationService,
    # Convenience functions
    get_validation_service,
    validate_json,
    create_schema,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def field_validator():
    """Create field validator."""
    return FieldValidator()


@pytest.fixture
def request_validator():
    """Create request validator."""
    return RequestValidator()


@pytest.fixture
def service():
    """Create validation service."""
    return RequestValidationService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_content_types(self):
        """Should have expected content types."""
        assert ContentType.JSON == "application/json"
        assert ContentType.FORM == "application/x-www-form-urlencoded"
    
    def test_field_types(self):
        """Should have expected field types."""
        assert FieldType.STRING == "string"
        assert FieldType.EMAIL == "email"
        assert FieldType.UUID == "uuid"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""
    
    def test_field_rule_defaults(self):
        """Should have sensible defaults."""
        rule = FieldRule()
        
        assert rule.field_type == FieldType.STRING
        assert rule.required is False
    
    def test_validation_error_to_dict(self):
        """Should convert to dictionary."""
        error = ValidationError(
            field="email",
            message="Invalid format",
            location=ParameterLocation.BODY,
        )
        
        data = error.to_dict()
        
        assert data["field"] == "email"
        assert data["message"] == "Invalid format"
        assert data["location"] == "body"
    
    def test_validation_result(self):
        """Should track validation state."""
        result = ValidationResult(
            valid=True,
            errors=[],
            sanitized_data={"name": "test"},
        )
        
        assert result.valid is True


# =============================================================================
# Test: Field Validator
# =============================================================================

class TestFieldValidator:
    """Test FieldValidator."""
    
    def test_required_field_missing(self, field_validator):
        """Should error on missing required field."""
        rule = FieldRule(required=True)
        
        errors = field_validator.validate(None, rule, "name")
        
        assert len(errors) == 1
        assert "required" in errors[0].message.lower()
    
    def test_required_field_present(self, field_validator):
        """Should pass for present required field."""
        rule = FieldRule(required=True)
        
        errors = field_validator.validate("value", rule, "name")
        
        assert len(errors) == 0
    
    def test_string_min_length(self, field_validator):
        """Should validate minimum length."""
        rule = FieldRule(field_type=FieldType.STRING, min_length=5)
        
        errors = field_validator.validate("ab", rule, "name")
        
        assert len(errors) == 1
        assert "minimum" in errors[0].message.lower()
    
    def test_string_max_length(self, field_validator):
        """Should validate maximum length."""
        rule = FieldRule(field_type=FieldType.STRING, max_length=5)
        
        errors = field_validator.validate("abcdefgh", rule, "name")
        
        assert len(errors) == 1
        assert "maximum" in errors[0].message.lower()
    
    def test_integer_min_value(self, field_validator):
        """Should validate minimum value."""
        rule = FieldRule(field_type=FieldType.INTEGER, min_value=10)
        
        errors = field_validator.validate(5, rule, "count")
        
        assert len(errors) == 1
        assert "minimum" in errors[0].message.lower()
    
    def test_integer_max_value(self, field_validator):
        """Should validate maximum value."""
        rule = FieldRule(field_type=FieldType.INTEGER, max_value=100)
        
        errors = field_validator.validate(150, rule, "count")
        
        assert len(errors) == 1
        assert "maximum" in errors[0].message.lower()
    
    def test_email_valid(self, field_validator):
        """Should accept valid email."""
        rule = FieldRule(field_type=FieldType.EMAIL)
        
        errors = field_validator.validate("user@example.com", rule, "email")
        
        assert len(errors) == 0
    
    def test_email_invalid(self, field_validator):
        """Should reject invalid email."""
        rule = FieldRule(field_type=FieldType.EMAIL)
        
        errors = field_validator.validate("invalid-email", rule, "email")
        
        assert len(errors) == 1
        assert "email" in errors[0].message.lower()
    
    def test_url_valid(self, field_validator):
        """Should accept valid URL."""
        rule = FieldRule(field_type=FieldType.URL)
        
        errors = field_validator.validate("https://example.com/path", rule, "website")
        
        assert len(errors) == 0
    
    def test_url_invalid(self, field_validator):
        """Should reject invalid URL."""
        rule = FieldRule(field_type=FieldType.URL)
        
        errors = field_validator.validate("not-a-url", rule, "website")
        
        assert len(errors) == 1
    
    def test_uuid_valid(self, field_validator):
        """Should accept valid UUID."""
        rule = FieldRule(field_type=FieldType.UUID)
        
        errors = field_validator.validate(
            "550e8400-e29b-41d4-a716-446655440000",
            rule,
            "id",
        )
        
        assert len(errors) == 0
    
    def test_uuid_invalid(self, field_validator):
        """Should reject invalid UUID."""
        rule = FieldRule(field_type=FieldType.UUID)
        
        errors = field_validator.validate("not-a-uuid", rule, "id")
        
        assert len(errors) == 1
    
    def test_enum_validation(self, field_validator):
        """Should validate enum values."""
        rule = FieldRule(enum_values=["active", "inactive"])
        
        errors = field_validator.validate("pending", rule, "status")
        
        assert len(errors) == 1
        assert "one of" in errors[0].message.lower()
    
    def test_pattern_validation(self, field_validator):
        """Should validate against pattern."""
        rule = FieldRule(pattern=r"^\d{3}-\d{4}$")
        
        errors = field_validator.validate("123-4567", rule, "phone")
        assert len(errors) == 0
        
        errors = field_validator.validate("invalid", rule, "phone")
        assert len(errors) == 1
    
    def test_type_mismatch(self, field_validator):
        """Should detect type mismatch."""
        rule = FieldRule(field_type=FieldType.INTEGER)
        
        errors = field_validator.validate("not-an-int", rule, "count")
        
        assert len(errors) == 1
        assert "expected type" in errors[0].message.lower()


# =============================================================================
# Test: Request Validator
# =============================================================================

class TestRequestValidator:
    """Test RequestValidator."""
    
    def test_validate_content_type_allowed(self, request_validator):
        """Should allow valid content type."""
        # Should not raise
        request_validator.validate_content_type(
            "application/json",
            [ContentType.JSON],
        )
    
    def test_validate_content_type_denied(self, request_validator):
        """Should reject invalid content type."""
        with pytest.raises(InvalidContentTypeError):
            request_validator.validate_content_type(
                "text/plain",
                [ContentType.JSON],
            )
    
    def test_validate_body_size_ok(self, request_validator):
        """Should allow body within limit."""
        body = b"x" * 1000
        
        # Should not raise
        request_validator.validate_body_size(body)
    
    def test_validate_body_size_exceeded(self):
        """Should reject oversized body."""
        limits = RequestLimits(max_body_size=100)
        validator = RequestValidator(limits)
        
        body = b"x" * 200
        
        with pytest.raises(RequestSizeLimitError):
            validator.validate_body_size(body)
    
    def test_validate_json_body_valid(self, request_validator):
        """Should validate valid JSON body."""
        schema = {
            "name": FieldRule(required=True),
            "email": FieldRule(field_type=FieldType.EMAIL, required=True),
        }
        
        body = {"name": "Test User", "email": "user@example.com"}
        
        result = request_validator.validate_json_body(body, schema)
        
        assert result.valid is True
        assert result.sanitized_data["name"] == "Test User"
    
    def test_validate_json_body_invalid(self, request_validator):
        """Should detect invalid JSON body."""
        schema = {
            "email": FieldRule(field_type=FieldType.EMAIL, required=True),
        }
        
        body = {"email": "invalid"}
        
        result = request_validator.validate_json_body(body, schema)
        
        assert result.valid is False
        assert len(result.errors) > 0
    
    def test_validate_json_string_body(self, request_validator):
        """Should parse JSON string."""
        schema = {"name": FieldRule(required=True)}
        
        body = '{"name": "Test"}'
        
        result = request_validator.validate_json_body(body, schema)
        
        assert result.valid is True
    
    def test_validate_json_invalid_syntax(self, request_validator):
        """Should detect invalid JSON syntax."""
        schema = {"name": FieldRule()}
        
        body = "not valid json"
        
        result = request_validator.validate_json_body(body, schema)
        
        assert result.valid is False
        assert "invalid json" in result.errors[0].message.lower()
    
    def test_validate_unknown_fields(self, request_validator):
        """Should detect unknown fields."""
        schema = {"name": FieldRule()}
        
        body = {"name": "Test", "unknown_field": "value"}
        
        result = request_validator.validate_json_body(body, schema)
        
        assert result.valid is False
        assert any("unknown" in e.message.lower() for e in result.errors)
    
    def test_validate_query_params(self, request_validator):
        """Should validate query parameters."""
        schema = {
            "page": FieldRule(field_type=FieldType.INTEGER, min_value=1),
            "limit": FieldRule(field_type=FieldType.INTEGER, max_value=100),
        }
        
        params = {"page": "1", "limit": "20"}
        
        result = request_validator.validate_query_params(params, schema)
        
        assert result.valid is True
        assert result.sanitized_data["page"] == 1
    
    def test_validate_headers_required(self, request_validator):
        """Should require specified headers."""
        headers = {"Content-Type": "application/json"}
        
        result = request_validator.validate_headers(
            headers,
            required=["Authorization"],
        )
        
        assert result.valid is False
    
    def test_validate_headers_forbidden(self, request_validator):
        """Should reject forbidden headers."""
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Token": "secret",
        }
        
        result = request_validator.validate_headers(
            headers,
            forbidden=["X-Internal-Token"],
        )
        
        assert result.valid is False


# =============================================================================
# Test: Schema Builder
# =============================================================================

class TestSchemaBuilder:
    """Test SchemaBuilder."""
    
    def test_build_string_field(self):
        """Should build string field."""
        schema = (
            create_schema()
            .string("name", required=True, min_length=1, max_length=100)
            .build()
        )
        
        assert "name" in schema
        assert schema["name"].field_type == FieldType.STRING
        assert schema["name"].required is True
    
    def test_build_integer_field(self):
        """Should build integer field."""
        schema = (
            create_schema()
            .integer("age", min_value=0, max_value=150)
            .build()
        )
        
        assert "age" in schema
        assert schema["age"].field_type == FieldType.INTEGER
    
    def test_build_email_field(self):
        """Should build email field."""
        schema = (
            create_schema()
            .email("email", required=True)
            .build()
        )
        
        assert "email" in schema
        assert schema["email"].field_type == FieldType.EMAIL
    
    def test_build_uuid_field(self):
        """Should build UUID field."""
        schema = (
            create_schema()
            .uuid("id", required=True)
            .build()
        )
        
        assert "id" in schema
        assert schema["id"].field_type == FieldType.UUID
    
    def test_fluent_chaining(self):
        """Should support fluent chaining."""
        schema = (
            create_schema()
            .string("name", required=True)
            .email("email", required=True)
            .integer("age", min_value=0)
            .build()
        )
        
        assert len(schema) == 3


# =============================================================================
# Test: Request Validation Service
# =============================================================================

class TestRequestValidationService:
    """Test RequestValidationService."""
    
    def test_register_schema(self, service):
        """Should register schema."""
        schema = {"name": FieldRule(required=True)}
        
        service.register_schema("/api/users", schema)
        
        assert "/api/users" in service._schemas
    
    def test_validate_request(self, service):
        """Should validate complete request."""
        schema = {
            "name": FieldRule(required=True),
            "email": FieldRule(field_type=FieldType.EMAIL, required=True),
        }
        
        service.register_schema("/api/users", schema)
        
        result = service.validate_request(
            "/api/users",
            body={"name": "Test", "email": "test@example.com"},
        )
        
        assert result.valid is True
    
    def test_validate_request_fails(self, service):
        """Should fail invalid request."""
        schema = {
            "email": FieldRule(field_type=FieldType.EMAIL, required=True),
        }
        
        service.register_schema("/api/users", schema)
        
        result = service.validate_request(
            "/api/users",
            body={"email": "invalid"},
        )
        
        assert result.valid is False


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_validation_service(self):
        """Should return service instance."""
        service = get_validation_service()
        assert service is not None
    
    def test_validate_json_function(self):
        """Should validate via convenience function."""
        schema = {"name": FieldRule(required=True)}
        
        result = validate_json({"name": "Test"}, schema)
        
        assert result.valid is True
    
    def test_create_schema_function(self):
        """Should create schema builder."""
        builder = create_schema()
        
        assert isinstance(builder, SchemaBuilder)
