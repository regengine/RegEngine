"""
SEC-048: LDAP Injection Prevention.

Secure LDAP query building with injection prevention,
input sanitization, and filter validation.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class LDAPThreatType(str, Enum):
    """Types of LDAP threats."""
    INJECTION = "injection"
    FILTER_BYPASS = "filter_bypass"
    DN_MANIPULATION = "dn_manipulation"
    ATTRIBUTE_INJECTION = "attribute_injection"
    WILDCARD_ABUSE = "wildcard_abuse"


class LDAPValidationResult(str, Enum):
    """Validation result types."""
    VALID = "valid"
    BLOCKED = "blocked"
    SANITIZED = "sanitized"


@dataclass
class LDAPSecurityConfig:
    """Configuration for LDAP security."""
    
    # Feature controls
    allow_wildcards: bool = False
    allow_nested_filters: bool = True
    strict_dn_validation: bool = True
    
    # Limits
    max_filter_length: int = 1000
    max_dn_length: int = 500
    max_attribute_length: int = 255
    max_value_length: int = 1000
    max_filter_depth: int = 10
    
    # Blocked patterns
    blocked_characters: str = "\x00\n\r"
    
    # Allowed attributes (empty = all allowed)
    allowed_attributes: list = field(default_factory=list)


@dataclass
class LDAPValidationReport:
    """Result of LDAP validation."""
    
    status: LDAPValidationResult
    is_safe: bool
    original_value: str
    sanitized_value: Optional[str] = None
    threats_detected: list = field(default_factory=list)
    error_message: Optional[str] = None


class LDAPCharacterEncoder:
    """Encodes special characters for LDAP."""
    
    # Characters that need escaping in LDAP filter values
    FILTER_ESCAPE_CHARS = {
        "\\": r"\5c",
        "*": r"\2a",
        "(": r"\28",
        ")": r"\29",
        "\x00": r"\00",
    }
    
    # Characters that need escaping in DN values
    DN_ESCAPE_CHARS = {
        "\\": r"\\",
        ",": r"\,",
        "+": r"\+",
        '"': r'\"',
        "<": r"\<",
        ">": r"\>",
        ";": r"\;",
        "=": r"\=",
        "#": r"\#",
        " ": r"\ ",  # Leading/trailing spaces
    }
    
    @classmethod
    def escape_filter_value(cls, value: str) -> str:
        """Escape value for use in LDAP filter."""
        if not value:
            return value
        
        result = value
        for char, escaped in cls.FILTER_ESCAPE_CHARS.items():
            result = result.replace(char, escaped)
        
        return result
    
    @classmethod
    def escape_dn_value(cls, value: str) -> str:
        """Escape value for use in DN."""
        if not value:
            return value
        
        result = []
        for i, char in enumerate(value):
            if char in cls.DN_ESCAPE_CHARS:
                # Special handling for leading/trailing spaces
                if char == " " and (i == 0 or i == len(value) - 1):
                    result.append(r"\ ")
                else:
                    result.append(cls.DN_ESCAPE_CHARS[char])
            else:
                result.append(char)
        
        return "".join(result)
    
    @classmethod
    def encode_value(cls, value: str) -> str:
        """Encode value using hex encoding for special chars."""
        result = []
        for char in value:
            if ord(char) < 32 or ord(char) > 126:
                result.append(f"\\{ord(char):02x}")
            else:
                result.append(char)
        return "".join(result)


class LDAPInputValidator:
    """Validates LDAP input for injection attempts."""
    
    # Injection patterns
    INJECTION_PATTERNS = [
        r"\)\s*\(",           # Filter concatenation
        r"\|\s*\(",           # OR injection
        r"&\s*\(",            # AND injection
        r"!\s*\(",            # NOT injection
        r"\*\s*\)",           # Wildcard filter bypass
        r"\\[0-9a-f]{2}",     # Hex-encoded characters (potential bypass)
        r"\x00",              # Null byte
        r"[\r\n]",            # Newline injection
    ]
    
    # Dangerous DN patterns - only match in values (not in full DNs)
    DN_INJECTION_PATTERNS = [
        r"[^\\],\s*cn=",      # Unescaped comma before cn=
        r"[^\\],\s*ou=",      # Unescaped comma before ou=
        r"[^\\],\s*dc=",      # Unescaped comma before dc=
        r"[^\\],\s*uid=",     # Unescaped comma before uid=
    ]
    
    def __init__(self, config: Optional[LDAPSecurityConfig] = None):
        self.config = config or LDAPSecurityConfig()
        self._injection_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]
        self._dn_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DN_INJECTION_PATTERNS
        ]
    
    def validate_filter_value(self, value: str) -> LDAPValidationReport:
        """Validate a value intended for LDAP filter."""
        threats = []
        
        # Check length
        if len(value) > self.config.max_value_length:
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=value,
                threats_detected=[LDAPThreatType.INJECTION],
                error_message="Value exceeds maximum length",
            )
        
        # Check for blocked characters
        for char in self.config.blocked_characters:
            if char in value:
                threats.append(LDAPThreatType.INJECTION)
                break
        
        # Check for injection patterns
        for pattern in self._injection_patterns:
            if pattern.search(value):
                threats.append(LDAPThreatType.INJECTION)
                break
        
        # Check for wildcards
        if "*" in value and not self.config.allow_wildcards:
            threats.append(LDAPThreatType.WILDCARD_ABUSE)
        
        if threats:
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=value,
                threats_detected=threats,
                error_message="Injection patterns detected",
            )
        
        return LDAPValidationReport(
            status=LDAPValidationResult.VALID,
            is_safe=True,
            original_value=value,
            sanitized_value=value,
        )
    
    def validate_dn(self, dn: str, is_full_dn: bool = True) -> LDAPValidationReport:
        """Validate a distinguished name.
        
        Args:
            dn: The DN to validate
            is_full_dn: If True, treat as complete DN (allows standard separators)
                       If False, treat as user input that shouldn't contain DN components
        """
        threats = []
        
        # Check length
        if len(dn) > self.config.max_dn_length:
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=dn,
                threats_detected=[LDAPThreatType.DN_MANIPULATION],
                error_message="DN exceeds maximum length",
            )
        
        # Check for blocked characters
        for char in self.config.blocked_characters:
            if char in dn:
                threats.append(LDAPThreatType.DN_MANIPULATION)
                break
        
        # Check for DN injection patterns only if not a full DN
        if self.config.strict_dn_validation and not is_full_dn:
            for pattern in self._dn_patterns:
                if pattern.search(dn):
                    threats.append(LDAPThreatType.DN_MANIPULATION)
                    break
        
        if threats:
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=dn,
                threats_detected=threats,
                error_message="DN manipulation detected",
            )
        
        return LDAPValidationReport(
            status=LDAPValidationResult.VALID,
            is_safe=True,
            original_value=dn,
            sanitized_value=dn,
        )
    
    def validate_attribute(self, attr: str) -> LDAPValidationReport:
        """Validate an attribute name."""
        # Check length
        if len(attr) > self.config.max_attribute_length:
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=attr,
                error_message="Attribute name too long",
            )
        
        # Check format (alphanumeric and hyphens only)
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9\-]*$", attr):
            return LDAPValidationReport(
                status=LDAPValidationResult.BLOCKED,
                is_safe=False,
                original_value=attr,
                threats_detected=[LDAPThreatType.ATTRIBUTE_INJECTION],
                error_message="Invalid attribute name format",
            )
        
        # Check allowlist if configured
        if self.config.allowed_attributes:
            if attr.lower() not in [a.lower() for a in self.config.allowed_attributes]:
                return LDAPValidationReport(
                    status=LDAPValidationResult.BLOCKED,
                    is_safe=False,
                    original_value=attr,
                    error_message="Attribute not in allowlist",
                )
        
        return LDAPValidationReport(
            status=LDAPValidationResult.VALID,
            is_safe=True,
            original_value=attr,
            sanitized_value=attr,
        )


class LDAPFilterBuilder:
    """Builds safe LDAP filters."""
    
    def __init__(self, config: Optional[LDAPSecurityConfig] = None):
        self.config = config or LDAPSecurityConfig()
        self.validator = LDAPInputValidator(self.config)
        self.encoder = LDAPCharacterEncoder()
    
    def equals(self, attr: str, value: str) -> Optional[str]:
        """Build equality filter: (attr=value)."""
        attr_result = self.validator.validate_attribute(attr)
        if not attr_result.is_safe:
            return None
        
        value_result = self.validator.validate_filter_value(value)
        if not value_result.is_safe:
            return None
        
        escaped_value = self.encoder.escape_filter_value(value)
        return f"({attr}={escaped_value})"
    
    def presence(self, attr: str) -> Optional[str]:
        """Build presence filter: (attr=*)."""
        attr_result = self.validator.validate_attribute(attr)
        if not attr_result.is_safe:
            return None
        
        return f"({attr}=*)"
    
    def starts_with(self, attr: str, value: str) -> Optional[str]:
        """Build starts-with filter: (attr=value*)."""
        if not self.config.allow_wildcards:
            return None
        
        attr_result = self.validator.validate_attribute(attr)
        if not attr_result.is_safe:
            return None
        
        # Don't allow wildcards in value itself
        if "*" in value:
            return None
        
        escaped_value = self.encoder.escape_filter_value(value)
        return f"({attr}={escaped_value}*)"
    
    def ends_with(self, attr: str, value: str) -> Optional[str]:
        """Build ends-with filter: (attr=*value)."""
        if not self.config.allow_wildcards:
            return None
        
        attr_result = self.validator.validate_attribute(attr)
        if not attr_result.is_safe:
            return None
        
        if "*" in value:
            return None
        
        escaped_value = self.encoder.escape_filter_value(value)
        return f"({attr}=*{escaped_value})"
    
    def contains(self, attr: str, value: str) -> Optional[str]:
        """Build contains filter: (attr=*value*)."""
        if not self.config.allow_wildcards:
            return None
        
        attr_result = self.validator.validate_attribute(attr)
        if not attr_result.is_safe:
            return None
        
        if "*" in value:
            return None
        
        escaped_value = self.encoder.escape_filter_value(value)
        return f"({attr}=*{escaped_value}*)"
    
    def and_filter(self, *filters: str) -> Optional[str]:
        """Build AND filter: (&(filter1)(filter2)...)."""
        if not filters:
            return None
        
        valid_filters = [f for f in filters if f]
        if not valid_filters:
            return None
        
        combined = "".join(valid_filters)
        if len(combined) > self.config.max_filter_length:
            return None
        
        return f"(&{combined})"
    
    def or_filter(self, *filters: str) -> Optional[str]:
        """Build OR filter: (|(filter1)(filter2)...)."""
        if not filters:
            return None
        
        valid_filters = [f for f in filters if f]
        if not valid_filters:
            return None
        
        combined = "".join(valid_filters)
        if len(combined) > self.config.max_filter_length:
            return None
        
        return f"(|{combined})"
    
    def not_filter(self, filter_str: str) -> Optional[str]:
        """Build NOT filter: (!(filter))."""
        if not filter_str:
            return None
        
        return f"(!{filter_str})"


class LDAPDNBuilder:
    """Builds safe LDAP distinguished names."""
    
    def __init__(self, config: Optional[LDAPSecurityConfig] = None):
        self.config = config or LDAPSecurityConfig()
        self.validator = LDAPInputValidator(self.config)
        self.encoder = LDAPCharacterEncoder()
    
    def build_dn(self, **components: str) -> Optional[str]:
        """Build DN from components."""
        parts = []
        
        for attr, value in components.items():
            # Validate attribute
            attr_result = self.validator.validate_attribute(attr)
            if not attr_result.is_safe:
                return None
            
            # Escape value
            escaped_value = self.encoder.escape_dn_value(value)
            parts.append(f"{attr}={escaped_value}")
        
        dn = ",".join(parts)
        
        if len(dn) > self.config.max_dn_length:
            return None
        
        return dn
    
    def build_user_dn(
        self,
        username: str,
        base_dn: str,
    ) -> Optional[str]:
        """Build user DN."""
        # Validate base DN (as a full DN)
        dn_result = self.validator.validate_dn(base_dn, is_full_dn=True)
        if not dn_result.is_safe:
            return None
        
        # Escape username
        escaped_user = self.encoder.escape_dn_value(username)
        
        dn = f"cn={escaped_user},{base_dn}"
        
        if len(dn) > self.config.max_dn_length:
            return None
        
        return dn


class LDAPSecurityService:
    """Comprehensive LDAP security service."""
    
    _instance: Optional["LDAPSecurityService"] = None
    
    def __init__(self, config: Optional[LDAPSecurityConfig] = None):
        self.config = config or LDAPSecurityConfig()
        self.validator = LDAPInputValidator(self.config)
        self.encoder = LDAPCharacterEncoder()
        self.filter_builder = LDAPFilterBuilder(self.config)
        self.dn_builder = LDAPDNBuilder(self.config)
    
    @classmethod
    def get_instance(cls) -> "LDAPSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: LDAPSecurityConfig) -> "LDAPSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def escape_filter_value(self, value: str) -> str:
        """Escape value for filter."""
        return self.encoder.escape_filter_value(value)
    
    def escape_dn_value(self, value: str) -> str:
        """Escape value for DN."""
        return self.encoder.escape_dn_value(value)
    
    def validate_filter_value(self, value: str) -> LDAPValidationReport:
        """Validate filter value."""
        return self.validator.validate_filter_value(value)
    
    def validate_dn(self, dn: str, is_full_dn: bool = True) -> LDAPValidationReport:
        """Validate DN."""
        return self.validator.validate_dn(dn, is_full_dn=is_full_dn)
    
    def build_filter(
        self,
        attr: str,
        value: str,
    ) -> Optional[str]:
        """Build safe equality filter."""
        return self.filter_builder.equals(attr, value)
    
    def build_dn(self, **components: str) -> Optional[str]:
        """Build safe DN."""
        return self.dn_builder.build_dn(**components)
    
    def sanitize_for_filter(self, value: str) -> str:
        """Sanitize value for filter use."""
        return self.encoder.escape_filter_value(value)
    
    def sanitize_for_dn(self, value: str) -> str:
        """Sanitize value for DN use."""
        return self.encoder.escape_dn_value(value)


# Convenience functions
def get_ldap_service() -> LDAPSecurityService:
    """Get LDAP service instance."""
    return LDAPSecurityService.get_instance()


def escape_ldap_filter(value: str) -> str:
    """Escape value for LDAP filter."""
    return get_ldap_service().escape_filter_value(value)


def escape_ldap_dn(value: str) -> str:
    """Escape value for LDAP DN."""
    return get_ldap_service().escape_dn_value(value)


def build_ldap_filter(attr: str, value: str) -> Optional[str]:
    """Build safe LDAP filter."""
    return get_ldap_service().build_filter(attr, value)
