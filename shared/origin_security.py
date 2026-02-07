"""
SEC-040: Request Origin Validation.

Provides request origin validation:
- Origin header validation
- Referer header validation
- CORS preflight handling
- Domain whitelist management
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse


# =============================================================================
# Enums
# =============================================================================

class OriginValidationResult(str, Enum):
    """Origin validation results."""
    VALID = "valid"
    MISSING_ORIGIN = "missing_origin"
    INVALID_ORIGIN = "invalid_origin"
    BLOCKED_ORIGIN = "blocked_origin"
    INVALID_FORMAT = "invalid_format"


class CORSMode(str, Enum):
    """CORS handling modes."""
    DISABLED = "disabled"
    ALLOW_ALL = "allow_all"
    WHITELIST = "whitelist"
    SAME_ORIGIN = "same_origin"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OriginConfig:
    """Origin validation configuration."""
    allowed_origins: Set[str] = field(default_factory=set)
    blocked_origins: Set[str] = field(default_factory=set)
    allow_subdomains: bool = False
    cors_mode: CORSMode = CORSMode.WHITELIST
    allow_null_origin: bool = False
    require_origin_header: bool = True
    fallback_to_referer: bool = True


@dataclass
class CORSConfig:
    """CORS configuration."""
    allowed_methods: Set[str] = field(default_factory=lambda: {
        "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"
    })
    allowed_headers: Set[str] = field(default_factory=lambda: {
        "Content-Type", "Authorization", "X-Requested-With"
    })
    exposed_headers: Set[str] = field(default_factory=set)
    allow_credentials: bool = False
    max_age: int = 86400  # 24 hours


@dataclass
class OriginValidation:
    """Result of origin validation."""
    is_valid: bool
    result: OriginValidationResult
    origin: str
    message: str = ""


@dataclass
class CORSHeaders:
    """CORS response headers."""
    access_control_allow_origin: Optional[str] = None
    access_control_allow_methods: Optional[str] = None
    access_control_allow_headers: Optional[str] = None
    access_control_expose_headers: Optional[str] = None
    access_control_allow_credentials: Optional[str] = None
    access_control_max_age: Optional[str] = None
    vary: str = "Origin"
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to header dict."""
        headers = {}
        
        if self.access_control_allow_origin:
            headers["Access-Control-Allow-Origin"] = self.access_control_allow_origin
        if self.access_control_allow_methods:
            headers["Access-Control-Allow-Methods"] = self.access_control_allow_methods
        if self.access_control_allow_headers:
            headers["Access-Control-Allow-Headers"] = self.access_control_allow_headers
        if self.access_control_expose_headers:
            headers["Access-Control-Expose-Headers"] = self.access_control_expose_headers
        if self.access_control_allow_credentials:
            headers["Access-Control-Allow-Credentials"] = self.access_control_allow_credentials
        if self.access_control_max_age:
            headers["Access-Control-Max-Age"] = self.access_control_max_age
        if self.vary:
            headers["Vary"] = self.vary
        
        return headers


# =============================================================================
# Origin Validator
# =============================================================================

class OriginValidator:
    """
    Validates request origins for security.
    """
    
    def __init__(self, config: Optional[OriginConfig] = None):
        """Initialize validator."""
        self.config = config or OriginConfig()
    
    def validate(
        self,
        origin: Optional[str],
        referer: Optional[str] = None,
    ) -> OriginValidation:
        """
        Validate request origin.
        
        Args:
            origin: Origin header value
            referer: Referer header value (fallback)
            
        Returns:
            OriginValidation result
        """
        # Try to get origin from headers
        effective_origin = origin
        
        if not effective_origin and self.config.fallback_to_referer and referer:
            # Extract origin from referer
            effective_origin = self._extract_origin(referer)
        
        # Check if origin is required
        if not effective_origin:
            if self.config.require_origin_header:
                return OriginValidation(
                    is_valid=False,
                    result=OriginValidationResult.MISSING_ORIGIN,
                    origin="",
                    message="Origin header is required",
                )
            else:
                return OriginValidation(
                    is_valid=True,
                    result=OriginValidationResult.VALID,
                    origin="",
                    message="Origin not required",
                )
        
        # Handle null origin
        if effective_origin.lower() == "null":
            if self.config.allow_null_origin:
                return OriginValidation(
                    is_valid=True,
                    result=OriginValidationResult.VALID,
                    origin="null",
                    message="Null origin allowed",
                )
            else:
                return OriginValidation(
                    is_valid=False,
                    result=OriginValidationResult.INVALID_ORIGIN,
                    origin="null",
                    message="Null origin not allowed",
                )
        
        # Validate origin format
        if not self._is_valid_origin_format(effective_origin):
            return OriginValidation(
                is_valid=False,
                result=OriginValidationResult.INVALID_FORMAT,
                origin=effective_origin,
                message="Invalid origin format",
            )
        
        # Check CORS mode
        if self.config.cors_mode == CORSMode.ALLOW_ALL:
            return OriginValidation(
                is_valid=True,
                result=OriginValidationResult.VALID,
                origin=effective_origin,
                message="All origins allowed",
            )
        
        # Check blocked list
        if self._is_blocked(effective_origin):
            return OriginValidation(
                is_valid=False,
                result=OriginValidationResult.BLOCKED_ORIGIN,
                origin=effective_origin,
                message="Origin is blocked",
            )
        
        # Check allowed list
        if self._is_allowed(effective_origin):
            return OriginValidation(
                is_valid=True,
                result=OriginValidationResult.VALID,
                origin=effective_origin,
                message="Origin is allowed",
            )
        
        return OriginValidation(
            is_valid=False,
            result=OriginValidationResult.INVALID_ORIGIN,
            origin=effective_origin,
            message="Origin not in allowed list",
        )
    
    def _extract_origin(self, url: str) -> str:
        """Extract origin from URL."""
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                port_part = ""
                if parsed.port and parsed.port not in (80, 443):
                    port_part = f":{parsed.port}"
                return f"{parsed.scheme}://{parsed.hostname}{port_part}"
        except Exception:
            pass
        return ""
    
    def _is_valid_origin_format(self, origin: str) -> bool:
        """Check if origin has valid format."""
        try:
            parsed = urlparse(origin)
            return bool(parsed.scheme and parsed.netloc)
        except Exception:
            return False
    
    def _is_blocked(self, origin: str) -> bool:
        """Check if origin is blocked."""
        origin_lower = origin.lower()
        
        for blocked in self.config.blocked_origins:
            if blocked.lower() == origin_lower:
                return True
            
            # Check subdomain
            if self.config.allow_subdomains:
                parsed = urlparse(origin)
                blocked_parsed = urlparse(blocked)
                if parsed.hostname and blocked_parsed.hostname:
                    if parsed.hostname.endswith(f".{blocked_parsed.hostname}"):
                        return True
        
        return False
    
    def _is_allowed(self, origin: str) -> bool:
        """Check if origin is allowed."""
        origin_lower = origin.lower()
        
        for allowed in self.config.allowed_origins:
            if allowed.lower() == origin_lower:
                return True
            
            # Check subdomain
            if self.config.allow_subdomains:
                parsed = urlparse(origin)
                allowed_parsed = urlparse(allowed)
                if parsed.hostname and allowed_parsed.hostname:
                    if parsed.hostname.endswith(f".{allowed_parsed.hostname}"):
                        return True
        
        return False


# =============================================================================
# CORS Handler
# =============================================================================

class CORSHandler:
    """
    Handles CORS preflight and response headers.
    """
    
    def __init__(
        self,
        origin_config: Optional[OriginConfig] = None,
        cors_config: Optional[CORSConfig] = None,
    ):
        """Initialize handler."""
        self.origin_config = origin_config or OriginConfig()
        self.cors_config = cors_config or CORSConfig()
        self.origin_validator = OriginValidator(self.origin_config)
    
    def handle_preflight(
        self,
        origin: Optional[str],
        request_method: Optional[str] = None,
        request_headers: Optional[str] = None,
    ) -> Tuple[bool, CORSHeaders]:
        """
        Handle CORS preflight request.
        
        Args:
            origin: Origin header
            request_method: Access-Control-Request-Method header
            request_headers: Access-Control-Request-Headers header
            
        Returns:
            Tuple of (is_allowed, cors_headers)
        """
        # Validate origin
        validation = self.origin_validator.validate(origin)
        
        if not validation.is_valid:
            return False, CORSHeaders()
        
        # Check requested method
        if request_method and request_method.upper() not in self.cors_config.allowed_methods:
            return False, CORSHeaders()
        
        # Build response headers
        headers = self._build_cors_headers(validation.origin, is_preflight=True)
        
        return True, headers
    
    def handle_request(
        self,
        origin: Optional[str],
    ) -> Tuple[bool, CORSHeaders]:
        """
        Handle CORS for actual request.
        
        Args:
            origin: Origin header
            
        Returns:
            Tuple of (is_allowed, cors_headers)
        """
        validation = self.origin_validator.validate(origin)
        
        if not validation.is_valid:
            return False, CORSHeaders()
        
        headers = self._build_cors_headers(validation.origin, is_preflight=False)
        
        return True, headers
    
    def _build_cors_headers(
        self,
        origin: str,
        is_preflight: bool = False,
    ) -> CORSHeaders:
        """Build CORS response headers."""
        headers = CORSHeaders()
        
        # Set origin
        if self.origin_config.cors_mode == CORSMode.ALLOW_ALL:
            headers.access_control_allow_origin = "*"
        else:
            headers.access_control_allow_origin = origin
        
        # Preflight-specific headers
        if is_preflight:
            headers.access_control_allow_methods = ", ".join(
                sorted(self.cors_config.allowed_methods)
            )
            headers.access_control_allow_headers = ", ".join(
                sorted(self.cors_config.allowed_headers)
            )
            headers.access_control_max_age = str(self.cors_config.max_age)
        
        # Exposed headers
        if self.cors_config.exposed_headers:
            headers.access_control_expose_headers = ", ".join(
                sorted(self.cors_config.exposed_headers)
            )
        
        # Credentials
        if self.cors_config.allow_credentials:
            headers.access_control_allow_credentials = "true"
        
        return headers


# =============================================================================
# Origin Security Service
# =============================================================================

class OriginSecurityService:
    """
    High-level service for origin security.
    """
    
    _instance: Optional["OriginSecurityService"] = None
    
    def __init__(
        self,
        origin_config: Optional[OriginConfig] = None,
        cors_config: Optional[CORSConfig] = None,
    ):
        """Initialize service."""
        self.origin_config = origin_config or OriginConfig()
        self.cors_config = cors_config or CORSConfig()
        self.validator = OriginValidator(self.origin_config)
        self.cors_handler = CORSHandler(self.origin_config, self.cors_config)
    
    @classmethod
    def get_instance(cls) -> "OriginSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        origin_config: OriginConfig,
        cors_config: Optional[CORSConfig] = None,
    ) -> "OriginSecurityService":
        """Configure the service."""
        cls._instance = cls(origin_config, cors_config)
        return cls._instance
    
    def validate_origin(
        self,
        origin: Optional[str],
        referer: Optional[str] = None,
    ) -> OriginValidation:
        """Validate request origin."""
        return self.validator.validate(origin, referer)
    
    def handle_preflight(
        self,
        origin: Optional[str],
        request_method: Optional[str] = None,
        request_headers: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, str]]:
        """Handle CORS preflight."""
        is_allowed, headers = self.cors_handler.handle_preflight(
            origin, request_method, request_headers
        )
        return is_allowed, headers.to_dict()
    
    def handle_cors(
        self,
        origin: Optional[str],
    ) -> Dict[str, str]:
        """Get CORS headers for request."""
        _, headers = self.cors_handler.handle_request(origin)
        return headers.to_dict()
    
    def add_allowed_origin(self, origin: str) -> None:
        """Add an allowed origin."""
        self.origin_config.allowed_origins.add(origin)
    
    def remove_allowed_origin(self, origin: str) -> None:
        """Remove an allowed origin."""
        self.origin_config.allowed_origins.discard(origin)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_origin_service() -> OriginSecurityService:
    """Get the global origin security service."""
    return OriginSecurityService.get_instance()


def validate_origin(origin: Optional[str]) -> bool:
    """Validate request origin."""
    result = get_origin_service().validate_origin(origin)
    return result.is_valid


def get_cors_headers(origin: Optional[str]) -> Dict[str, str]:
    """Get CORS headers for origin."""
    return get_origin_service().handle_cors(origin)
