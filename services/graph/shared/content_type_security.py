"""
SEC-015: Content-Type Validation and Request Body Security.

This module provides utilities for validating Content-Type headers,
request body formats, and preventing content-type attacks.
"""

import json
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class ContentTypeError(Exception):
    """Base exception for content-type issues."""
    pass


class InvalidContentTypeError(ContentTypeError):
    """Raised when Content-Type is invalid or not allowed."""
    
    def __init__(
        self,
        message: str,
        provided_type: Optional[str] = None,
        expected_types: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.provided_type = provided_type
        self.expected_types = expected_types or []


class ContentSizeLimitError(ContentTypeError):
    """Raised when content exceeds size limits."""
    
    def __init__(self, message: str, size: int, limit: int):
        super().__init__(message)
        self.size = size
        self.limit = limit


class MalformedContentError(ContentTypeError):
    """Raised when content is malformed for its declared type."""
    pass


class ContentSniffingError(ContentTypeError):
    """Raised when content doesn't match its declared type (MIME sniffing)."""
    pass


# =============================================================================
# Content Type Constants
# =============================================================================

class CommonContentTypes:
    """Common Content-Type values."""
    
    # Application types
    JSON = "application/json"
    XML = "application/xml"
    FORM_URLENCODED = "application/x-www-form-urlencoded"
    MULTIPART_FORM = "multipart/form-data"
    OCTET_STREAM = "application/octet-stream"
    PDF = "application/pdf"
    ZIP = "application/zip"
    JAVASCRIPT = "application/javascript"
    
    # Text types
    TEXT_PLAIN = "text/plain"
    TEXT_HTML = "text/html"
    TEXT_XML = "text/xml"
    TEXT_CSS = "text/css"
    TEXT_CSV = "text/csv"
    
    # Image types
    IMAGE_JPEG = "image/jpeg"
    IMAGE_PNG = "image/png"
    IMAGE_GIF = "image/gif"
    IMAGE_WEBP = "image/webp"
    IMAGE_SVG = "image/svg+xml"
    
    # API common
    API_TYPES = frozenset({
        JSON,
        XML,
        FORM_URLENCODED,
        MULTIPART_FORM,
        TEXT_PLAIN,
    })
    
    # Safe types for uploads
    SAFE_UPLOAD_TYPES = frozenset({
        IMAGE_JPEG,
        IMAGE_PNG,
        IMAGE_GIF,
        IMAGE_WEBP,
        PDF,
        TEXT_PLAIN,
        TEXT_CSV,
    })
    
    # Dangerous types that should be blocked
    DANGEROUS_TYPES = frozenset({
        JAVASCRIPT,
        "text/javascript",
        "application/x-javascript",
        "text/x-script",
        "application/x-executable",
        "application/x-msdos-program",
        "application/x-msdownload",
        "application/bat",
        "application/x-bat",
        "application/x-sh",
        "application/x-csh",
    })


# =============================================================================
# Content-Type Parser
# =============================================================================

@dataclass
class ParsedContentType:
    """Parsed Content-Type header."""
    
    media_type: str  # e.g., "application/json"
    main_type: str  # e.g., "application"
    sub_type: str  # e.g., "json"
    charset: Optional[str] = None
    boundary: Optional[str] = None
    parameters: Dict[str, str] = field(default_factory=dict)
    
    def matches(self, other: str) -> bool:
        """Check if this content type matches another.
        
        Supports wildcards like "text/*" or "*/*".
        """
        # Handle wildcards without full parsing
        if other == "*/*":
            return True
        
        if "/" not in other:
            return False
        
        other_main, other_sub = other.split("/", 1)
        other_main = other_main.lower()
        other_sub = other_sub.lower()
        
        # Check main type
        if other_main != "*" and self.main_type != other_main:
            return False
        
        # Check sub type
        if other_sub != "*" and self.sub_type != other_sub:
            return False
        
        return True
    
    def __str__(self) -> str:
        """Return the media type string."""
        return self.media_type


class ContentTypeParser:
    """Parse Content-Type headers safely."""
    
    # RFC 7231 compliant Content-Type pattern
    CONTENT_TYPE_PATTERN = re.compile(
        r'^(?P<type>[a-zA-Z0-9!#$&\-^_+.]+)'
        r'/(?P<subtype>[a-zA-Z0-9!#$&\-^_+.]+)'
        r'(?:\s*;\s*(?P<params>.*))?$'
    )
    
    # Parameter pattern
    PARAM_PATTERN = re.compile(
        r'(?P<key>[a-zA-Z0-9!#$&\-^_+.]+)'
        r'\s*=\s*'
        r'(?:"(?P<quoted>[^"]*)"|(?P<value>[^\s;]+))'
    )
    
    @classmethod
    def parse(cls, content_type: str) -> Optional[ParsedContentType]:
        """Parse a Content-Type header.
        
        Args:
            content_type: Raw Content-Type header value
            
        Returns:
            ParsedContentType or None if invalid
        """
        if not content_type:
            return None
        
        # Normalize whitespace
        content_type = content_type.strip()
        
        # Parse main pattern
        match = cls.CONTENT_TYPE_PATTERN.match(content_type)
        if not match:
            logger.warning("Invalid content-type format: %s", content_type[:100])
            return None
        
        main_type = match.group('type').lower()
        sub_type = match.group('subtype').lower()
        params_str = match.group('params') or ""
        
        # Parse parameters
        parameters = {}
        charset = None
        boundary = None
        
        for param_match in cls.PARAM_PATTERN.finditer(params_str):
            key = param_match.group('key').lower()
            value = param_match.group('quoted') or param_match.group('value')
            
            parameters[key] = value
            
            if key == 'charset':
                charset = value
            elif key == 'boundary':
                boundary = value
        
        return ParsedContentType(
            media_type=f"{main_type}/{sub_type}",
            main_type=main_type,
            sub_type=sub_type,
            charset=charset,
            boundary=boundary,
            parameters=parameters,
        )
    
    @classmethod
    def normalize(cls, content_type: str) -> str:
        """Normalize a Content-Type to its base media type.
        
        Args:
            content_type: Raw Content-Type header value
            
        Returns:
            Normalized media type (lowercase, no params)
        """
        parsed = cls.parse(content_type)
        if not parsed:
            return ""
        return parsed.media_type


# =============================================================================
# Content-Type Validator
# =============================================================================

class ContentTypeValidator:
    """Validate Content-Type headers for requests."""
    
    def __init__(
        self,
        allowed_types: Optional[Set[str]] = None,
        blocked_types: Optional[Set[str]] = None,
        require_charset: bool = False,
        default_charset: str = "utf-8",
    ):
        """Initialize validator.
        
        Args:
            allowed_types: Set of allowed content types (whitelist)
            blocked_types: Set of blocked content types (blacklist)
            require_charset: Whether to require charset parameter
            default_charset: Default charset if not specified
        """
        self._allowed_types = allowed_types
        self._blocked_types = blocked_types or CommonContentTypes.DANGEROUS_TYPES
        self._require_charset = require_charset
        self._default_charset = default_charset
    
    def validate(
        self,
        content_type: str,
        expected_types: Optional[List[str]] = None,
    ) -> ParsedContentType:
        """Validate a Content-Type header.
        
        Args:
            content_type: Raw Content-Type header value
            expected_types: List of expected types (if specific)
            
        Returns:
            Parsed and validated content type
            
        Raises:
            InvalidContentTypeError: If content type is invalid
        """
        # Parse the content type
        parsed = ContentTypeParser.parse(content_type)
        
        if not parsed:
            raise InvalidContentTypeError(
                "Invalid Content-Type format",
                provided_type=content_type,
            )
        
        # Check against blocked types
        if parsed.media_type in self._blocked_types:
            logger.warning(
                "Blocked content-type: %s",
                parsed.media_type,
            )
            raise InvalidContentTypeError(
                f"Content-Type not allowed: {parsed.media_type}",
                provided_type=parsed.media_type,
            )
        
        # Check against allowed types (whitelist)
        if self._allowed_types is not None:
            if parsed.media_type not in self._allowed_types:
                raise InvalidContentTypeError(
                    f"Content-Type not in allowed list: {parsed.media_type}",
                    provided_type=parsed.media_type,
                    expected_types=list(self._allowed_types),
                )
        
        # Check against expected types for this endpoint
        if expected_types:
            if not any(parsed.matches(et) for et in expected_types):
                raise InvalidContentTypeError(
                    f"Unexpected Content-Type: {parsed.media_type}",
                    provided_type=parsed.media_type,
                    expected_types=expected_types,
                )
        
        # Check charset requirement
        if self._require_charset and not parsed.charset:
            # Add default charset
            parsed = ParsedContentType(
                media_type=parsed.media_type,
                main_type=parsed.main_type,
                sub_type=parsed.sub_type,
                charset=self._default_charset,
                boundary=parsed.boundary,
                parameters={**parsed.parameters, 'charset': self._default_charset},
            )
        
        return parsed
    
    def is_json(self, content_type: str) -> bool:
        """Check if content type is JSON."""
        parsed = ContentTypeParser.parse(content_type)
        if not parsed:
            return False
        return parsed.media_type == CommonContentTypes.JSON
    
    def is_form(self, content_type: str) -> bool:
        """Check if content type is form data."""
        parsed = ContentTypeParser.parse(content_type)
        if not parsed:
            return False
        return parsed.media_type in {
            CommonContentTypes.FORM_URLENCODED,
            CommonContentTypes.MULTIPART_FORM,
        }
    
    def is_multipart(self, content_type: str) -> bool:
        """Check if content type is multipart."""
        parsed = ContentTypeParser.parse(content_type)
        if not parsed:
            return False
        return parsed.main_type == "multipart"
    
    def get_boundary(self, content_type: str) -> Optional[str]:
        """Get the boundary parameter from multipart content type."""
        parsed = ContentTypeParser.parse(content_type)
        if not parsed:
            return None
        return parsed.boundary


# =============================================================================
# Content Body Validator
# =============================================================================

class ContentBodyValidator:
    """Validate request body content."""
    
    DEFAULT_MAX_SIZE = 10 * 1024 * 1024  # 10MB
    DEFAULT_MAX_JSON_DEPTH = 20
    DEFAULT_MAX_JSON_KEYS = 1000
    
    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        max_json_depth: int = DEFAULT_MAX_JSON_DEPTH,
        max_json_keys: int = DEFAULT_MAX_JSON_KEYS,
    ):
        """Initialize body validator.
        
        Args:
            max_size: Maximum body size in bytes
            max_json_depth: Maximum JSON nesting depth
            max_json_keys: Maximum number of JSON keys
        """
        self._max_size = max_size
        self._max_json_depth = max_json_depth
        self._max_json_keys = max_json_keys
    
    def validate_size(self, content: bytes, content_type: str = "") -> None:
        """Validate content size.
        
        Args:
            content: Request body content
            content_type: Content type for context
            
        Raises:
            ContentSizeLimitError: If content exceeds limit
        """
        if len(content) > self._max_size:
            raise ContentSizeLimitError(
                f"Content exceeds maximum size of {self._max_size} bytes",
                size=len(content),
                limit=self._max_size,
            )
    
    def validate_json(self, content: Union[str, bytes]) -> Any:
        """Validate and parse JSON content.
        
        Args:
            content: JSON content as string or bytes
            
        Returns:
            Parsed JSON data
            
        Raises:
            MalformedContentError: If JSON is malformed
        """
        if isinstance(content, bytes):
            try:
                content = content.decode('utf-8')
            except UnicodeDecodeError as e:
                raise MalformedContentError(f"Invalid UTF-8 encoding: {e}")
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise MalformedContentError(f"Invalid JSON: {e}")
        
        # Check depth and key count
        depth, keys = self._analyze_json(data)
        
        if depth > self._max_json_depth:
            raise MalformedContentError(
                f"JSON exceeds maximum nesting depth of {self._max_json_depth}"
            )
        
        if keys > self._max_json_keys:
            raise MalformedContentError(
                f"JSON exceeds maximum key count of {self._max_json_keys}"
            )
        
        return data
    
    def _analyze_json(
        self,
        data: Any,
        current_depth: int = 1,
    ) -> Tuple[int, int]:
        """Analyze JSON structure for depth and key count.
        
        Args:
            data: JSON data to analyze
            current_depth: Current nesting depth
            
        Returns:
            Tuple of (max_depth, total_keys)
        """
        max_depth = current_depth
        total_keys = 0
        
        if isinstance(data, dict):
            total_keys += len(data)
            for value in data.values():
                child_depth, child_keys = self._analyze_json(
                    value,
                    current_depth + 1,
                )
                max_depth = max(max_depth, child_depth)
                total_keys += child_keys
        
        elif isinstance(data, list):
            for item in data:
                child_depth, child_keys = self._analyze_json(
                    item,
                    current_depth + 1,
                )
                max_depth = max(max_depth, child_depth)
                total_keys += child_keys
        
        return max_depth, total_keys
    
    def validate_xml(self, content: Union[str, bytes]) -> None:
        """Validate XML content (basic structure check).
        
        Args:
            content: XML content as string or bytes
            
        Raises:
            MalformedContentError: If XML is malformed
        """
        if isinstance(content, bytes):
            try:
                content = content.decode('utf-8')
            except UnicodeDecodeError as e:
                raise MalformedContentError(f"Invalid UTF-8 encoding: {e}")
        
        # Basic XML structure check (not full parsing for security)
        content = content.strip()
        
        if not content:
            raise MalformedContentError("Empty XML content")
        
        # Check for XML declaration or root element
        if not (content.startswith('<?xml') or content.startswith('<')):
            raise MalformedContentError("Invalid XML: must start with < or <?xml")
        
        # Check for DTD/entity attacks (XXE prevention)
        dangerous_patterns = [
            '<!DOCTYPE',
            '<!ENTITY',
            'SYSTEM',
            'file://',
            'expect://',
            'php://',
        ]
        
        content_upper = content.upper()
        for pattern in dangerous_patterns:
            if pattern.upper() in content_upper:
                logger.warning(
                    "Potential XXE attack detected: %s",
                    pattern,
                )
                raise MalformedContentError(
                    f"Potentially dangerous XML content: {pattern}"
                )


# =============================================================================
# MIME Type Sniffing Detection
# =============================================================================

class MimeSniffingDetector:
    """Detect MIME type sniffing attacks."""
    
    # Magic bytes for common file types
    MAGIC_BYTES = {
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'\xff\xd8\xff': 'image/jpeg',
        b'GIF87a': 'image/gif',
        b'GIF89a': 'image/gif',
        b'%PDF': 'application/pdf',
        b'PK\x03\x04': 'application/zip',
        b'\x1f\x8b': 'application/gzip',
    }
    
    # Text patterns that indicate HTML/JS (could execute)
    EXECUTABLE_PATTERNS = [
        b'<html',
        b'<script',
        b'javascript:',
        b'<iframe',
        b'<object',
        b'<embed',
    ]
    
    @classmethod
    def detect_type(cls, content: bytes) -> Optional[str]:
        """Detect the actual content type from magic bytes.
        
        Args:
            content: File content (at least first 100 bytes)
            
        Returns:
            Detected MIME type or None if unknown
        """
        if not content:
            return None
        
        # Check magic bytes
        for magic, mime_type in cls.MAGIC_BYTES.items():
            if content.startswith(magic):
                return mime_type
        
        # Check for text-based executable content
        content_lower = content[:1000].lower()
        for pattern in cls.EXECUTABLE_PATTERNS:
            if pattern in content_lower:
                return 'text/html'  # Could be executable
        
        return None
    
    @classmethod
    def validate_match(
        cls,
        content: bytes,
        declared_type: str,
        strict: bool = True,
    ) -> bool:
        """Validate that content matches its declared type.
        
        Args:
            content: File content
            declared_type: Declared Content-Type
            strict: Whether to enforce strict matching
            
        Returns:
            True if content matches declared type
            
        Raises:
            ContentSniffingError: If content doesn't match (strict mode)
        """
        detected = cls.detect_type(content)
        
        if detected is None:
            # Can't determine type, allow if not strict
            return not strict
        
        # Parse declared type
        parsed = ContentTypeParser.parse(declared_type)
        if not parsed:
            if strict:
                raise ContentSniffingError(
                    f"Invalid declared type: {declared_type}"
                )
            return False
        
        # Check for mismatch
        if detected != parsed.media_type:
            # Check if the declared type is a parent type
            detected_parsed = ContentTypeParser.parse(detected)
            if detected_parsed and detected_parsed.main_type == parsed.main_type:
                # Same main type (e.g., both image/*), allow
                return True
            
            if strict:
                raise ContentSniffingError(
                    f"Content type mismatch: declared {declared_type}, "
                    f"detected {detected}"
                )
            return False
        
        return True
    
    @classmethod
    def is_potentially_executable(cls, content: bytes) -> bool:
        """Check if content could be executable in a browser.
        
        Args:
            content: File content
            
        Returns:
            True if content could be executed
        """
        content_lower = content[:5000].lower()
        
        for pattern in cls.EXECUTABLE_PATTERNS:
            if pattern in content_lower:
                return True
        
        return False


# =============================================================================
# Content Validation Middleware Helpers
# =============================================================================

@dataclass
class ContentValidationConfig:
    """Configuration for content validation."""
    
    allowed_types: Optional[Set[str]] = None
    blocked_types: Optional[Set[str]] = None
    max_size: int = 10 * 1024 * 1024  # 10MB
    require_content_type: bool = True
    validate_json_structure: bool = True
    detect_mime_sniffing: bool = True
    

def create_api_validator(
    allowed_types: Optional[Set[str]] = None,
) -> ContentTypeValidator:
    """Create a validator for API endpoints.
    
    Args:
        allowed_types: Override allowed types
        
    Returns:
        Configured validator
    """
    return ContentTypeValidator(
        allowed_types=allowed_types or CommonContentTypes.API_TYPES,
        blocked_types=CommonContentTypes.DANGEROUS_TYPES,
        require_charset=False,
    )


def create_upload_validator(
    allowed_types: Optional[Set[str]] = None,
) -> ContentTypeValidator:
    """Create a validator for file upload endpoints.
    
    Args:
        allowed_types: Override allowed types
        
    Returns:
        Configured validator
    """
    return ContentTypeValidator(
        allowed_types=allowed_types or CommonContentTypes.SAFE_UPLOAD_TYPES,
        blocked_types=CommonContentTypes.DANGEROUS_TYPES,
        require_charset=False,
    )


# =============================================================================
# Security Headers for Content-Type
# =============================================================================

def get_content_type_security_headers() -> Dict[str, str]:
    """Get recommended security headers for content-type handling.
    
    Returns:
        Dict of header name to value
    """
    return {
        # Prevent MIME type sniffing
        "X-Content-Type-Options": "nosniff",
        
        # Prevent framing
        "X-Frame-Options": "DENY",
        
        # XSS protection (legacy, but still useful)
        "X-XSS-Protection": "1; mode=block",
    }


# =============================================================================
# Convenience Functions
# =============================================================================

def validate_json_request(
    content_type: str,
    body: Union[str, bytes],
    max_size: int = 10 * 1024 * 1024,
) -> Any:
    """Validate a JSON API request.
    
    Args:
        content_type: Request Content-Type header
        body: Request body
        max_size: Maximum body size
        
    Returns:
        Parsed JSON data
        
    Raises:
        InvalidContentTypeError: If content type is not JSON
        ContentSizeLimitError: If body exceeds size limit
        MalformedContentError: If JSON is malformed
    """
    # Validate content type
    validator = create_api_validator({CommonContentTypes.JSON})
    validator.validate(content_type, expected_types=[CommonContentTypes.JSON])
    
    # Validate body
    body_validator = ContentBodyValidator(max_size=max_size)
    
    if isinstance(body, str):
        body = body.encode('utf-8')
    
    body_validator.validate_size(body, content_type)
    
    return body_validator.validate_json(body)


def validate_form_request(
    content_type: str,
    body_size: int,
    max_size: int = 10 * 1024 * 1024,
) -> ParsedContentType:
    """Validate a form submission request.
    
    Args:
        content_type: Request Content-Type header
        body_size: Size of request body
        max_size: Maximum body size
        
    Returns:
        Parsed content type
        
    Raises:
        InvalidContentTypeError: If content type is not form
        ContentSizeLimitError: If body exceeds size limit
    """
    # Validate content type
    validator = create_api_validator({
        CommonContentTypes.FORM_URLENCODED,
        CommonContentTypes.MULTIPART_FORM,
    })
    
    parsed = validator.validate(content_type)
    
    # Validate size
    if body_size > max_size:
        raise ContentSizeLimitError(
            f"Request body exceeds maximum size of {max_size} bytes",
            size=body_size,
            limit=max_size,
        )
    
    return parsed


def validate_file_upload(
    content_type: str,
    content: bytes,
    allowed_types: Optional[Set[str]] = None,
    max_size: int = 10 * 1024 * 1024,
    strict_mime: bool = True,
) -> ParsedContentType:
    """Validate a file upload.
    
    Args:
        content_type: Declared Content-Type
        content: File content
        allowed_types: Set of allowed MIME types
        max_size: Maximum file size
        strict_mime: Whether to enforce strict MIME type checking
        
    Returns:
        Parsed and validated content type
        
    Raises:
        InvalidContentTypeError: If content type not allowed
        ContentSizeLimitError: If file exceeds size limit
        ContentSniffingError: If content doesn't match declared type
    """
    # Validate content type
    validator = create_upload_validator(allowed_types)
    parsed = validator.validate(content_type)
    
    # Validate size
    if len(content) > max_size:
        raise ContentSizeLimitError(
            f"File exceeds maximum size of {max_size} bytes",
            size=len(content),
            limit=max_size,
        )
    
    # Validate MIME type matches content
    MimeSniffingDetector.validate_match(content, content_type, strict=strict_mime)
    
    # Check for executable content
    if MimeSniffingDetector.is_potentially_executable(content):
        logger.warning(
            "Potentially executable content detected in upload: %s",
            content_type,
        )
        raise ContentSniffingError(
            "Upload contains potentially executable content"
        )
    
    return parsed
