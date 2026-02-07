"""
SEC-037: Cookie Security.

Provides secure cookie handling:
- Secure flag
- HttpOnly flag
- SameSite attribute
- Domain/Path restrictions
- Expiration management
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote, unquote


# =============================================================================
# Enums
# =============================================================================

class SameSite(str, Enum):
    """SameSite cookie attribute values."""
    STRICT = "Strict"
    LAX = "Lax"
    NONE = "None"


class CookiePriority(str, Enum):
    """Cookie priority values."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CookieConfig:
    """Cookie configuration."""
    secure: bool = True
    http_only: bool = True
    same_site: SameSite = SameSite.LAX
    domain: Optional[str] = None
    path: str = "/"
    max_age: Optional[int] = None
    expires: Optional[datetime] = None
    priority: CookiePriority = CookiePriority.MEDIUM
    partitioned: bool = False
    
    def validate(self) -> List[str]:
        """Validate configuration."""
        errors = []
        
        if self.same_site == SameSite.NONE and not self.secure:
            errors.append("SameSite=None requires Secure flag")
        
        if self.max_age is not None and self.max_age < 0:
            errors.append("max_age cannot be negative")
        
        return errors


@dataclass
class Cookie:
    """Represents a cookie."""
    name: str
    value: str
    config: CookieConfig = field(default_factory=CookieConfig)
    
    def to_header_value(self) -> str:
        """Convert to Set-Cookie header value."""
        parts = [f"{quote(self.name)}={quote(self.value)}"]
        
        if self.config.secure:
            parts.append("Secure")
        
        if self.config.http_only:
            parts.append("HttpOnly")
        
        parts.append(f"SameSite={self.config.same_site.value}")
        
        if self.config.domain:
            parts.append(f"Domain={self.config.domain}")
        
        if self.config.path:
            parts.append(f"Path={self.config.path}")
        
        if self.config.max_age is not None:
            parts.append(f"Max-Age={self.config.max_age}")
        
        if self.config.expires:
            expires_str = self.config.expires.strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            parts.append(f"Expires={expires_str}")
        
        if self.config.priority != CookiePriority.MEDIUM:
            parts.append(f"Priority={self.config.priority.value}")
        
        if self.config.partitioned:
            parts.append("Partitioned")
        
        return "; ".join(parts)


@dataclass
class ParsedCookie:
    """A parsed cookie from request."""
    name: str
    value: str
    raw: str


# =============================================================================
# Cookie Builder
# =============================================================================

class CookieBuilder:
    """
    Fluent builder for cookies.
    """
    
    def __init__(self, name: str, value: str):
        """Initialize builder."""
        self._name = name
        self._value = value
        self._config = CookieConfig()
    
    def secure(self, enabled: bool = True) -> "CookieBuilder":
        """Set secure flag."""
        self._config.secure = enabled
        return self
    
    def http_only(self, enabled: bool = True) -> "CookieBuilder":
        """Set HttpOnly flag."""
        self._config.http_only = enabled
        return self
    
    def same_site(self, value: SameSite) -> "CookieBuilder":
        """Set SameSite attribute."""
        self._config.same_site = value
        return self
    
    def domain(self, domain: str) -> "CookieBuilder":
        """Set domain."""
        self._config.domain = domain
        return self
    
    def path(self, path: str) -> "CookieBuilder":
        """Set path."""
        self._config.path = path
        return self
    
    def max_age(self, seconds: int) -> "CookieBuilder":
        """Set max age in seconds."""
        self._config.max_age = seconds
        return self
    
    def expires(self, when: datetime) -> "CookieBuilder":
        """Set expiration time."""
        self._config.expires = when
        return self
    
    def expires_in(self, delta: timedelta) -> "CookieBuilder":
        """Set expiration relative to now."""
        self._config.expires = datetime.now(timezone.utc) + delta
        return self
    
    def priority(self, priority: CookiePriority) -> "CookieBuilder":
        """Set priority."""
        self._config.priority = priority
        return self
    
    def session(self) -> "CookieBuilder":
        """Make this a session cookie (no expiration)."""
        self._config.max_age = None
        self._config.expires = None
        return self
    
    def build(self) -> Cookie:
        """Build the cookie."""
        return Cookie(
            name=self._name,
            value=self._value,
            config=self._config,
        )
    
    def to_header_value(self) -> str:
        """Build and return header value."""
        return self.build().to_header_value()


# =============================================================================
# Cookie Parser
# =============================================================================

class CookieParser:
    """
    Parses cookies from request headers.
    """
    
    def parse(self, cookie_header: str) -> Dict[str, str]:
        """
        Parse Cookie header into dict.
        
        Args:
            cookie_header: The Cookie header value
            
        Returns:
            Dict of cookie name to value
        """
        cookies = {}
        
        if not cookie_header:
            return cookies
        
        pairs = cookie_header.split(";")
        for pair in pairs:
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                name = unquote(name.strip())
                value = unquote(value.strip())
                cookies[name] = value
        
        return cookies
    
    def parse_to_list(self, cookie_header: str) -> List[ParsedCookie]:
        """
        Parse Cookie header into list of ParsedCookie.
        
        Args:
            cookie_header: The Cookie header value
            
        Returns:
            List of parsed cookies
        """
        cookies = []
        
        if not cookie_header:
            return cookies
        
        pairs = cookie_header.split(";")
        for pair in pairs:
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies.append(ParsedCookie(
                    name=unquote(name.strip()),
                    value=unquote(value.strip()),
                    raw=pair,
                ))
        
        return cookies


# =============================================================================
# Cookie Validator
# =============================================================================

class CookieValidator:
    """
    Validates cookies for security issues.
    """
    
    # Reserved/sensitive cookie names
    SENSITIVE_NAMES = {"session", "auth", "token", "jwt", "csrf"}
    
    def __init__(self):
        """Initialize validator."""
        self._warnings: List[str] = []
    
    def validate(self, cookie: Cookie) -> List[str]:
        """
        Validate a cookie for security issues.
        
        Returns:
            List of warning messages
        """
        self._warnings = []
        
        # Check secure flag
        if not cookie.config.secure:
            self._warnings.append(
                f"Cookie '{cookie.name}' missing Secure flag"
            )
        
        # Check HttpOnly for sensitive cookies
        if cookie.name.lower() in self.SENSITIVE_NAMES:
            if not cookie.config.http_only:
                self._warnings.append(
                    f"Sensitive cookie '{cookie.name}' missing HttpOnly flag"
                )
        
        # Check SameSite
        if cookie.config.same_site == SameSite.NONE:
            self._warnings.append(
                f"Cookie '{cookie.name}' has SameSite=None, vulnerable to CSRF"
            )
        
        # Validate config
        config_errors = cookie.config.validate()
        self._warnings.extend(config_errors)
        
        return self._warnings


# =============================================================================
# Secure Cookie Manager
# =============================================================================

class SecureCookieManager:
    """
    Manages cookies with security features.
    
    Features:
    - Signed cookies
    - Encrypted cookies (simple obfuscation)
    - Prefix enforcement
    """
    
    # Cookie prefixes
    HOST_PREFIX = "__Host-"
    SECURE_PREFIX = "__Secure-"
    
    def __init__(
        self,
        secret_key: str,
        default_config: Optional[CookieConfig] = None,
    ):
        """Initialize manager."""
        self._secret_key = secret_key.encode()
        self.default_config = default_config or CookieConfig()
    
    def create(
        self,
        name: str,
        value: str,
        config: Optional[CookieConfig] = None,
    ) -> Cookie:
        """Create a cookie with default config."""
        return Cookie(
            name=name,
            value=value,
            config=config or self.default_config,
        )
    
    def create_signed(
        self,
        name: str,
        value: str,
        config: Optional[CookieConfig] = None,
    ) -> Cookie:
        """Create a signed cookie."""
        signature = self._sign(value)
        signed_value = f"{value}.{signature}"
        
        return Cookie(
            name=name,
            value=signed_value,
            config=config or self.default_config,
        )
    
    def verify_signed(self, cookie_value: str) -> Optional[str]:
        """
        Verify a signed cookie.
        
        Returns:
            Original value if valid, None if invalid
        """
        if "." not in cookie_value:
            return None
        
        value, signature = cookie_value.rsplit(".", 1)
        expected = self._sign(value)
        
        if hmac.compare_digest(signature, expected):
            return value
        
        return None
    
    def create_with_host_prefix(
        self,
        name: str,
        value: str,
    ) -> Cookie:
        """
        Create a cookie with __Host- prefix.
        
        __Host- cookies must:
        - Have Secure flag
        - Not have Domain attribute
        - Have Path=/
        """
        config = CookieConfig(
            secure=True,
            http_only=True,
            same_site=SameSite.STRICT,
            domain=None,  # Must not have domain
            path="/",  # Must be /
        )
        
        return Cookie(
            name=f"{self.HOST_PREFIX}{name}",
            value=value,
            config=config,
        )
    
    def create_with_secure_prefix(
        self,
        name: str,
        value: str,
        config: Optional[CookieConfig] = None,
    ) -> Cookie:
        """
        Create a cookie with __Secure- prefix.
        
        __Secure- cookies must have Secure flag.
        """
        final_config = config or CookieConfig()
        final_config.secure = True  # Must be secure
        
        return Cookie(
            name=f"{self.SECURE_PREFIX}{name}",
            value=value,
            config=final_config,
        )
    
    def _sign(self, value: str) -> str:
        """Create signature for value."""
        return hmac.new(
            self._secret_key,
            value.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
    
    def create_session_cookie(
        self,
        session_id: str,
    ) -> Cookie:
        """Create a secure session cookie."""
        config = CookieConfig(
            secure=True,
            http_only=True,
            same_site=SameSite.STRICT,
            path="/",
        )
        
        return self.create_signed(
            name=f"{self.HOST_PREFIX}session",
            value=session_id,
            config=config,
        )
    
    def delete_cookie(self, name: str) -> Cookie:
        """Create a cookie deletion header."""
        config = CookieConfig(
            max_age=0,
            expires=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
        
        return Cookie(name=name, value="", config=config)


# =============================================================================
# Cookie Security Service
# =============================================================================

class CookieSecurityService:
    """
    High-level service for cookie security.
    """
    
    _instance: Optional["CookieSecurityService"] = None
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        default_config: Optional[CookieConfig] = None,
    ):
        """Initialize service."""
        self._secret_key = secret_key or secrets.token_hex(32)
        self.default_config = default_config or CookieConfig()
        self.manager = SecureCookieManager(self._secret_key, self.default_config)
        self.parser = CookieParser()
        self.validator = CookieValidator()
    
    @classmethod
    def get_instance(cls) -> "CookieSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        secret_key: str,
        default_config: Optional[CookieConfig] = None,
    ) -> "CookieSecurityService":
        """Configure the service."""
        cls._instance = cls(secret_key, default_config)
        return cls._instance
    
    def create(self, name: str, value: str) -> Cookie:
        """Create a cookie."""
        return self.manager.create(name, value)
    
    def create_signed(self, name: str, value: str) -> Cookie:
        """Create a signed cookie."""
        return self.manager.create_signed(name, value)
    
    def verify_signed(self, value: str) -> Optional[str]:
        """Verify a signed cookie."""
        return self.manager.verify_signed(value)
    
    def parse(self, cookie_header: str) -> Dict[str, str]:
        """Parse cookies from header."""
        return self.parser.parse(cookie_header)
    
    def validate(self, cookie: Cookie) -> List[str]:
        """Validate a cookie."""
        return self.validator.validate(cookie)
    
    def builder(self, name: str, value: str) -> CookieBuilder:
        """Get a cookie builder."""
        return CookieBuilder(name, value)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_cookie_service() -> CookieSecurityService:
    """Get the global cookie service."""
    return CookieSecurityService.get_instance()


def create_secure_cookie(name: str, value: str) -> str:
    """Create a secure cookie header value."""
    return get_cookie_service().create(name, value).to_header_value()


def parse_cookies(cookie_header: str) -> Dict[str, str]:
    """Parse cookies from header."""
    return get_cookie_service().parse(cookie_header)
