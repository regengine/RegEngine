"""
SEC-029: CORS Configuration.

Provides secure Cross-Origin Resource Sharing (CORS) configuration:
- Origin validation
- Allowed methods and headers
- Credentials handling
- Preflight request handling
- Origin whitelisting/blacklisting
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Pattern
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class CORSMode(str, Enum):
    """CORS handling mode."""
    DISABLED = "disabled"
    PERMISSIVE = "permissive"  # Allow all origins
    STRICT = "strict"  # Only allow whitelisted origins
    REFLECT = "reflect"  # Reflect origin (dangerous, for dev only)


class CredentialsMode(str, Enum):
    """Credentials handling mode."""
    OMIT = "omit"  # Never send credentials
    SAME_ORIGIN = "same-origin"  # Only for same-origin requests
    INCLUDE = "include"  # Always include credentials


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CORSConfig:
    """CORS configuration."""
    mode: CORSMode = CORSMode.STRICT
    allowed_origins: Set[str] = field(default_factory=set)
    allowed_origin_patterns: List[str] = field(default_factory=list)
    allowed_methods: Set[str] = field(default_factory=lambda: {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"})
    allowed_headers: Set[str] = field(default_factory=lambda: {"Content-Type", "Authorization", "X-Requested-With"})
    exposed_headers: Set[str] = field(default_factory=set)
    credentials: CredentialsMode = CredentialsMode.SAME_ORIGIN
    max_age: int = 86400  # Preflight cache time in seconds (24 hours)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "allowed_origins": list(self.allowed_origins),
            "allowed_origin_patterns": self.allowed_origin_patterns,
            "allowed_methods": list(self.allowed_methods),
            "allowed_headers": list(self.allowed_headers),
            "exposed_headers": list(self.exposed_headers),
            "credentials": self.credentials.value,
            "max_age": self.max_age,
        }


@dataclass
class CORSRequest:
    """Parsed CORS request information."""
    origin: Optional[str] = None
    method: str = "GET"
    request_method: Optional[str] = None  # For preflight
    request_headers: Set[str] = field(default_factory=set)
    is_preflight: bool = False
    is_cors: bool = False
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str], method: str = "GET") -> "CORSRequest":
        """
        Create from request headers.
        
        Args:
            headers: Request headers (case-insensitive keys)
            method: HTTP method
            
        Returns:
            CORSRequest
        """
        # Normalize headers to lowercase
        normalized = {k.lower(): v for k, v in headers.items()}
        
        origin = normalized.get("origin")
        is_cors = origin is not None
        
        # Check if preflight
        is_preflight = (
            method.upper() == "OPTIONS" and
            is_cors and
            "access-control-request-method" in normalized
        )
        
        request_method = normalized.get("access-control-request-method")
        
        request_headers_str = normalized.get("access-control-request-headers", "")
        request_headers = {
            h.strip() for h in request_headers_str.split(",") if h.strip()
        }
        
        return cls(
            origin=origin,
            method=method,
            request_method=request_method,
            request_headers=request_headers,
            is_preflight=is_preflight,
            is_cors=is_cors,
        )


@dataclass
class CORSResponse:
    """CORS response headers."""
    allow_origin: Optional[str] = None
    allow_methods: Optional[str] = None
    allow_headers: Optional[str] = None
    allow_credentials: Optional[str] = None
    expose_headers: Optional[str] = None
    max_age: Optional[str] = None
    vary: str = "Origin"
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to response headers."""
        headers = {}
        
        if self.allow_origin:
            headers["Access-Control-Allow-Origin"] = self.allow_origin
        if self.allow_methods:
            headers["Access-Control-Allow-Methods"] = self.allow_methods
        if self.allow_headers:
            headers["Access-Control-Allow-Headers"] = self.allow_headers
        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = self.allow_credentials
        if self.expose_headers:
            headers["Access-Control-Expose-Headers"] = self.expose_headers
        if self.max_age:
            headers["Access-Control-Max-Age"] = self.max_age
        
        headers["Vary"] = self.vary
        
        return headers


@dataclass
class CORSValidationResult:
    """Result of CORS validation."""
    allowed: bool
    response: CORSResponse
    error: Optional[str] = None


# =============================================================================
# CORS Validator
# =============================================================================

class CORSValidator:
    """
    Validates and handles CORS requests.
    
    Features:
    - Origin validation (exact match and patterns)
    - Preflight request handling
    - Header and method validation
    - Credentials handling
    """
    
    def __init__(self, config: Optional[CORSConfig] = None):
        """Initialize validator."""
        self.config = config or CORSConfig()
        self._compiled_patterns: List[Pattern] = []
        self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Compile origin patterns to regex."""
        self._compiled_patterns = []
        for pattern in self.config.allowed_origin_patterns:
            try:
                # Convert wildcard pattern to regex
                regex = pattern.replace(".", r"\.").replace("*", ".*")
                self._compiled_patterns.append(re.compile(f"^{regex}$", re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid origin pattern '{pattern}': {e}")
    
    def add_origin(self, origin: str) -> None:
        """Add allowed origin."""
        self.config.allowed_origins.add(origin)
    
    def add_pattern(self, pattern: str) -> None:
        """Add allowed origin pattern."""
        self.config.allowed_origin_patterns.append(pattern)
        self._compile_patterns()
    
    def remove_origin(self, origin: str) -> None:
        """Remove allowed origin."""
        self.config.allowed_origins.discard(origin)
    
    def is_origin_allowed(self, origin: str) -> bool:
        """
        Check if origin is allowed.
        
        Args:
            origin: Origin to check
            
        Returns:
            True if allowed
        """
        if self.config.mode == CORSMode.DISABLED:
            return False
        
        if self.config.mode == CORSMode.PERMISSIVE:
            return True
        
        if self.config.mode == CORSMode.REFLECT:
            return True
        
        # Strict mode - check whitelist
        if origin in self.config.allowed_origins:
            return True
        
        # Check patterns
        for pattern in self._compiled_patterns:
            if pattern.match(origin):
                return True
        
        return False
    
    def is_method_allowed(self, method: str) -> bool:
        """Check if method is allowed."""
        return method.upper() in self.config.allowed_methods
    
    def are_headers_allowed(self, headers: Set[str]) -> bool:
        """Check if all headers are allowed."""
        # Normalize to lowercase for comparison
        allowed = {h.lower() for h in self.config.allowed_headers}
        requested = {h.lower() for h in headers}
        return requested.issubset(allowed)
    
    def validate_request(self, request: CORSRequest) -> CORSValidationResult:
        """
        Validate CORS request.
        
        Args:
            request: CORS request
            
        Returns:
            CORSValidationResult
        """
        # Non-CORS requests are always allowed
        if not request.is_cors:
            return CORSValidationResult(
                allowed=True,
                response=CORSResponse(),
            )
        
        # Check origin
        if not self.is_origin_allowed(request.origin):
            return CORSValidationResult(
                allowed=False,
                response=CORSResponse(vary="Origin"),
                error=f"Origin '{request.origin}' not allowed",
            )
        
        # Handle preflight
        if request.is_preflight:
            return self._handle_preflight(request)
        
        # Regular CORS request
        return self._handle_cors_request(request)
    
    def _handle_preflight(self, request: CORSRequest) -> CORSValidationResult:
        """Handle preflight request."""
        # Check requested method
        if request.request_method and not self.is_method_allowed(request.request_method):
            return CORSValidationResult(
                allowed=False,
                response=CORSResponse(vary="Origin"),
                error=f"Method '{request.request_method}' not allowed",
            )
        
        # Check requested headers
        if request.request_headers and not self.are_headers_allowed(request.request_headers):
            return CORSValidationResult(
                allowed=False,
                response=CORSResponse(vary="Origin"),
                error=f"Some requested headers not allowed",
            )
        
        # Build response
        allow_origin = self._get_allow_origin(request.origin)
        
        response = CORSResponse(
            allow_origin=allow_origin,
            allow_methods=", ".join(sorted(self.config.allowed_methods)),
            allow_headers=", ".join(sorted(self.config.allowed_headers)),
            max_age=str(self.config.max_age),
            vary="Origin",
        )
        
        if self.config.credentials == CredentialsMode.INCLUDE:
            response.allow_credentials = "true"
        
        return CORSValidationResult(allowed=True, response=response)
    
    def _handle_cors_request(self, request: CORSRequest) -> CORSValidationResult:
        """Handle regular CORS request."""
        allow_origin = self._get_allow_origin(request.origin)
        
        response = CORSResponse(
            allow_origin=allow_origin,
            vary="Origin",
        )
        
        if self.config.credentials == CredentialsMode.INCLUDE:
            response.allow_credentials = "true"
        
        if self.config.exposed_headers:
            response.expose_headers = ", ".join(sorted(self.config.exposed_headers))
        
        return CORSValidationResult(allowed=True, response=response)
    
    def _get_allow_origin(self, origin: str) -> str:
        """Get Allow-Origin header value."""
        if self.config.mode == CORSMode.PERMISSIVE:
            # Cannot use "*" with credentials
            if self.config.credentials == CredentialsMode.INCLUDE:
                return origin
            return "*"
        
        if self.config.mode == CORSMode.REFLECT:
            return origin
        
        # Strict mode - return the specific origin
        return origin


# =============================================================================
# CORS Middleware
# =============================================================================

class CORSMiddleware:
    """
    CORS middleware for request handling.
    
    Can be integrated with various frameworks.
    """
    
    def __init__(self, config: Optional[CORSConfig] = None):
        """Initialize middleware."""
        self.validator = CORSValidator(config)
    
    def process_request(
        self,
        method: str,
        headers: Dict[str, str],
    ) -> tuple[bool, Dict[str, str], Optional[str]]:
        """
        Process a request for CORS.
        
        Args:
            method: HTTP method
            headers: Request headers
            
        Returns:
            Tuple of (should_continue, response_headers, error)
        """
        request = CORSRequest.from_headers(headers, method)
        result = self.validator.validate_request(request)
        
        response_headers = result.response.to_headers()
        
        if not result.allowed:
            return False, response_headers, result.error
        
        # For preflight, request handling should stop
        if request.is_preflight:
            return False, response_headers, None
        
        return True, response_headers, None


# =============================================================================
# CORS Policy Builder
# =============================================================================

class CORSPolicyBuilder:
    """
    Builder for CORS configuration.
    
    Provides a fluent interface for creating CORS configs.
    """
    
    def __init__(self):
        """Initialize builder."""
        self._config = CORSConfig()
    
    def mode(self, mode: CORSMode) -> "CORSPolicyBuilder":
        """Set CORS mode."""
        self._config.mode = mode
        return self
    
    def allow_origin(self, origin: str) -> "CORSPolicyBuilder":
        """Add allowed origin."""
        self._config.allowed_origins.add(origin)
        return self
    
    def allow_origins(self, origins: List[str]) -> "CORSPolicyBuilder":
        """Add multiple allowed origins."""
        self._config.allowed_origins.update(origins)
        return self
    
    def allow_origin_pattern(self, pattern: str) -> "CORSPolicyBuilder":
        """Add allowed origin pattern."""
        self._config.allowed_origin_patterns.append(pattern)
        return self
    
    def allow_method(self, method: str) -> "CORSPolicyBuilder":
        """Add allowed method."""
        self._config.allowed_methods.add(method.upper())
        return self
    
    def allow_methods(self, methods: List[str]) -> "CORSPolicyBuilder":
        """Set allowed methods."""
        self._config.allowed_methods = {m.upper() for m in methods}
        return self
    
    def allow_header(self, header: str) -> "CORSPolicyBuilder":
        """Add allowed header."""
        self._config.allowed_headers.add(header)
        return self
    
    def allow_headers(self, headers: List[str]) -> "CORSPolicyBuilder":
        """Set allowed headers."""
        self._config.allowed_headers = set(headers)
        return self
    
    def expose_header(self, header: str) -> "CORSPolicyBuilder":
        """Add exposed header."""
        self._config.exposed_headers.add(header)
        return self
    
    def expose_headers(self, headers: List[str]) -> "CORSPolicyBuilder":
        """Set exposed headers."""
        self._config.exposed_headers = set(headers)
        return self
    
    def allow_credentials(self) -> "CORSPolicyBuilder":
        """Enable credentials."""
        self._config.credentials = CredentialsMode.INCLUDE
        return self
    
    def max_age(self, seconds: int) -> "CORSPolicyBuilder":
        """Set preflight cache time."""
        self._config.max_age = seconds
        return self
    
    def build(self) -> CORSConfig:
        """Build configuration."""
        return self._config


# =============================================================================
# Predefined Policies
# =============================================================================

def strict_cors_policy(allowed_origins: List[str]) -> CORSConfig:
    """
    Create a strict CORS policy.
    
    Only allows specified origins with limited methods.
    """
    return (
        CORSPolicyBuilder()
        .mode(CORSMode.STRICT)
        .allow_origins(allowed_origins)
        .allow_methods(["GET", "POST", "PUT", "DELETE"])
        .allow_headers(["Content-Type", "Authorization"])
        .max_age(3600)
        .build()
    )


def permissive_cors_policy() -> CORSConfig:
    """
    Create a permissive CORS policy.
    
    WARNING: Only use in development!
    """
    return (
        CORSPolicyBuilder()
        .mode(CORSMode.PERMISSIVE)
        .allow_methods(["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
        .allow_headers(["*"])
        .build()
    )


def api_cors_policy(
    allowed_origins: List[str],
    allow_credentials: bool = False,
) -> CORSConfig:
    """
    Create an API-friendly CORS policy.
    
    Suitable for REST APIs.
    """
    builder = (
        CORSPolicyBuilder()
        .mode(CORSMode.STRICT)
        .allow_origins(allowed_origins)
        .allow_methods(["GET", "POST", "PUT", "DELETE", "PATCH"])
        .allow_headers(["Content-Type", "Authorization", "X-RegEngine-API-Key", "X-Request-ID"])
        .expose_headers(["X-Request-ID", "X-Rate-Limit-Remaining"])
        .max_age(86400)
    )
    
    if allow_credentials:
        builder.allow_credentials()
    
    return builder.build()


# =============================================================================
# CORS Service
# =============================================================================

class CORSService:
    """
    High-level CORS service.
    
    Manages CORS configuration and provides utilities.
    """
    
    _instance: Optional["CORSService"] = None
    
    def __init__(self, config: Optional[CORSConfig] = None):
        """Initialize service."""
        self.config = config or CORSConfig()
        self.validator = CORSValidator(self.config)
        self.middleware = CORSMiddleware(self.config)
    
    @classmethod
    def get_instance(cls) -> "CORSService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: CORSConfig) -> "CORSService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def add_origin(self, origin: str) -> None:
        """Add allowed origin."""
        self.validator.add_origin(origin)
    
    def remove_origin(self, origin: str) -> None:
        """Remove allowed origin."""
        self.validator.remove_origin(origin)
    
    def check_origin(self, origin: str) -> bool:
        """Check if origin is allowed."""
        return self.validator.is_origin_allowed(origin)
    
    def process_request(
        self,
        method: str,
        headers: Dict[str, str],
    ) -> tuple[bool, Dict[str, str], Optional[str]]:
        """Process request for CORS."""
        return self.middleware.process_request(method, headers)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_cors_service() -> CORSService:
    """Get the global CORS service."""
    return CORSService.get_instance()


def check_cors_origin(origin: str) -> bool:
    """Check if origin is allowed."""
    return get_cors_service().check_origin(origin)
