"""
SEC-036: HTTP Security Headers.

Provides comprehensive HTTP security headers:
- Content-Security-Policy (CSP)
- X-Frame-Options
- X-Content-Type-Options
- Strict-Transport-Security (HSTS)
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


# =============================================================================
# Enums
# =============================================================================

class FrameOption(str, Enum):
    """X-Frame-Options values."""
    DENY = "DENY"
    SAMEORIGIN = "SAMEORIGIN"
    ALLOW_FROM = "ALLOW-FROM"


class ReferrerPolicy(str, Enum):
    """Referrer-Policy values."""
    NO_REFERRER = "no-referrer"
    NO_REFERRER_DOWNGRADE = "no-referrer-when-downgrade"
    ORIGIN = "origin"
    ORIGIN_CROSS = "origin-when-cross-origin"
    SAME_ORIGIN = "same-origin"
    STRICT_ORIGIN = "strict-origin"
    STRICT_ORIGIN_CROSS = "strict-origin-when-cross-origin"
    UNSAFE_URL = "unsafe-url"


class CSPDirective(str, Enum):
    """CSP directive names."""
    DEFAULT_SRC = "default-src"
    SCRIPT_SRC = "script-src"
    STYLE_SRC = "style-src"
    IMG_SRC = "img-src"
    FONT_SRC = "font-src"
    CONNECT_SRC = "connect-src"
    MEDIA_SRC = "media-src"
    OBJECT_SRC = "object-src"
    FRAME_SRC = "frame-src"
    FRAME_ANCESTORS = "frame-ancestors"
    FORM_ACTION = "form-action"
    BASE_URI = "base-uri"
    REPORT_URI = "report-uri"
    REPORT_TO = "report-to"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CSPConfig:
    """Content-Security-Policy configuration."""
    directives: Dict[str, List[str]] = field(default_factory=lambda: {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
    })
    report_uri: Optional[str] = None
    report_only: bool = False
    
    def to_header_value(self) -> str:
        """Convert to header value string."""
        parts = []
        for directive, sources in self.directives.items():
            parts.append(f"{directive} {' '.join(sources)}")
        
        if self.report_uri:
            parts.append(f"report-uri {self.report_uri}")
        
        return "; ".join(parts)


@dataclass
class HSTSConfig:
    """HTTP Strict Transport Security configuration."""
    max_age: int = 31536000  # 1 year
    include_subdomains: bool = True
    preload: bool = False
    
    def to_header_value(self) -> str:
        """Convert to header value string."""
        value = f"max-age={self.max_age}"
        if self.include_subdomains:
            value += "; includeSubDomains"
        if self.preload:
            value += "; preload"
        return value


@dataclass
class PermissionsPolicyConfig:
    """Permissions-Policy configuration."""
    policies: Dict[str, List[str]] = field(default_factory=lambda: {
        "geolocation": [],
        "microphone": [],
        "camera": [],
        "payment": [],
        "usb": [],
        "magnetometer": [],
        "gyroscope": [],
        "accelerometer": [],
    })
    
    def to_header_value(self) -> str:
        """Convert to header value string."""
        parts = []
        for feature, allowlist in self.policies.items():
            if not allowlist:
                parts.append(f"{feature}=()")
            else:
                parts.append(f"{feature}=({' '.join(allowlist)})")
        return ", ".join(parts)


@dataclass
class SecurityHeadersConfig:
    """Complete security headers configuration."""
    csp: CSPConfig = field(default_factory=CSPConfig)
    hsts: HSTSConfig = field(default_factory=HSTSConfig)
    permissions: PermissionsPolicyConfig = field(default_factory=PermissionsPolicyConfig)
    frame_options: FrameOption = FrameOption.DENY
    frame_options_uri: Optional[str] = None
    content_type_nosniff: bool = True
    xss_protection: bool = True
    xss_protection_block: bool = True
    referrer_policy: ReferrerPolicy = ReferrerPolicy.STRICT_ORIGIN_CROSS
    
    # Feature flags
    enable_csp: bool = True
    enable_hsts: bool = True
    enable_permissions: bool = True


# =============================================================================
# Security Headers Builder
# =============================================================================

class SecurityHeadersBuilder:
    """
    Builds security headers from configuration.
    
    Features:
    - Configurable header generation
    - Safe defaults
    - Header validation
    """
    
    def __init__(self, config: Optional[SecurityHeadersConfig] = None):
        """Initialize builder."""
        self.config = config or SecurityHeadersConfig()
    
    def build(self) -> Dict[str, str]:
        """Build all security headers."""
        headers: Dict[str, str] = {}
        
        # Content-Security-Policy
        if self.config.enable_csp:
            header_name = (
                "Content-Security-Policy-Report-Only"
                if self.config.csp.report_only
                else "Content-Security-Policy"
            )
            headers[header_name] = self.config.csp.to_header_value()
        
        # X-Frame-Options
        if self.config.frame_options == FrameOption.ALLOW_FROM:
            if self.config.frame_options_uri:
                headers["X-Frame-Options"] = (
                    f"ALLOW-FROM {self.config.frame_options_uri}"
                )
        else:
            headers["X-Frame-Options"] = self.config.frame_options.value
        
        # X-Content-Type-Options
        if self.config.content_type_nosniff:
            headers["X-Content-Type-Options"] = "nosniff"
        
        # X-XSS-Protection
        if self.config.xss_protection:
            value = "1"
            if self.config.xss_protection_block:
                value += "; mode=block"
            headers["X-XSS-Protection"] = value
        
        # Strict-Transport-Security
        if self.config.enable_hsts:
            headers["Strict-Transport-Security"] = (
                self.config.hsts.to_header_value()
            )
        
        # Referrer-Policy
        headers["Referrer-Policy"] = self.config.referrer_policy.value
        
        # Permissions-Policy
        if self.config.enable_permissions:
            headers["Permissions-Policy"] = (
                self.config.permissions.to_header_value()
            )
        
        return headers
    
    def build_csp(self) -> str:
        """Build CSP header value only."""
        return self.config.csp.to_header_value()
    
    def build_hsts(self) -> str:
        """Build HSTS header value only."""
        return self.config.hsts.to_header_value()


# =============================================================================
# CSP Builder
# =============================================================================

class CSPBuilder:
    """
    Fluent builder for Content-Security-Policy.
    """
    
    def __init__(self):
        """Initialize builder."""
        self._directives: Dict[str, List[str]] = {}
        self._report_uri: Optional[str] = None
        self._report_only: bool = False
    
    def default_src(self, *sources: str) -> "CSPBuilder":
        """Set default-src directive."""
        self._directives["default-src"] = list(sources)
        return self
    
    def script_src(self, *sources: str) -> "CSPBuilder":
        """Set script-src directive."""
        self._directives["script-src"] = list(sources)
        return self
    
    def style_src(self, *sources: str) -> "CSPBuilder":
        """Set style-src directive."""
        self._directives["style-src"] = list(sources)
        return self
    
    def img_src(self, *sources: str) -> "CSPBuilder":
        """Set img-src directive."""
        self._directives["img-src"] = list(sources)
        return self
    
    def font_src(self, *sources: str) -> "CSPBuilder":
        """Set font-src directive."""
        self._directives["font-src"] = list(sources)
        return self
    
    def connect_src(self, *sources: str) -> "CSPBuilder":
        """Set connect-src directive."""
        self._directives["connect-src"] = list(sources)
        return self
    
    def frame_ancestors(self, *sources: str) -> "CSPBuilder":
        """Set frame-ancestors directive."""
        self._directives["frame-ancestors"] = list(sources)
        return self
    
    def form_action(self, *sources: str) -> "CSPBuilder":
        """Set form-action directive."""
        self._directives["form-action"] = list(sources)
        return self
    
    def base_uri(self, *sources: str) -> "CSPBuilder":
        """Set base-uri directive."""
        self._directives["base-uri"] = list(sources)
        return self
    
    def object_src(self, *sources: str) -> "CSPBuilder":
        """Set object-src directive."""
        self._directives["object-src"] = list(sources)
        return self
    
    def report_uri(self, uri: str) -> "CSPBuilder":
        """Set report-uri."""
        self._report_uri = uri
        return self
    
    def report_only(self, enabled: bool = True) -> "CSPBuilder":
        """Set report-only mode."""
        self._report_only = enabled
        return self
    
    def add_nonce(self, nonce: str) -> "CSPBuilder":
        """Add nonce to script-src and style-src."""
        nonce_value = f"'nonce-{nonce}'"
        
        if "script-src" not in self._directives:
            self._directives["script-src"] = ["'self'"]
        self._directives["script-src"].append(nonce_value)
        
        if "style-src" not in self._directives:
            self._directives["style-src"] = ["'self'"]
        self._directives["style-src"].append(nonce_value)
        
        return self
    
    def build(self) -> CSPConfig:
        """Build CSP configuration."""
        return CSPConfig(
            directives=self._directives.copy(),
            report_uri=self._report_uri,
            report_only=self._report_only,
        )
    
    def to_header_value(self) -> str:
        """Build and return header value."""
        return self.build().to_header_value()


# =============================================================================
# Header Validator
# =============================================================================

class HeaderValidator:
    """
    Validates security headers for common issues.
    """
    
    UNSAFE_CSP_VALUES = ["'unsafe-inline'", "'unsafe-eval'", "*"]
    
    def __init__(self):
        """Initialize validator."""
        self._warnings: List[str] = []
    
    def validate(self, headers: Dict[str, str]) -> List[str]:
        """
        Validate headers for security issues.
        
        Returns:
            List of warning messages
        """
        self._warnings = []
        
        self._validate_csp(headers)
        self._validate_frame_options(headers)
        self._validate_hsts(headers)
        
        return self._warnings
    
    def _validate_csp(self, headers: Dict[str, str]) -> None:
        """Validate CSP header."""
        csp = headers.get("Content-Security-Policy", "")
        
        if not csp:
            self._warnings.append("Missing Content-Security-Policy header")
            return
        
        for unsafe in self.UNSAFE_CSP_VALUES:
            if unsafe in csp:
                self._warnings.append(
                    f"CSP contains unsafe value: {unsafe}"
                )
        
        if "default-src" not in csp:
            self._warnings.append("CSP missing default-src directive")
    
    def _validate_frame_options(self, headers: Dict[str, str]) -> None:
        """Validate X-Frame-Options header."""
        frame_opts = headers.get("X-Frame-Options", "")
        
        if not frame_opts:
            self._warnings.append("Missing X-Frame-Options header")
    
    def _validate_hsts(self, headers: Dict[str, str]) -> None:
        """Validate HSTS header."""
        hsts = headers.get("Strict-Transport-Security", "")
        
        if not hsts:
            self._warnings.append("Missing Strict-Transport-Security header")
            return
        
        if "max-age=0" in hsts:
            self._warnings.append("HSTS max-age is 0 (disabled)")


# =============================================================================
# Middleware
# =============================================================================

class SecurityHeadersMiddleware:
    """
    Middleware that adds security headers to responses.
    """
    
    def __init__(
        self,
        config: Optional[SecurityHeadersConfig] = None,
        exclude_paths: Optional[Set[str]] = None,
    ):
        """Initialize middleware."""
        self.config = config or SecurityHeadersConfig()
        self.builder = SecurityHeadersBuilder(self.config)
        self.exclude_paths = exclude_paths or set()
        self._headers = self.builder.build()
    
    def process_response(
        self,
        path: str,
        response_headers: Dict[str, str],
    ) -> Dict[str, str]:
        """
        Add security headers to response.
        
        Args:
            path: Request path
            response_headers: Existing response headers
            
        Returns:
            Updated headers dict
        """
        if path in self.exclude_paths:
            return response_headers
        
        # Merge security headers (don't override existing)
        result = response_headers.copy()
        for header, value in self._headers.items():
            if header not in result:
                result[header] = value
        
        return result
    
    def get_headers(self) -> Dict[str, str]:
        """Get all security headers."""
        return self._headers.copy()


# =============================================================================
# Service
# =============================================================================

class SecurityHeadersService:
    """
    High-level service for security headers.
    """
    
    _instance: Optional["SecurityHeadersService"] = None
    
    def __init__(self, config: Optional[SecurityHeadersConfig] = None):
        """Initialize service."""
        self.config = config or SecurityHeadersConfig()
        self.builder = SecurityHeadersBuilder(self.config)
        self.validator = HeaderValidator()
        self.middleware = SecurityHeadersMiddleware(self.config)
    
    @classmethod
    def get_instance(cls) -> "SecurityHeadersService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: SecurityHeadersConfig) -> "SecurityHeadersService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def get_headers(self) -> Dict[str, str]:
        """Get all security headers."""
        return self.builder.build()
    
    def validate_headers(self, headers: Dict[str, str]) -> List[str]:
        """Validate headers."""
        return self.validator.validate(headers)
    
    def create_csp_builder(self) -> CSPBuilder:
        """Create a CSP builder."""
        return CSPBuilder()
    
    def apply_to_response(
        self,
        path: str,
        headers: Dict[str, str],
    ) -> Dict[str, str]:
        """Apply security headers to response."""
        return self.middleware.process_response(path, headers)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_security_headers_service() -> SecurityHeadersService:
    """Get the global security headers service."""
    return SecurityHeadersService.get_instance()


def get_default_headers() -> Dict[str, str]:
    """Get default security headers."""
    return get_security_headers_service().get_headers()


def create_csp(
    default_src: str = "'self'",
    script_src: Optional[str] = None,
    style_src: Optional[str] = None,
) -> str:
    """Create a simple CSP header value."""
    builder = CSPBuilder().default_src(default_src)
    
    if script_src:
        builder.script_src(script_src)
    if style_src:
        builder.style_src(style_src)
    
    return builder.to_header_value()
