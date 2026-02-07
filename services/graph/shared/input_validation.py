"""
SEC-011: Input Validation for RegEngine.

This module provides comprehensive input validation to prevent:
- SQL Injection
- NoSQL Injection
- Command Injection
- LDAP Injection
- XPath Injection

Usage:
    from shared.input_validation import InputValidator, ValidationError
    
    validator = InputValidator()
    
    # Validate user input
    clean_id = validator.validate_identifier(user_input)
    clean_email = validator.validate_email(email_input)
    
    # Or use decorators
    @validate_input(id=IdentifierField(), email=EmailField())
    async def create_user(id: str, email: str):
        ...
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Pattern, TypeVar, Union
from functools import wraps

import structlog
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger("input_validation")


# =============================================================================
# Exceptions
# =============================================================================

class ValidationError(Exception):
    """Raised when input validation fails."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        code: str = "VALIDATION_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.field = field
        self.value = value
        self.code = code
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "error": self.code,
            "message": self.message,
            "field": self.field,
        }


class InjectionAttemptError(ValidationError):
    """Raised when injection attempt is detected."""
    
    def __init__(
        self,
        message: str,
        injection_type: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ):
        super().__init__(
            message=message,
            field=field,
            value=value,
            code="INJECTION_ATTEMPT",
        )
        self.injection_type = injection_type


# =============================================================================
# Injection Detection Patterns
# =============================================================================

class InjectionPatterns:
    """Patterns for detecting injection attempts."""
    
    # SQL Injection patterns
    SQL_INJECTION: list[Pattern] = [
        re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|TRUNCATE)\b)", re.IGNORECASE),
        re.compile(r"(\b(OR|AND)\s+[\d\w]+\s*=\s*[\d\w]+)", re.IGNORECASE),
        re.compile(r"(--|#|/\*|\*/)", re.IGNORECASE),  # SQL comments
        re.compile(r"(\bEXEC\b|\bEXECUTE\b|\bXP_)", re.IGNORECASE),
        re.compile(r"(;\s*(DROP|DELETE|INSERT|UPDATE))", re.IGNORECASE),
        re.compile(r"('\s*OR\s*'|\"\s*OR\s*\")", re.IGNORECASE),
        re.compile(r"(SLEEP\s*\(|WAITFOR\s+DELAY|BENCHMARK\s*\()", re.IGNORECASE),
        re.compile(r"(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)", re.IGNORECASE),
    ]
    
    # NoSQL Injection patterns (MongoDB, etc.)
    NOSQL_INJECTION: list[Pattern] = [
        re.compile(r"(\$where|\$gt|\$lt|\$ne|\$in|\$nin|\$or|\$and|\$not|\$exists)", re.IGNORECASE),
        re.compile(r"(\$regex|\$options|\$elemMatch|\$size|\$type)", re.IGNORECASE),
        re.compile(r"(mapReduce|group|aggregate)", re.IGNORECASE),
        re.compile(r'(\{\s*"\$)', re.IGNORECASE),  # JSON operators
    ]
    
    # Command Injection patterns
    COMMAND_INJECTION: list[Pattern] = [
        re.compile(r"([;&|`$])", re.IGNORECASE),
        re.compile(r"(\|\||&&)", re.IGNORECASE),
        re.compile(r"(\$\(|\$\{|`)", re.IGNORECASE),  # Command substitution
        re.compile(r"(>|<|>>|<<)", re.IGNORECASE),  # Redirection
        re.compile(r"(\bcat\b|\bls\b|\brm\b|\bchmod\b|\bchown\b)", re.IGNORECASE),
        re.compile(r"(/etc/passwd|/etc/shadow|/bin/sh|/bin/bash)", re.IGNORECASE),
    ]
    
    # LDAP Injection patterns
    LDAP_INJECTION: list[Pattern] = [
        re.compile(r"([)(|*\\])", re.IGNORECASE),
        re.compile(r"(\x00|\x0a|\x0d)", re.IGNORECASE),  # Null, newline, carriage return
    ]
    
    # XPath Injection patterns
    XPATH_INJECTION: list[Pattern] = [
        re.compile(r"(\[|\]|/|\||@|::|\.\.)", re.IGNORECASE),
        re.compile(r"(\bor\b|\band\b|\bnot\b)", re.IGNORECASE),
        re.compile(r"(contains\s*\(|starts-with\s*\(|string\s*\()", re.IGNORECASE),
    ]
    
    # Header Injection patterns
    HEADER_INJECTION: list[Pattern] = [
        re.compile(r"(\r\n|\r|\n)", re.IGNORECASE),
        re.compile(r"(Set-Cookie|Location|Content-Type):", re.IGNORECASE),
    ]


# =============================================================================
# Input Sanitizers
# =============================================================================

class InputSanitizer:
    """Sanitize input to remove dangerous content."""
    
    @staticmethod
    def strip_sql_chars(value: str) -> str:
        """Remove SQL-specific dangerous characters."""
        # Remove SQL comment sequences
        value = re.sub(r'--.*$', '', value, flags=re.MULTILINE)
        value = re.sub(r'/\*.*?\*/', '', value, flags=re.DOTALL)
        # Remove semicolons that could chain commands
        value = value.replace(';', '')
        return value.strip()
    
    @staticmethod
    def strip_shell_chars(value: str) -> str:
        """Remove shell-specific dangerous characters."""
        dangerous = set(';&|`$(){}[]<>\\\'\"')
        return ''.join(c for c in value if c not in dangerous)
    
    @staticmethod
    def strip_html(value: str) -> str:
        """Remove HTML tags."""
        return re.sub(r'<[^>]+>', '', value)
    
    @staticmethod
    def escape_sql(value: str) -> str:
        """Escape SQL special characters."""
        replacements = {
            "'": "''",
            "\\": "\\\\",
            "\x00": "\\0",
            "\n": "\\n",
            "\r": "\\r",
            "\x1a": "\\Z",
        }
        for char, escape in replacements.items():
            value = value.replace(char, escape)
        return value
    
    @staticmethod
    def normalize_unicode(value: str) -> str:
        """Normalize unicode to prevent homograph attacks."""
        import unicodedata
        # Normalize to NFC form
        normalized = unicodedata.normalize('NFC', value)
        # Remove non-printable characters
        return ''.join(c for c in normalized if unicodedata.category(c) != 'Cc')
    
    @staticmethod
    def to_alphanumeric(value: str, allowed: str = "") -> str:
        """Keep only alphanumeric characters and specified allowed chars."""
        allowed_set = set(string.ascii_letters + string.digits + allowed)
        return ''.join(c for c in value if c in allowed_set)


# =============================================================================
# Validation Rules
# =============================================================================

@dataclass
class ValidationRule:
    """Base class for validation rules."""
    
    name: str = "base"
    
    def validate(self, value: Any, field_name: str = "") -> Any:
        """Validate and return cleaned value."""
        raise NotImplementedError


@dataclass
class LengthRule(ValidationRule):
    """Validate string length."""
    
    name: str = "length"
    min_length: int = 0
    max_length: int = 10000
    
    def validate(self, value: Any, field_name: str = "") -> str:
        if not isinstance(value, str):
            value = str(value)
        
        if len(value) < self.min_length:
            raise ValidationError(
                f"Value too short (min {self.min_length})",
                field=field_name,
            )
        
        if len(value) > self.max_length:
            raise ValidationError(
                f"Value too long (max {self.max_length})",
                field=field_name,
            )
        
        return value


@dataclass
class PatternRule(ValidationRule):
    """Validate against regex pattern."""
    
    name: str = "pattern"
    pattern: str = ".*"
    message: str = "Value does not match required pattern"
    
    def __post_init__(self):
        self._compiled = re.compile(self.pattern)
    
    def validate(self, value: Any, field_name: str = "") -> str:
        if not isinstance(value, str):
            value = str(value)
        
        if not self._compiled.match(value):
            raise ValidationError(
                self.message,
                field=field_name,
                value=value[:50] if len(value) > 50 else value,
            )
        
        return value


@dataclass
class InjectionRule(ValidationRule):
    """Check for injection attempts."""
    
    name: str = "injection"
    check_sql: bool = True
    check_nosql: bool = True
    check_command: bool = True
    check_ldap: bool = False
    check_xpath: bool = False
    check_header: bool = True
    
    def validate(self, value: Any, field_name: str = "") -> str:
        if not isinstance(value, str):
            value = str(value)
        
        if self.check_sql:
            self._check_patterns(value, InjectionPatterns.SQL_INJECTION, "SQL", field_name)
        
        if self.check_nosql:
            self._check_patterns(value, InjectionPatterns.NOSQL_INJECTION, "NoSQL", field_name)
        
        if self.check_command:
            self._check_patterns(value, InjectionPatterns.COMMAND_INJECTION, "Command", field_name)
        
        if self.check_ldap:
            self._check_patterns(value, InjectionPatterns.LDAP_INJECTION, "LDAP", field_name)
        
        if self.check_xpath:
            self._check_patterns(value, InjectionPatterns.XPATH_INJECTION, "XPath", field_name)
        
        if self.check_header:
            self._check_patterns(value, InjectionPatterns.HEADER_INJECTION, "Header", field_name)
        
        return value
    
    def _check_patterns(
        self,
        value: str,
        patterns: list[Pattern],
        injection_type: str,
        field_name: str,
    ) -> None:
        for pattern in patterns:
            if pattern.search(value):
                logger.warning(
                    "injection_attempt_detected",
                    type=injection_type,
                    field=field_name,
                    pattern=pattern.pattern[:50],
                )
                raise InjectionAttemptError(
                    f"Potential {injection_type} injection detected",
                    injection_type=injection_type,
                    field=field_name,
                )


@dataclass  
class AllowlistRule(ValidationRule):
    """Validate value is in allowlist."""
    
    name: str = "allowlist"
    allowed_values: set[str] = field(default_factory=set)
    case_sensitive: bool = True
    
    def validate(self, value: Any, field_name: str = "") -> str:
        if not isinstance(value, str):
            value = str(value)
        
        check_value = value if self.case_sensitive else value.lower()
        check_against = self.allowed_values if self.case_sensitive else {v.lower() for v in self.allowed_values}
        
        if check_value not in check_against:
            raise ValidationError(
                f"Value not in allowed list",
                field=field_name,
            )
        
        return value


# =============================================================================
# Field Types
# =============================================================================

@dataclass
class FieldValidator:
    """Base field validator with composable rules."""
    
    rules: list[ValidationRule] = field(default_factory=list)
    required: bool = True
    default: Any = None
    sanitize: bool = True
    
    def validate(self, value: Any, field_name: str = "") -> Any:
        """Validate a value through all rules."""
        # Handle None/empty
        if value is None or (isinstance(value, str) and not value.strip()):
            if self.required:
                raise ValidationError(f"Field is required", field=field_name)
            return self.default
        
        # Sanitize first if enabled
        if self.sanitize and isinstance(value, str):
            value = InputSanitizer.normalize_unicode(value)
        
        # Apply all rules
        for rule in self.rules:
            value = rule.validate(value, field_name)
        
        return value


class IdentifierField(FieldValidator):
    """Validator for identifiers (IDs, slugs, etc.)."""
    
    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 128,
        allow_uuid: bool = True,
        required: bool = True,
    ):
        # UUID pattern or alphanumeric with hyphens/underscores
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$'
        if allow_uuid:
            pattern = r'^([a-zA-Z0-9][a-zA-Z0-9_-]*|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$'
        
        super().__init__(
            rules=[
                LengthRule(min_length=min_length, max_length=max_length),
                PatternRule(
                    pattern=pattern,
                    message="Invalid identifier format",
                ),
                InjectionRule(check_sql=True, check_command=True),
            ],
            required=required,
        )


class EmailField(FieldValidator):
    """Validator for email addresses."""
    
    def __init__(self, required: bool = True):
        super().__init__(
            rules=[
                LengthRule(min_length=5, max_length=254),
                PatternRule(
                    pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
                    message="Invalid email format",
                ),
                InjectionRule(check_header=True),
            ],
            required=required,
        )


class URLField(FieldValidator):
    """Validator for URLs."""
    
    def __init__(
        self,
        allowed_schemes: set[str] = None,
        required: bool = True,
    ):
        self.allowed_schemes = allowed_schemes or {"http", "https"}
        super().__init__(
            rules=[
                LengthRule(max_length=2048),
                PatternRule(
                    pattern=r'^https?://[^\s<>\"{}|\\^`\[\]]+$',
                    message="Invalid URL format",
                ),
            ],
            required=required,
        )
    
    def validate(self, value: Any, field_name: str = "") -> Any:
        value = super().validate(value, field_name)
        if value:
            # Additional scheme check
            from urllib.parse import urlparse
            parsed = urlparse(value)
            if parsed.scheme not in self.allowed_schemes:
                raise ValidationError(
                    f"URL scheme not allowed: {parsed.scheme}",
                    field=field_name,
                )
        return value


class TextContentField(FieldValidator):
    """Validator for free-form text content."""
    
    def __init__(
        self,
        max_length: int = 10000,
        allow_html: bool = False,
        required: bool = True,
    ):
        self.allow_html = allow_html
        super().__init__(
            rules=[
                LengthRule(max_length=max_length),
                InjectionRule(
                    check_sql=True,
                    check_command=False,  # Handled in validate() after HTML stripping
                    check_header=True,
                ),
            ],
            required=required,
        )
    
    def validate(self, value: Any, field_name: str = "") -> Any:
        # Handle None/empty first
        if value is None or (isinstance(value, str) and not value.strip()):
            if self.required:
                raise ValidationError(f"Field is required", field=field_name)
            return self.default
        
        # Strip HTML first if not allowed (before injection check)
        if isinstance(value, str) and not self.allow_html:
            value = InputSanitizer.strip_html(value)
        
        # Run parent validation (length, SQL injection, header injection)
        value = super().validate(value, field_name)
        
        # Check command injection only on non-HTML content
        if value and not self.allow_html:
            rule = InjectionRule(
                check_sql=False,
                check_nosql=False,
                check_command=True,
                check_header=False,
            )
            rule.validate(value, field_name)
        
        return value


class IntegerField(FieldValidator):
    """Validator for integer values."""
    
    def __init__(
        self,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        required: bool = True,
    ):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(rules=[], required=required)
    
    def validate(self, value: Any, field_name: str = "") -> Optional[int]:
        if value is None or (isinstance(value, str) and not value.strip()):
            if self.required:
                raise ValidationError(f"Field is required", field=field_name)
            return self.default
        
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(
                "Value must be an integer",
                field=field_name,
            )
        
        if self.min_value is not None and int_value < self.min_value:
            raise ValidationError(
                f"Value must be at least {self.min_value}",
                field=field_name,
            )
        
        if self.max_value is not None and int_value > self.max_value:
            raise ValidationError(
                f"Value must be at most {self.max_value}",
                field=field_name,
            )
        
        return int_value


class EnumField(FieldValidator):
    """Validator for enum values."""
    
    def __init__(
        self,
        allowed_values: set[str],
        case_sensitive: bool = False,
        required: bool = True,
    ):
        super().__init__(
            rules=[
                AllowlistRule(
                    allowed_values=allowed_values,
                    case_sensitive=case_sensitive,
                ),
            ],
            required=required,
        )


# =============================================================================
# Input Validator Class
# =============================================================================

class InputValidator:
    """Main input validator with common validation methods."""
    
    def __init__(self, strict_mode: bool = True):
        """Initialize validator.
        
        Args:
            strict_mode: If True, log and raise on all potential injections
        """
        self._strict = strict_mode
        self._id_validator = IdentifierField()
        self._email_validator = EmailField()
        self._url_validator = URLField()
        self._injection_rule = InjectionRule()
    
    def validate_identifier(self, value: str, field_name: str = "id") -> str:
        """Validate an identifier (ID, slug, etc.)."""
        return self._id_validator.validate(value, field_name)
    
    def validate_email(self, value: str, field_name: str = "email") -> str:
        """Validate an email address."""
        return self._email_validator.validate(value, field_name)
    
    def validate_url(self, value: str, field_name: str = "url") -> str:
        """Validate a URL."""
        return self._url_validator.validate(value, field_name)
    
    def check_injection(
        self,
        value: str,
        field_name: str = "",
        check_sql: bool = True,
        check_nosql: bool = True,
        check_command: bool = True,
    ) -> str:
        """Check for injection attempts."""
        rule = InjectionRule(
            check_sql=check_sql,
            check_nosql=check_nosql,
            check_command=check_command,
        )
        return rule.validate(value, field_name)
    
    def sanitize_for_sql(self, value: str) -> str:
        """Sanitize a value for safe SQL usage."""
        return InputSanitizer.escape_sql(value)
    
    def sanitize_for_shell(self, value: str) -> str:
        """Sanitize a value for safe shell usage."""
        return InputSanitizer.strip_shell_chars(value)
    
    def sanitize_for_html(self, value: str) -> str:
        """Sanitize a value for safe HTML output."""
        return InputSanitizer.strip_html(value)
    
    def validate_dict(
        self,
        data: dict[str, Any],
        schema: dict[str, FieldValidator],
    ) -> dict[str, Any]:
        """Validate a dictionary against a schema.
        
        Args:
            data: Input data
            schema: Dict of field names to validators
            
        Returns:
            Validated data
        """
        errors: list[ValidationError] = []
        result: dict[str, Any] = {}
        
        for field_name, validator in schema.items():
            try:
                value = data.get(field_name)
                result[field_name] = validator.validate(value, field_name)
            except ValidationError as e:
                errors.append(e)
        
        if errors:
            # Combine errors
            messages = [f"{e.field}: {e.message}" for e in errors]
            raise ValidationError(
                "; ".join(messages),
                code="MULTIPLE_VALIDATION_ERRORS",
            )
        
        return result


# =============================================================================
# Decorator for Function Validation
# =============================================================================

F = TypeVar('F', bound=Callable)


def validate_input(**field_validators: FieldValidator) -> Callable[[F], F]:
    """Decorator to validate function input parameters.
    
    Usage:
        @validate_input(user_id=IdentifierField(), email=EmailField())
        async def create_user(user_id: str, email: str):
            ...
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            validated_kwargs = _validate_kwargs(kwargs, field_validators)
            return await func(*args, **validated_kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            validated_kwargs = _validate_kwargs(kwargs, field_validators)
            return func(*args, **validated_kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore
    
    return decorator


def _validate_kwargs(
    kwargs: dict[str, Any],
    validators: dict[str, FieldValidator],
) -> dict[str, Any]:
    """Validate keyword arguments."""
    result = dict(kwargs)
    
    for param_name, validator in validators.items():
        if param_name in kwargs:
            result[param_name] = validator.validate(kwargs[param_name], param_name)
    
    return result


# =============================================================================
# Pydantic Integration
# =============================================================================

class ValidatedModel(BaseModel):
    """Base model with automatic injection checking."""
    
    @field_validator('*', mode='before')
    @classmethod
    def check_injection(cls, v, info):
        """Check all string fields for injection."""
        if isinstance(v, str):
            rule = InjectionRule()
            try:
                rule.validate(v, info.field_name if info else "")
            except InjectionAttemptError:
                raise ValueError(f"Invalid input for field {info.field_name if info else 'unknown'}")
        return v
