"""
SEC-032: Exception Message Sanitization.

Provides sanitization of exception messages to prevent information disclosure:
- Pattern-based sensitive data detection
- Automatic redaction
- Safe message generation
- Custom sanitization rules
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern, Set, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class SensitiveDataType(str, Enum):
    """Types of sensitive data."""
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    SECRET = "secret"
    IP_ADDRESS = "ip_address"
    EMAIL = "email"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    FILE_PATH = "file_path"
    DATABASE_URL = "database_url"
    PHONE = "phone"
    STACK_TRACE = "stack_trace"
    INTERNAL_URL = "internal_url"


# =============================================================================
# Redaction Patterns
# =============================================================================

# Patterns for detecting sensitive data
SENSITIVE_PATTERNS: Dict[SensitiveDataType, List[Pattern]] = {
    SensitiveDataType.PASSWORD: [
        re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'pwd["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'passwd["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
    ],
    SensitiveDataType.API_KEY: [
        re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'apikey["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'\b(sk_live_[a-zA-Z0-9]+)\b'),
        re.compile(r'\b(pk_live_[a-zA-Z0-9]+)\b'),
        re.compile(r'\b(sk_test_[a-zA-Z0-9]+)\b'),
        re.compile(r'\b(rk_[a-zA-Z0-9_-]+)\b'),
    ],
    SensitiveDataType.TOKEN: [
        re.compile(r'token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'bearer\s+([a-zA-Z0-9._-]+)', re.IGNORECASE),
        re.compile(r'authorization["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'\b(eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)\b'),  # JWT
    ],
    SensitiveDataType.SECRET: [
        re.compile(r'secret["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
        re.compile(r'private[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE),
    ],
    SensitiveDataType.IP_ADDRESS: [
        re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'),
        re.compile(r'\b([0-9a-fA-F:]{7,})\b'),  # IPv6
    ],
    SensitiveDataType.EMAIL: [
        re.compile(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'),
    ],
    SensitiveDataType.CREDIT_CARD: [
        re.compile(r'\b(\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})\b'),
        re.compile(r'\b(\d{15,16})\b'),
    ],
    SensitiveDataType.SSN: [
        re.compile(r'\b(\d{3}-\d{2}-\d{4})\b'),
        re.compile(r'\b(\d{9})\b'),  # 9 consecutive digits
    ],
    SensitiveDataType.FILE_PATH: [
        re.compile(r'(/[a-zA-Z0-9._-]+){3,}'),
        re.compile(r'([A-Z]:\\[^\s:*?"<>|]+)', re.IGNORECASE),
    ],
    SensitiveDataType.DATABASE_URL: [
        re.compile(r'(postgres://[^\s]+)', re.IGNORECASE),
        re.compile(r'(mysql://[^\s]+)', re.IGNORECASE),
        re.compile(r'(mongodb://[^\s]+)', re.IGNORECASE),
        re.compile(r'(redis://[^\s]+)', re.IGNORECASE),
    ],
    SensitiveDataType.PHONE: [
        re.compile(r'\b(\+?1?[-.]?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4})\b'),
    ],
    SensitiveDataType.INTERNAL_URL: [
        re.compile(r'(https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)[^\s]*)'),
        re.compile(r'(https?://[a-zA-Z0-9.-]+\.internal[^\s]*)'),
        re.compile(r'(https?://[a-zA-Z0-9.-]+\.local[^\s]*)'),
    ],
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SanitizationResult:
    """Result of message sanitization."""
    original_message: str
    sanitized_message: str
    redacted_types: Set[SensitiveDataType] = field(default_factory=set)
    redaction_count: int = 0
    
    @property
    def was_sanitized(self) -> bool:
        """Check if any redaction occurred."""
        return self.redaction_count > 0


@dataclass
class SanitizationRule:
    """Custom sanitization rule."""
    name: str
    pattern: Pattern
    replacement: str = "[REDACTED]"
    data_type: Optional[SensitiveDataType] = None


# =============================================================================
# Message Sanitizer
# =============================================================================

class MessageSanitizer:
    """
    Sanitizes messages to remove sensitive data.
    
    Features:
    - Pattern-based detection
    - Multiple data type support
    - Customizable redaction
    - Custom rules
    """
    
    DEFAULT_REDACTION = "[REDACTED]"
    
    def __init__(
        self,
        enabled_types: Optional[Set[SensitiveDataType]] = None,
        custom_patterns: Optional[Dict[SensitiveDataType, List[Pattern]]] = None,
        redaction_text: str = DEFAULT_REDACTION,
    ):
        """
        Initialize sanitizer.
        
        Args:
            enabled_types: Types of data to redact (all by default)
            custom_patterns: Additional patterns per type
            redaction_text: Text to replace sensitive data with
        """
        self.enabled_types = enabled_types or set(SensitiveDataType)
        self.patterns = {**SENSITIVE_PATTERNS}
        self.redaction_text = redaction_text
        self._custom_rules: List[SanitizationRule] = []
        
        # Add custom patterns
        if custom_patterns:
            for data_type, patterns in custom_patterns.items():
                if data_type not in self.patterns:
                    self.patterns[data_type] = []
                self.patterns[data_type].extend(patterns)
    
    def add_rule(self, rule: SanitizationRule) -> None:
        """Add custom sanitization rule."""
        self._custom_rules.append(rule)
    
    def add_pattern(
        self,
        data_type: SensitiveDataType,
        pattern: str,
        flags: int = re.IGNORECASE,
    ) -> None:
        """Add pattern for data type."""
        if data_type not in self.patterns:
            self.patterns[data_type] = []
        self.patterns[data_type].append(re.compile(pattern, flags))
    
    def sanitize(self, message: str) -> SanitizationResult:
        """
        Sanitize a message.
        
        Args:
            message: Message to sanitize
            
        Returns:
            SanitizationResult
        """
        if not message:
            return SanitizationResult(
                original_message=message,
                sanitized_message=message,
            )
        
        sanitized = message
        redacted_types: Set[SensitiveDataType] = set()
        redaction_count = 0
        
        # Apply patterns for enabled types
        for data_type in self.enabled_types:
            patterns = self.patterns.get(data_type, [])
            for pattern in patterns:
                matches = pattern.findall(sanitized)
                if matches:
                    redacted_types.add(data_type)
                    redaction_count += len(matches)
                    
                    # Replace matches
                    sanitized = pattern.sub(
                        self._get_redaction(data_type),
                        sanitized,
                    )
        
        # Apply custom rules
        for rule in self._custom_rules:
            matches = rule.pattern.findall(sanitized)
            if matches:
                redaction_count += len(matches)
                if rule.data_type:
                    redacted_types.add(rule.data_type)
                sanitized = rule.pattern.sub(rule.replacement, sanitized)
        
        return SanitizationResult(
            original_message=message,
            sanitized_message=sanitized,
            redacted_types=redacted_types,
            redaction_count=redaction_count,
        )
    
    def _get_redaction(self, data_type: SensitiveDataType) -> str:
        """Get redaction text for data type."""
        type_labels = {
            SensitiveDataType.PASSWORD: "[REDACTED:PASSWORD]",
            SensitiveDataType.API_KEY: "[REDACTED:API_KEY]",
            SensitiveDataType.TOKEN: "[REDACTED:TOKEN]",
            SensitiveDataType.SECRET: "[REDACTED:SECRET]",
            SensitiveDataType.IP_ADDRESS: "[REDACTED:IP]",
            SensitiveDataType.EMAIL: "[REDACTED:EMAIL]",
            SensitiveDataType.CREDIT_CARD: "[REDACTED:CARD]",
            SensitiveDataType.SSN: "[REDACTED:SSN]",
            SensitiveDataType.FILE_PATH: "[REDACTED:PATH]",
            SensitiveDataType.DATABASE_URL: "[REDACTED:DB_URL]",
            SensitiveDataType.PHONE: "[REDACTED:PHONE]",
            SensitiveDataType.INTERNAL_URL: "[REDACTED:INTERNAL_URL]",
        }
        return type_labels.get(data_type, self.redaction_text)
    
    def is_sensitive(self, message: str) -> bool:
        """Check if message contains sensitive data."""
        for data_type in self.enabled_types:
            patterns = self.patterns.get(data_type, [])
            for pattern in patterns:
                if pattern.search(message):
                    return True
        return False
    
    def detect_sensitive_types(self, message: str) -> Set[SensitiveDataType]:
        """Detect types of sensitive data in message."""
        detected: Set[SensitiveDataType] = set()
        
        for data_type in self.enabled_types:
            patterns = self.patterns.get(data_type, [])
            for pattern in patterns:
                if pattern.search(message):
                    detected.add(data_type)
                    break
        
        return detected


# =============================================================================
# Exception Sanitizer
# =============================================================================

class ExceptionSanitizer:
    """
    Sanitizes exceptions for safe logging and response.
    """
    
    def __init__(self, sanitizer: Optional[MessageSanitizer] = None):
        """Initialize exception sanitizer."""
        self.sanitizer = sanitizer or MessageSanitizer()
    
    def sanitize_exception(
        self,
        exception: Exception,
        include_type: bool = True,
    ) -> str:
        """
        Sanitize exception message.
        
        Args:
            exception: Exception to sanitize
            include_type: Include exception type name
            
        Returns:
            Sanitized message
        """
        message = str(exception)
        result = self.sanitizer.sanitize(message)
        
        if include_type:
            exc_type = type(exception).__name__
            return f"{exc_type}: {result.sanitized_message}"
        
        return result.sanitized_message
    
    def sanitize_traceback(self, traceback_str: str) -> str:
        """
        Sanitize a traceback string.
        
        Args:
            traceback_str: Full traceback string
            
        Returns:
            Sanitized traceback
        """
        # Sanitize the entire traceback
        result = self.sanitizer.sanitize(traceback_str)
        return result.sanitized_message
    
    def get_safe_message(
        self,
        exception: Exception,
        default_message: str = "An error occurred",
    ) -> str:
        """
        Get safe message for exception.
        
        If exception message contains sensitive data,
        returns the default message instead.
        """
        message = str(exception)
        
        if self.sanitizer.is_sensitive(message):
            return default_message
        
        return message


# =============================================================================
# Log Sanitizer
# =============================================================================

class LogSanitizer:
    """
    Sanitizes log messages and contexts.
    """
    
    def __init__(self, sanitizer: Optional[MessageSanitizer] = None):
        """Initialize log sanitizer."""
        self.sanitizer = sanitizer or MessageSanitizer()
    
    def sanitize_log_record(
        self,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Dict[str, Any]]:
        """
        Sanitize log record.
        
        Args:
            message: Log message
            extra: Extra context
            
        Returns:
            Tuple of (sanitized_message, sanitized_extra)
        """
        # Sanitize message
        result = self.sanitizer.sanitize(message)
        sanitized_message = result.sanitized_message
        
        # Sanitize extra context
        sanitized_extra = {}
        if extra:
            sanitized_extra = self._sanitize_dict(extra)
        
        return sanitized_message, sanitized_extra
    
    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary."""
        sanitized = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                result = self.sanitizer.sanitize(value)
                sanitized[key] = result.sanitized_message
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = self._sanitize_list(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_list(self, data: List[Any]) -> List[Any]:
        """Sanitize list items."""
        sanitized = []
        
        for item in data:
            if isinstance(item, str):
                result = self.sanitizer.sanitize(item)
                sanitized.append(result.sanitized_message)
            elif isinstance(item, dict):
                sanitized.append(self._sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(self._sanitize_list(item))
            else:
                sanitized.append(item)
        
        return sanitized


# =============================================================================
# Sanitization Service
# =============================================================================

class SanitizationService:
    """
    High-level sanitization service.
    """
    
    _instance: Optional["SanitizationService"] = None
    
    def __init__(self):
        """Initialize service."""
        self.message_sanitizer = MessageSanitizer()
        self.exception_sanitizer = ExceptionSanitizer(self.message_sanitizer)
        self.log_sanitizer = LogSanitizer(self.message_sanitizer)
    
    @classmethod
    def get_instance(cls) -> "SanitizationService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def sanitize(self, message: str) -> str:
        """Sanitize a message."""
        return self.message_sanitizer.sanitize(message).sanitized_message
    
    def sanitize_exception(self, exception: Exception) -> str:
        """Sanitize exception message."""
        return self.exception_sanitizer.sanitize_exception(exception)
    
    def is_sensitive(self, message: str) -> bool:
        """Check if message contains sensitive data."""
        return self.message_sanitizer.is_sensitive(message)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_sanitization_service() -> SanitizationService:
    """Get the global sanitization service."""
    return SanitizationService.get_instance()


def sanitize_message(message: str) -> str:
    """Sanitize a message."""
    return get_sanitization_service().sanitize(message)


def sanitize_exception(exception: Exception) -> str:
    """Sanitize exception message."""
    return get_sanitization_service().sanitize_exception(exception)


def is_sensitive(message: str) -> bool:
    """Check if message contains sensitive data."""
    return get_sanitization_service().is_sensitive(message)
