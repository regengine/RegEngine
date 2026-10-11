"""Compatibility helpers for shared input validation and sanitization.

This module provides a small validation toolkit used by the shared security
tests. The surface is intentionally lightweight and framework-agnostic so
services can reuse the same defensive checks for identifiers, emails, URLs,
plain text, and generic injection detection.
"""

from __future__ import annotations

import inspect
import re
import unicodedata
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse
from uuid import UUID


@dataclass
class ValidationError(Exception):
    """Raised when a value fails a validation rule."""

    message: str
    field: str | None = None
    value: Any = None
    code: str = "VALIDATION_ERROR"

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "error": self.code,
            "message": self.message,
            "field": self.field,
        }
        if self.value is not None:
            payload["value"] = self.value
        return payload


class InjectionAttemptError(ValidationError):
    """Raised when input appears to contain an injection payload."""

    def __init__(
        self,
        message: str,
        *,
        injection_type: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            field=field,
            value=value,
            code="INJECTION_ATTEMPT",
        )
        self.injection_type = injection_type


class InjectionPatterns:
    """Common regex signatures for suspicious user-controlled input."""

    SQL_INJECTION = [
        re.compile(r"(?i)\bunion\b\s+\bselect\b"),
        re.compile(r"(?i)\bdrop\b\s+\btable\b"),
        re.compile(r"(?i)\bdelete\b\s+\bfrom\b"),
        re.compile(r"(?i)\bor\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+"),
        re.compile(r"(?i)\bor\b\s+['\"]?[a-z0-9_]+['\"]?\s*=\s*['\"]?[a-z0-9_]+"),
        re.compile(r"(?i)--"),
        re.compile(r"(?i);\s*(select|insert|update|delete|drop)\b"),
    ]
    NOSQL_INJECTION = [
        re.compile(r'"\s*\$(gt|gte|lt|lte|ne|where|regex|or|and)\b', re.IGNORECASE),
        re.compile(r"\$(gt|gte|lt|lte|ne|where|regex|or|and)\b", re.IGNORECASE),
    ]
    COMMAND_INJECTION = [
        re.compile(r"[;&|]{1,2}"),
        re.compile(r"`[^`]*`"),
        re.compile(r"\$\([^)]*\)"),
        re.compile(r"(?i)\b(rm|wget|curl|cat|bash|sh|powershell|cmd)\b"),
    ]
    HEADER_INJECTION = [
        re.compile(r"[\r\n]"),
    ]


class InputSanitizer:
    """Utility sanitizers for untrusted user input."""

    _HTML_RE = re.compile(r"<[^>]+>")
    _SQL_DANGEROUS_RE = re.compile(r"--|[;]")
    _SHELL_DANGEROUS_RE = re.compile(r"[`$|;&]")

    @staticmethod
    def strip_sql_chars(value: str) -> str:
        return InputSanitizer._SQL_DANGEROUS_RE.sub("", value)

    @staticmethod
    def strip_shell_chars(value: str) -> str:
        return InputSanitizer._SHELL_DANGEROUS_RE.sub("", value)

    @staticmethod
    def strip_html(value: str) -> str:
        return InputSanitizer._HTML_RE.sub("", value)

    @staticmethod
    def escape_sql(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def normalize_unicode(value: str) -> str:
        return unicodedata.normalize("NFKC", value)

    @staticmethod
    def to_alphanumeric(value: str, *, allowed: str = "") -> str:
        allowed_chars = set(allowed)
        return "".join(char for char in value if char.isalnum() or char in allowed_chars)


class LengthRule:
    """Validate text length boundaries."""

    def __init__(self, *, min_length: int = 0, max_length: int | None = None) -> None:
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, value: str, field: str) -> str:
        if len(value) < self.min_length:
            raise ValidationError(
                message=f"{field} is too short",
                field=field,
                value=value,
                code="TOO_SHORT",
            )
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(
                message=f"{field} is too long",
                field=field,
                value=value,
                code="TOO_LONG",
            )
        return value


class PatternRule:
    """Validate a string against a regex pattern."""

    def __init__(self, *, pattern: str, message: str | None = None) -> None:
        self.pattern = re.compile(pattern)
        self.message = message or "Invalid format"

    def validate(self, value: str, field: str) -> str:
        if not self.pattern.fullmatch(value):
            raise ValidationError(
                message=self.message,
                field=field,
                value=value,
                code="INVALID_PATTERN",
            )
        return value


class InjectionRule:
    """Reject suspicious strings that resemble injection payloads."""

    def __init__(
        self,
        *,
        check_sql: bool = True,
        check_nosql: bool = True,
        check_command: bool = True,
        check_header: bool = True,
    ) -> None:
        self.check_sql = check_sql
        self.check_nosql = check_nosql
        self.check_command = check_command
        self.check_header = check_header

    # SQL comment sequences used to glue keywords past whitespace checks.
    _SQL_COMMENT_RE = re.compile(r"/\*.*?\*/")

    def validate(self, value: str, field: str) -> str:
        normalized = InputSanitizer.normalize_unicode(str(value))
        # Unmask comment-obfuscated keywords (e.g. UNION/**/SELECT) for the
        # SQL checks only; the returned value is untouched.
        sql_probe = self._SQL_COMMENT_RE.sub(" ", normalized)
        checks: list[tuple[str, bool, Iterable[re.Pattern[str]]]] = [
            ("SQL", self.check_sql, InjectionPatterns.SQL_INJECTION),
            ("NoSQL", self.check_nosql, InjectionPatterns.NOSQL_INJECTION),
            ("Command", self.check_command, InjectionPatterns.COMMAND_INJECTION),
            ("Header", self.check_header, InjectionPatterns.HEADER_INJECTION),
        ]
        for injection_type, enabled, patterns in checks:
            if not enabled:
                continue
            probe = sql_probe if injection_type == "SQL" else normalized
            for pattern in patterns:
                if pattern.search(probe):
                    raise InjectionAttemptError(
                        f"{injection_type} injection detected",
                        injection_type=injection_type,
                        field=field,
                        value=value,
                    )
        return value


class AllowlistRule:
    """Accept only explicitly approved values."""

    def __init__(
        self,
        *,
        allowed_values: set[str] | frozenset[str],
        case_sensitive: bool = True,
    ) -> None:
        self.case_sensitive = case_sensitive
        self.allowed_values = set(allowed_values)
        self._normalized_allowed = (
            self.allowed_values if case_sensitive else {value.lower() for value in self.allowed_values}
        )

    def validate(self, value: str, field: str) -> str:
        candidate = value if self.case_sensitive else value.lower()
        if candidate not in self._normalized_allowed:
            raise ValidationError(
                message=f"{field} is not in allowed values",
                field=field,
                value=value,
                code="VALUE_NOT_ALLOWED",
            )
        return value


class IdentifierField:
    """Validate slugs, ids, and UUID-like identifiers."""

    _IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(
        self,
        *,
        allow_uuid: bool = False,
        min_length: int = 1,
        max_length: int = 255,
    ) -> None:
        self.allow_uuid = allow_uuid
        self.length_rule = LengthRule(min_length=min_length, max_length=max_length)
        self.injection_rule = InjectionRule()

    def validate(self, value: str, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(
                message=f"{field} must be a string",
                field=field,
                value=value,
                code="INVALID_TYPE",
            )
        normalized = InputSanitizer.normalize_unicode(value)
        self.length_rule.validate(normalized, field)
        self.injection_rule.validate(normalized, field)
        if self.allow_uuid:
            try:
                UUID(normalized)
                return normalized
            except ValueError:
                pass
        if not self._IDENTIFIER_RE.fullmatch(normalized):
            raise ValidationError(
                message=f"{field} contains invalid characters",
                field=field,
                value=value,
                code="INVALID_IDENTIFIER",
            )
        return normalized


class EmailField:
    """Validate RFC-lite email address syntax."""

    _EMAIL_RE = re.compile(
        r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
    )

    def validate(self, value: str, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(
                message=f"{field} must be a string",
                field=field,
                value=value,
                code="INVALID_TYPE",
            )
        normalized = InputSanitizer.normalize_unicode(value).strip()
        if not self._EMAIL_RE.fullmatch(normalized):
            raise ValidationError(
                message=f"{field} must be a valid email address",
                field=field,
                value=value,
                code="INVALID_EMAIL",
            )
        return normalized


class URLField:
    """Validate http(s) URLs and optionally restrict schemes."""

    def __init__(self, *, allowed_schemes: set[str] | None = None) -> None:
        self.allowed_schemes = allowed_schemes or {"http", "https"}

    def validate(self, value: str, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(
                message=f"{field} must be a string",
                field=field,
                value=value,
                code="INVALID_TYPE",
            )
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError(
                message=f"{field} must be a valid URL",
                field=field,
                value=value,
                code="INVALID_URL",
            )
        if parsed.scheme.lower() not in {scheme.lower() for scheme in self.allowed_schemes}:
            raise ValidationError(
                message=f"{field} uses an unsupported scheme",
                field=field,
                value=value,
                code="INVALID_URL_SCHEME",
            )
        return value


class TextContentField:
    """Validate and optionally sanitize general text content."""

    def __init__(
        self,
        *,
        allow_html: bool = False,
        min_length: int = 0,
        max_length: int | None = None,
    ) -> None:
        self.allow_html = allow_html
        self.length_rule = LengthRule(min_length=min_length, max_length=max_length)

    def validate(self, value: str, field: str) -> str:
        if not isinstance(value, str):
            raise ValidationError(
                message=f"{field} must be a string",
                field=field,
                value=value,
                code="INVALID_TYPE",
            )
        normalized = InputSanitizer.normalize_unicode(value)
        if not self.allow_html:
            normalized = InputSanitizer.strip_html(normalized)
        self.length_rule.validate(normalized, field)
        return normalized


class IntegerField:
    """Validate integer input with optional bounds."""

    def __init__(self, *, min_value: int | None = None, max_value: int | None = None) -> None:
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, value: Any, field: str) -> int:
        try:
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message=f"{field} must be an integer",
                field=field,
                value=value,
                code="INVALID_INTEGER",
            ) from exc
        if self.min_value is not None and parsed < self.min_value:
            raise ValidationError(
                message=f"{field} must be at least {self.min_value}",
                field=field,
                value=value,
                code="INTEGER_TOO_SMALL",
            )
        if self.max_value is not None and parsed > self.max_value:
            raise ValidationError(
                message=f"{field} must be at most {self.max_value}",
                field=field,
                value=value,
                code="INTEGER_TOO_LARGE",
            )
        return parsed


class EnumField(AllowlistRule):
    """Alias for allowlist-style enum validation."""


class InputValidator:
    """High-level helper methods built on top of field validators."""

    def __init__(self) -> None:
        self._injection_rule = InjectionRule()

    def validate_identifier(self, value: str, *, field_name: str = "identifier") -> str:
        return IdentifierField().validate(value, field_name)

    def validate_email(self, value: str, *, field_name: str = "email") -> str:
        return EmailField().validate(value, field_name)

    def validate_url(self, value: str, *, field_name: str = "url") -> str:
        return URLField().validate(value, field_name)

    def check_injection(self, value: str, *, field_name: str = "input") -> str:
        return self._injection_rule.validate(value, field_name)

    def sanitize_for_sql(self, value: str) -> str:
        return InputSanitizer.escape_sql(value)

    def validate_dict(
        self,
        data: Mapping[str, Any],
        schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        validated: dict[str, Any] = {}
        errors: list[str] = []
        for field_name, validator in schema.items():
            try:
                validated[field_name] = validator.validate(data.get(field_name), field_name)
            except ValidationError as exc:
                errors.append(f"{field_name}: {exc.message}")
        if errors:
            raise ValidationError(
                message="; ".join(errors),
                field="schema",
                value=dict(data),
                code="MULTIPLE_VALIDATION_ERRORS",
            )
        return validated


def validate_input(**validators: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that validates selected function arguments before invocation."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)

        def _validate_args(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
            bound = signature.bind_partial(*args, **kwargs)
            for field_name, validator in validators.items():
                if field_name in bound.arguments:
                    bound.arguments[field_name] = validator.validate(
                        bound.arguments[field_name],
                        field_name,
                    )
            # Rebuild the call from the bound arguments so validated and
            # sanitized values actually reach the wrapped function instead
            # of being silently discarded.
            return bound.args, bound.kwargs

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                validated_args, validated_kwargs = _validate_args(*args, **kwargs)
                return await func(*validated_args, **validated_kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            validated_args, validated_kwargs = _validate_args(*args, **kwargs)
            return func(*validated_args, **validated_kwargs)

        return sync_wrapper

    return decorator


__all__ = [
    "AllowlistRule",
    "EmailField",
    "EnumField",
    "IdentifierField",
    "InjectionAttemptError",
    "InjectionPatterns",
    "InjectionRule",
    "InputSanitizer",
    "InputValidator",
    "IntegerField",
    "LengthRule",
    "PatternRule",
    "TextContentField",
    "URLField",
    "ValidationError",
    "validate_input",
]
