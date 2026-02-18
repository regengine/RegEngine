"""
SEC-027: Request Validation.

Provides comprehensive API request validation:
- Request body validation
- Query parameter validation
- Header validation
- Content-Type validation
- Request size limits
- Schema validation
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class RequestValidationError(Exception):
    """Base exception for request validation errors."""
    
    def __init__(self, message: str, errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.errors = errors or []


class InvalidContentTypeError(RequestValidationError):
    """Raised when content type is invalid."""
    pass


class RequestSizeLimitError(RequestValidationError):
    """Raised when request exceeds size limit."""
    pass


class InvalidParameterError(RequestValidationError):
    """Raised when parameter is invalid."""
    pass


class MissingParameterError(RequestValidationError):
    """Raised when required parameter is missing."""
    pass


class SchemaValidationError(RequestValidationError):
    """Raised when schema validation fails."""
    pass


# =============================================================================
# Enums
# =============================================================================

class ContentType(str, Enum):
    """Supported content types."""
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    MULTIPART = "multipart/form-data"
    TEXT = "text/plain"
    XML = "application/xml"


class ParameterLocation(str, Enum):
    """Parameter locations."""
    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    BODY = "body"


class FieldType(str, Enum):
    """Field types for validation."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    EMAIL = "email"
    URL = "url"
    UUID = "uuid"
    DATE = "date"
    DATETIME = "datetime"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FieldRule:
    """Validation rule for a field."""
    field_type: FieldType = FieldType.STRING
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    enum_values: Optional[List[Any]] = None
    default: Any = None
    description: str = ""


@dataclass
class ValidationError:
    """Single validation error."""
    field: str
    message: str
    location: ParameterLocation = ParameterLocation.BODY
    value: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "message": self.message,
            "location": self.location.value,
        }


@dataclass
class ValidationResult:
    """Result of validation."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    sanitized_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass
class RequestLimits:
    """Request size and content limits."""
    max_body_size: int = 1024 * 1024  # 1 MB
    max_query_params: int = 50
    max_headers: int = 100
    max_array_items: int = 1000
    max_string_length: int = 10000
    max_json_depth: int = 20


# =============================================================================
# Field Validators
# =============================================================================

class FieldValidator:
    """Validates individual fields."""
    
    # Email pattern
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    # URL pattern
    URL_PATTERN = re.compile(
        r'^https?://[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+(/[^\s]*)?$'
    )
    
    # UUID pattern
    UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE,
    )
    
    def validate(
        self,
        value: Any,
        rule: FieldRule,
        field_name: str,
    ) -> List[ValidationError]:
        """
        Validate a field value against rules.
        
        Args:
            value: Value to validate
            rule: Validation rules
            field_name: Field name for errors
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check required
        if value is None:
            if rule.required:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"{field_name} is required",
                ))
            return errors
        
        # Type validation
        type_errors = self._validate_type(value, rule, field_name)
        if type_errors:
            return type_errors
        
        # Type-specific validation
        if rule.field_type == FieldType.STRING:
            errors.extend(self._validate_string(value, rule, field_name))
        elif rule.field_type == FieldType.INTEGER:
            errors.extend(self._validate_number(value, rule, field_name))
        elif rule.field_type == FieldType.FLOAT:
            errors.extend(self._validate_number(value, rule, field_name))
        elif rule.field_type == FieldType.EMAIL:
            errors.extend(self._validate_email(value, field_name))
        elif rule.field_type == FieldType.URL:
            errors.extend(self._validate_url(value, field_name))
        elif rule.field_type == FieldType.UUID:
            errors.extend(self._validate_uuid(value, field_name))
        elif rule.field_type == FieldType.ARRAY:
            errors.extend(self._validate_array(value, rule, field_name))
        
        # Enum validation
        if rule.enum_values and value not in rule.enum_values:
            errors.append(ValidationError(
                field=field_name,
                message=f"Must be one of: {rule.enum_values}",
                value=value,
            ))
        
        # Pattern validation
        if rule.pattern:
            errors.extend(self._validate_pattern(value, rule.pattern, field_name))
        
        return errors
    
    def _validate_type(
        self,
        value: Any,
        rule: FieldRule,
        field_name: str,
    ) -> List[ValidationError]:
        """Validate value type."""
        errors = []
        
        type_map = {
            FieldType.STRING: str,
            FieldType.EMAIL: str,
            FieldType.URL: str,
            FieldType.UUID: str,
            FieldType.INTEGER: int,
            FieldType.FLOAT: (int, float),
            FieldType.BOOLEAN: bool,
            FieldType.ARRAY: list,
            FieldType.OBJECT: dict,
        }
        
        expected_type = type_map.get(rule.field_type)
        
        if expected_type and not isinstance(value, expected_type):
            errors.append(ValidationError(
                field=field_name,
                message=f"Expected type {rule.field_type.value}, got {type(value).__name__}",
                value=value,
            ))
        
        return errors
    
    def _validate_string(
        self,
        value: str,
        rule: FieldRule,
        field_name: str,
    ) -> List[ValidationError]:
        """Validate string value."""
        errors = []
        
        if rule.min_length is not None and len(value) < rule.min_length:
            errors.append(ValidationError(
                field=field_name,
                message=f"Minimum length is {rule.min_length}",
                value=value,
            ))
        
        if rule.max_length is not None and len(value) > rule.max_length:
            errors.append(ValidationError(
                field=field_name,
                message=f"Maximum length is {rule.max_length}",
                value=value,
            ))
        
        return errors
    
    def _validate_number(
        self,
        value: Union[int, float],
        rule: FieldRule,
        field_name: str,
    ) -> List[ValidationError]:
        """Validate numeric value."""
        errors = []
        
        if rule.min_value is not None and value < rule.min_value:
            errors.append(ValidationError(
                field=field_name,
                message=f"Minimum value is {rule.min_value}",
                value=value,
            ))
        
        if rule.max_value is not None and value > rule.max_value:
            errors.append(ValidationError(
                field=field_name,
                message=f"Maximum value is {rule.max_value}",
                value=value,
            ))
        
        return errors
    
    def _validate_email(self, value: str, field_name: str) -> List[ValidationError]:
        """Validate email format."""
        errors = []
        
        if not self.EMAIL_PATTERN.match(value):
            errors.append(ValidationError(
                field=field_name,
                message="Invalid email format",
                value=value,
            ))
        
        return errors
    
    def _validate_url(self, value: str, field_name: str) -> List[ValidationError]:
        """Validate URL format."""
        errors = []
        
        if not self.URL_PATTERN.match(value):
            errors.append(ValidationError(
                field=field_name,
                message="Invalid URL format",
                value=value,
            ))
        
        return errors
    
    def _validate_uuid(self, value: str, field_name: str) -> List[ValidationError]:
        """Validate UUID format."""
        errors = []
        
        if not self.UUID_PATTERN.match(value):
            errors.append(ValidationError(
                field=field_name,
                message="Invalid UUID format",
                value=value,
            ))
        
        return errors
    
    def _validate_array(
        self,
        value: list,
        rule: FieldRule,
        field_name: str,
    ) -> List[ValidationError]:
        """Validate array value."""
        errors = []
        
        if rule.min_length is not None and len(value) < rule.min_length:
            errors.append(ValidationError(
                field=field_name,
                message=f"Minimum items is {rule.min_length}",
                value=value,
            ))
        
        if rule.max_length is not None and len(value) > rule.max_length:
            errors.append(ValidationError(
                field=field_name,
                message=f"Maximum items is {rule.max_length}",
                value=value,
            ))
        
        return errors
    
    def _validate_pattern(
        self,
        value: str,
        pattern: str,
        field_name: str,
    ) -> List[ValidationError]:
        """Validate against regex pattern."""
        errors = []
        
        try:
            if not re.match(pattern, str(value)):
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Does not match pattern: {pattern}",
                    value=value,
                ))
        except re.error:
            errors.append(ValidationError(
                field=field_name,
                message="Invalid pattern",
                value=value,
            ))
        
        return errors


# =============================================================================
# Request Validator
# =============================================================================

class RequestValidator:
    """
    Validates API requests.
    
    Features:
    - Body validation
    - Query parameter validation
    - Header validation
    - Content-Type validation
    """
    
    def __init__(
        self,
        limits: Optional[RequestLimits] = None,
    ):
        """Initialize validator."""
        self.limits = limits or RequestLimits()
        self.field_validator = FieldValidator()
    
    def validate_content_type(
        self,
        content_type: str,
        allowed: List[ContentType],
    ) -> None:
        """
        Validate content type.
        
        Args:
            content_type: Request content type
            allowed: Allowed content types
            
        Raises:
            InvalidContentTypeError: If content type not allowed
        """
        # Extract media type without parameters
        media_type = content_type.split(";")[0].strip().lower()
        
        allowed_types = [ct.value.lower() for ct in allowed]
        
        if media_type not in allowed_types:
            raise InvalidContentTypeError(
                f"Content type '{content_type}' not allowed. "
                f"Allowed: {allowed_types}"
            )
    
    def validate_body_size(self, body: bytes) -> None:
        """
        Validate request body size.
        
        Args:
            body: Request body bytes
            
        Raises:
            RequestSizeLimitError: If body exceeds limit
        """
        if len(body) > self.limits.max_body_size:
            raise RequestSizeLimitError(
                f"Request body exceeds maximum size of {self.limits.max_body_size} bytes"
            )
    
    def validate_json_body(
        self,
        body: Union[str, bytes, Dict[str, Any]],
        schema: Dict[str, FieldRule],
    ) -> ValidationResult:
        """
        Validate JSON request body against schema.
        
        Args:
            body: JSON body (string, bytes, or parsed dict)
            schema: Field rules by field name
            
        Returns:
            ValidationResult
        """
        errors = []
        sanitized = {}
        
        # Parse body if needed
        if isinstance(body, (str, bytes)):
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    valid=False,
                    errors=[ValidationError(
                        field="_body",
                        message=f"Invalid JSON: {e}",
                    )],
                )
        else:
            data = body
        
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                errors=[ValidationError(
                    field="_body",
                    message="Expected JSON object",
                )],
            )
        
        # Check for unknown fields
        known_fields = set(schema.keys())
        unknown_fields = set(data.keys()) - known_fields
        
        for field_name in unknown_fields:
            errors.append(ValidationError(
                field=field_name,
                message="Unknown field",
                location=ParameterLocation.BODY,
            ))
        
        # Validate each field
        for field_name, rule in schema.items():
            value = data.get(field_name, rule.default)
            
            field_errors = self.field_validator.validate(value, rule, field_name)
            
            for error in field_errors:
                error.location = ParameterLocation.BODY
            
            errors.extend(field_errors)
            
            if not field_errors and value is not None:
                sanitized[field_name] = value
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            sanitized_data=sanitized,
        )
    
    def validate_query_params(
        self,
        params: Dict[str, Any],
        schema: Dict[str, FieldRule],
    ) -> ValidationResult:
        """
        Validate query parameters.
        
        Args:
            params: Query parameters
            schema: Field rules by param name
            
        Returns:
            ValidationResult
        """
        errors = []
        sanitized = {}
        
        # Check param count
        if len(params) > self.limits.max_query_params:
            return ValidationResult(
                valid=False,
                errors=[ValidationError(
                    field="_query",
                    message=f"Too many query parameters (max: {self.limits.max_query_params})",
                    location=ParameterLocation.QUERY,
                )],
            )
        
        # Validate each param
        for param_name, rule in schema.items():
            value = params.get(param_name, rule.default)
            
            # Type coercion for query params
            if value is not None and isinstance(value, str):
                value = self._coerce_type(value, rule.field_type)
            
            field_errors = self.field_validator.validate(value, rule, param_name)
            
            for error in field_errors:
                error.location = ParameterLocation.QUERY
            
            errors.extend(field_errors)
            
            if not field_errors and value is not None:
                sanitized[param_name] = value
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            sanitized_data=sanitized,
        )
    
    def validate_headers(
        self,
        headers: Dict[str, str],
        required: Optional[List[str]] = None,
        forbidden: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        Validate request headers.
        
        Args:
            headers: Request headers
            required: Required header names
            forbidden: Forbidden header names
            
        Returns:
            ValidationResult
        """
        errors = []
        
        # Check header count
        if len(headers) > self.limits.max_headers:
            return ValidationResult(
                valid=False,
                errors=[ValidationError(
                    field="_headers",
                    message=f"Too many headers (max: {self.limits.max_headers})",
                    location=ParameterLocation.HEADER,
                )],
            )
        
        # Normalize header names
        normalized = {k.lower(): v for k, v in headers.items()}
        
        # Check required
        if required:
            for header in required:
                if header.lower() not in normalized:
                    errors.append(ValidationError(
                        field=header,
                        message=f"Required header missing: {header}",
                        location=ParameterLocation.HEADER,
                    ))
        
        # Check forbidden
        if forbidden:
            for header in forbidden:
                if header.lower() in normalized:
                    errors.append(ValidationError(
                        field=header,
                        message=f"Forbidden header present: {header}",
                        location=ParameterLocation.HEADER,
                    ))
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )
    
    def _coerce_type(self, value: str, field_type: FieldType) -> Any:
        """Coerce string value to target type."""
        try:
            if field_type == FieldType.INTEGER:
                return int(value)
            elif field_type == FieldType.FLOAT:
                return float(value)
            elif field_type == FieldType.BOOLEAN:
                return value.lower() in ("true", "1", "yes")
            elif field_type == FieldType.ARRAY:
                return value.split(",")
            else:
                return value
        except (ValueError, AttributeError):
            return value


# =============================================================================
# Schema Builder
# =============================================================================

class SchemaBuilder:
    """Fluent builder for validation schemas."""
    
    def __init__(self):
        """Initialize builder."""
        self._schema: Dict[str, FieldRule] = {}
    
    def add_field(
        self,
        name: str,
        field_type: FieldType = FieldType.STRING,
        **kwargs,
    ) -> "SchemaBuilder":
        """Add a field to the schema."""
        self._schema[name] = FieldRule(field_type=field_type, **kwargs)
        return self
    
    def string(
        self,
        name: str,
        required: bool = False,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        **kwargs,
    ) -> "SchemaBuilder":
        """Add string field."""
        return self.add_field(
            name,
            FieldType.STRING,
            required=required,
            min_length=min_length,
            max_length=max_length,
            pattern=pattern,
            **kwargs,
        )
    
    def integer(
        self,
        name: str,
        required: bool = False,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        **kwargs,
    ) -> "SchemaBuilder":
        """Add integer field."""
        return self.add_field(
            name,
            FieldType.INTEGER,
            required=required,
            min_value=min_value,
            max_value=max_value,
            **kwargs,
        )
    
    def email(self, name: str, required: bool = False, **kwargs) -> "SchemaBuilder":
        """Add email field."""
        return self.add_field(name, FieldType.EMAIL, required=required, **kwargs)
    
    def uuid(self, name: str, required: bool = False, **kwargs) -> "SchemaBuilder":
        """Add UUID field."""
        return self.add_field(name, FieldType.UUID, required=required, **kwargs)
    
    def build(self) -> Dict[str, FieldRule]:
        """Build the schema."""
        return self._schema.copy()


# =============================================================================
# Request Validation Service
# =============================================================================

class RequestValidationService:
    """
    High-level service for request validation.
    
    Provides:
    - Schema registration
    - Request validation
    - Error formatting
    """
    
    _instance: Optional["RequestValidationService"] = None
    
    def __init__(
        self,
        limits: Optional[RequestLimits] = None,
    ):
        """Initialize service."""
        self.validator = RequestValidator(limits)
        self._schemas: Dict[str, Dict[str, FieldRule]] = {}
    
    @classmethod
    def get_instance(cls) -> "RequestValidationService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_schema(
        self,
        endpoint: str,
        schema: Dict[str, FieldRule],
    ) -> None:
        """Register schema for endpoint."""
        self._schemas[endpoint] = schema
    
    def validate_request(
        self,
        endpoint: str,
        body: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate a complete request.
        
        Args:
            endpoint: Endpoint identifier
            body: Request body
            query_params: Query parameters
            headers: Request headers
            content_type: Content-Type header
            
        Returns:
            ValidationResult
        """
        all_errors = []
        sanitized = {}
        
        schema = self._schemas.get(endpoint, {})
        
        # Validate body
        if body is not None and schema:
            result = self.validator.validate_json_body(body, schema)
            all_errors.extend(result.errors)
            sanitized.update(result.sanitized_data)
        
        # Validate query params
        if query_params:
            result = self.validator.validate_query_params(query_params, schema)
            all_errors.extend(result.errors)
            sanitized.update(result.sanitized_data)
        
        return ValidationResult(
            valid=len(all_errors) == 0,
            errors=all_errors,
            sanitized_data=sanitized,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def get_validation_service() -> RequestValidationService:
    """Get the global validation service."""
    return RequestValidationService.get_instance()


def validate_json(
    body: Union[str, bytes, Dict[str, Any]],
    schema: Dict[str, FieldRule],
) -> ValidationResult:
    """Validate JSON body against schema."""
    validator = RequestValidator()
    return validator.validate_json_body(body, schema)


def create_schema() -> SchemaBuilder:
    """Create a new schema builder."""
    return SchemaBuilder()
