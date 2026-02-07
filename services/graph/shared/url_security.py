"""
SEC-038: URL Validation and Sanitization.

Provides secure URL handling:
- URL validation
- Protocol whitelisting
- Domain validation
- Path sanitization
- Open redirect prevention
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse


# =============================================================================
# Enums
# =============================================================================

class URLValidationResult(str, Enum):
    """URL validation results."""
    VALID = "valid"
    INVALID_SCHEME = "invalid_scheme"
    INVALID_HOST = "invalid_host"
    INVALID_PORT = "invalid_port"
    INVALID_PATH = "invalid_path"
    BLOCKED_DOMAIN = "blocked_domain"
    OPEN_REDIRECT = "open_redirect"
    MALFORMED = "malformed"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class URLConfig:
    """URL validation configuration."""
    allowed_schemes: Set[str] = field(default_factory=lambda: {"https"})
    allowed_hosts: Optional[Set[str]] = None  # None = allow all
    blocked_hosts: Set[str] = field(default_factory=lambda: {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
    })
    allowed_ports: Optional[Set[int]] = None  # None = allow all
    allow_credentials_in_url: bool = False
    allow_fragments: bool = True
    max_length: int = 2048
    allow_ip_addresses: bool = False
    require_tld: bool = True


@dataclass
class ParsedURL:
    """Parsed and validated URL."""
    original: str
    scheme: str
    host: str
    port: Optional[int]
    path: str
    query: str
    fragment: str
    username: Optional[str] = None
    password: Optional[str] = None
    is_valid: bool = True
    validation_result: URLValidationResult = URLValidationResult.VALID
    
    def to_string(self) -> str:
        """Convert back to URL string."""
        netloc = self.host
        if self.port:
            netloc = f"{self.host}:{self.port}"
        
        return urlunparse((
            self.scheme,
            netloc,
            self.path,
            "",  # params
            self.query,
            self.fragment if self.fragment else "",
        ))


@dataclass
class RedirectValidation:
    """Result of redirect URL validation."""
    is_safe: bool
    target_url: str
    reason: str


# =============================================================================
# URL Validator
# =============================================================================

class URLValidator:
    """
    Validates URLs for security issues.
    
    Features:
    - Scheme validation
    - Host/domain validation
    - Open redirect detection
    - IP address detection
    """
    
    # IP address patterns
    IPV4_PATTERN = re.compile(
        r"^(\d{1,3}\.){3}\d{1,3}$"
    )
    IPV6_PATTERN = re.compile(
        r"^\[?([a-fA-F0-9:]+)\]?$"
    )
    
    def __init__(self, config: Optional[URLConfig] = None):
        """Initialize validator."""
        self.config = config or URLConfig()
    
    def validate(self, url: str) -> Tuple[bool, URLValidationResult]:
        """
        Validate a URL.
        
        Returns:
            Tuple of (is_valid, result)
        """
        # Check length
        if len(url) > self.config.max_length:
            return False, URLValidationResult.MALFORMED
        
        try:
            parsed = urlparse(url)
        except Exception:
            return False, URLValidationResult.MALFORMED
        
        # Validate scheme
        if parsed.scheme.lower() not in self.config.allowed_schemes:
            return False, URLValidationResult.INVALID_SCHEME
        
        # Validate host exists
        if not parsed.netloc and not parsed.path.startswith("/"):
            return False, URLValidationResult.INVALID_HOST
        
        host = parsed.hostname or ""
        
        # Check for credentials in URL
        if not self.config.allow_credentials_in_url:
            if parsed.username or parsed.password:
                return False, URLValidationResult.MALFORMED
        
        # Check blocked hosts
        if host.lower() in self.config.blocked_hosts:
            return False, URLValidationResult.BLOCKED_DOMAIN
        
        # Check allowed hosts
        if self.config.allowed_hosts:
            if host.lower() not in self.config.allowed_hosts:
                return False, URLValidationResult.INVALID_HOST
        
        # Check for IP addresses
        if not self.config.allow_ip_addresses:
            if self._is_ip_address(host):
                return False, URLValidationResult.INVALID_HOST
        
        # Check for TLD
        if self.config.require_tld and host:
            if "." not in host and not self._is_ip_address(host):
                return False, URLValidationResult.INVALID_HOST
        
        # Check port
        if self.config.allowed_ports and parsed.port:
            if parsed.port not in self.config.allowed_ports:
                return False, URLValidationResult.INVALID_PORT
        
        return True, URLValidationResult.VALID
    
    def _is_ip_address(self, host: str) -> bool:
        """Check if host is an IP address."""
        if self.IPV4_PATTERN.match(host):
            return True
        if self.IPV6_PATTERN.match(host):
            return True
        return False
    
    def parse(self, url: str) -> ParsedURL:
        """Parse and validate a URL."""
        is_valid, result = self.validate(url)
        
        try:
            parsed = urlparse(url)
            return ParsedURL(
                original=url,
                scheme=parsed.scheme,
                host=parsed.hostname or "",
                port=parsed.port,
                path=parsed.path,
                query=parsed.query,
                fragment=parsed.fragment,
                username=parsed.username,
                password=parsed.password,
                is_valid=is_valid,
                validation_result=result,
            )
        except Exception:
            return ParsedURL(
                original=url,
                scheme="",
                host="",
                port=None,
                path="",
                query="",
                fragment="",
                is_valid=False,
                validation_result=URLValidationResult.MALFORMED,
            )


# =============================================================================
# Open Redirect Validator
# =============================================================================

class OpenRedirectValidator:
    """
    Validates redirect URLs to prevent open redirect attacks.
    """
    
    def __init__(
        self,
        allowed_hosts: Optional[Set[str]] = None,
        allow_relative: bool = True,
    ):
        """Initialize validator."""
        self.allowed_hosts = allowed_hosts or set()
        self.allow_relative = allow_relative
    
    def is_safe_redirect(
        self,
        target_url: str,
        current_host: str,
    ) -> RedirectValidation:
        """
        Check if redirect URL is safe.
        
        Args:
            target_url: The redirect target
            current_host: The current request host
            
        Returns:
            RedirectValidation result
        """
        # Normalize the URL
        target_url = target_url.strip()
        
        # Check for protocol-relative URLs (//evil.com)
        if target_url.startswith("//"):
            return RedirectValidation(
                is_safe=False,
                target_url=target_url,
                reason="Protocol-relative URLs not allowed",
            )
        
        # Check for javascript: or data: URLs
        lower_url = target_url.lower()
        if lower_url.startswith(("javascript:", "data:", "vbscript:")):
            return RedirectValidation(
                is_safe=False,
                target_url=target_url,
                reason="Dangerous scheme",
            )
        
        # Check for relative URLs
        if not target_url.startswith(("http://", "https://")):
            if self.allow_relative:
                # Ensure it's truly relative (starts with / or is path-only)
                if target_url.startswith("/") or not ":" in target_url.split("/")[0]:
                    return RedirectValidation(
                        is_safe=True,
                        target_url=target_url,
                        reason="Relative URL allowed",
                    )
            return RedirectValidation(
                is_safe=False,
                target_url=target_url,
                reason="Non-relative URL with unknown scheme",
            )
        
        # Parse the URL
        try:
            parsed = urlparse(target_url)
            target_host = parsed.hostname or ""
        except Exception:
            return RedirectValidation(
                is_safe=False,
                target_url=target_url,
                reason="Malformed URL",
            )
        
        # Check if host is allowed
        if target_host.lower() == current_host.lower():
            return RedirectValidation(
                is_safe=True,
                target_url=target_url,
                reason="Same host",
            )
        
        if target_host.lower() in self.allowed_hosts:
            return RedirectValidation(
                is_safe=True,
                target_url=target_url,
                reason="Allowed host",
            )
        
        # Check for subdomain of allowed host
        for allowed in self.allowed_hosts:
            if target_host.lower().endswith(f".{allowed.lower()}"):
                return RedirectValidation(
                    is_safe=True,
                    target_url=target_url,
                    reason="Allowed subdomain",
                )
        
        return RedirectValidation(
            is_safe=False,
            target_url=target_url,
            reason=f"Host '{target_host}' not in allowed list",
        )


# =============================================================================
# URL Sanitizer
# =============================================================================

class URLSanitizer:
    """
    Sanitizes URLs to remove dangerous content.
    """
    
    # Characters that need encoding
    UNSAFE_CHARS = '<>"\'{}'
    
    def __init__(self, config: Optional[URLConfig] = None):
        """Initialize sanitizer."""
        self.config = config or URLConfig()
    
    def sanitize(self, url: str) -> str:
        """
        Sanitize a URL.
        
        Args:
            url: The URL to sanitize
            
        Returns:
            Sanitized URL
        """
        # Trim whitespace
        url = url.strip()
        
        # Remove null bytes
        url = url.replace("\x00", "")
        
        # Remove control characters
        url = "".join(c for c in url if ord(c) >= 32 or c in "\t\n\r")
        
        # Parse the URL
        try:
            parsed = urlparse(url)
        except Exception:
            return ""
        
        # Sanitize each component
        scheme = self._sanitize_scheme(parsed.scheme)
        host = self._sanitize_host(parsed.hostname or "")
        port = parsed.port
        path = self._sanitize_path(parsed.path)
        query = self._sanitize_query(parsed.query)
        fragment = parsed.fragment if self.config.allow_fragments else ""
        
        # Rebuild netloc
        netloc = host
        if port:
            netloc = f"{host}:{port}"
        
        # Rebuild URL
        return urlunparse((
            scheme,
            netloc,
            path,
            "",  # params
            query,
            fragment,
        ))
    
    def _sanitize_scheme(self, scheme: str) -> str:
        """Sanitize URL scheme."""
        scheme = scheme.lower()
        if scheme in self.config.allowed_schemes:
            return scheme
        return "https"  # Default to https
    
    def _sanitize_host(self, host: str) -> str:
        """Sanitize hostname."""
        # Remove leading/trailing dots
        host = host.strip(".")
        # Lowercase
        host = host.lower()
        # Remove dangerous characters
        for char in self.UNSAFE_CHARS:
            host = host.replace(char, "")
        return host
    
    def _sanitize_path(self, path: str) -> str:
        """Sanitize URL path."""
        # Decode and re-encode to normalize
        try:
            path = unquote(path)
        except Exception:
            pass
        
        # Remove path traversal attempts
        while "../" in path:
            path = path.replace("../", "")
        while "..\\" in path:
            path = path.replace("..\\", "")
        
        # Re-encode special characters
        path = quote(path, safe="/")
        
        return path
    
    def _sanitize_query(self, query: str) -> str:
        """Sanitize query string."""
        if not query:
            return ""
        
        try:
            # Parse query parameters
            params = parse_qs(query, keep_blank_values=True)
            
            # Sanitize each value
            sanitized = {}
            for key, values in params.items():
                sanitized_values = []
                for value in values:
                    # Remove dangerous characters
                    for char in self.UNSAFE_CHARS:
                        value = value.replace(char, "")
                    sanitized_values.append(value)
                sanitized[key] = sanitized_values
            
            # Re-encode
            return urlencode(sanitized, doseq=True)
        except Exception:
            return ""
    
    def sanitize_for_html(self, url: str) -> str:
        """Sanitize URL for use in HTML attributes."""
        url = self.sanitize(url)
        
        # HTML-encode special characters
        html_entities = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#x27;",
        }
        
        for char, entity in html_entities.items():
            url = url.replace(char, entity)
        
        return url


# =============================================================================
# URL Security Service
# =============================================================================

class URLSecurityService:
    """
    High-level service for URL security.
    """
    
    _instance: Optional["URLSecurityService"] = None
    
    def __init__(self, config: Optional[URLConfig] = None):
        """Initialize service."""
        self.config = config or URLConfig()
        self.validator = URLValidator(self.config)
        self.sanitizer = URLSanitizer(self.config)
        self.redirect_validator = OpenRedirectValidator()
    
    @classmethod
    def get_instance(cls) -> "URLSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: URLConfig) -> "URLSecurityService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def validate(self, url: str) -> Tuple[bool, URLValidationResult]:
        """Validate a URL."""
        return self.validator.validate(url)
    
    def parse(self, url: str) -> ParsedURL:
        """Parse and validate a URL."""
        return self.validator.parse(url)
    
    def sanitize(self, url: str) -> str:
        """Sanitize a URL."""
        return self.sanitizer.sanitize(url)
    
    def is_safe_redirect(
        self,
        target: str,
        current_host: str,
    ) -> RedirectValidation:
        """Check if redirect is safe."""
        return self.redirect_validator.is_safe_redirect(target, current_host)
    
    def configure_redirect_validator(
        self,
        allowed_hosts: Set[str],
        allow_relative: bool = True,
    ) -> None:
        """Configure the redirect validator."""
        self.redirect_validator = OpenRedirectValidator(
            allowed_hosts=allowed_hosts,
            allow_relative=allow_relative,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def get_url_service() -> URLSecurityService:
    """Get the global URL security service."""
    return URLSecurityService.get_instance()


def validate_url(url: str) -> bool:
    """Validate a URL."""
    is_valid, _ = get_url_service().validate(url)
    return is_valid


def sanitize_url(url: str) -> str:
    """Sanitize a URL."""
    return get_url_service().sanitize(url)


def is_safe_redirect(target: str, current_host: str) -> bool:
    """Check if redirect is safe."""
    result = get_url_service().is_safe_redirect(target, current_host)
    return result.is_safe
