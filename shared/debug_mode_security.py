"""
SEC-034: Debug Mode Security.

Provides security controls for debug mode:
- Debug mode detection
- Environment validation
- Debug endpoint protection
- Information disclosure prevention
"""

import logging
import os
import warnings
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class DebugLevel(str, Enum):
    """Debug levels."""
    DISABLED = "disabled"
    MINIMAL = "minimal"
    STANDARD = "standard"
    VERBOSE = "verbose"
    FULL = "full"


class Environment(str, Enum):
    """Deployment environments."""
    LOCAL = "local"
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DebugConfig:
    """Debug mode configuration."""
    enabled: bool = False
    level: DebugLevel = DebugLevel.DISABLED
    environment: Environment = Environment.PRODUCTION
    allowed_environments: Set[Environment] = field(default_factory=lambda: {
        Environment.LOCAL,
        Environment.DEVELOPMENT,
        Environment.TESTING,
    })
    allowed_ips: Set[str] = field(default_factory=lambda: {
        "127.0.0.1",
        "::1",
        "localhost",
    })
    require_auth: bool = True
    log_access: bool = True
    
    def is_debug_allowed(self) -> bool:
        """Check if debug is allowed in current environment."""
        return self.environment in self.allowed_environments


@dataclass
class DebugAccessAttempt:
    """Record of debug access attempt."""
    timestamp: str
    ip_address: str
    endpoint: str
    user_id: Optional[str]
    allowed: bool
    reason: str


# =============================================================================
# Debug Mode Detector
# =============================================================================

class DebugModeDetector:
    """
    Detects and validates debug mode settings.
    
    Features:
    - Environment variable detection
    - Framework detection
    - Configuration validation
    """
    
    DEBUG_ENV_VARS = [
        "DEBUG",
        "FLASK_DEBUG",
        "DJANGO_DEBUG",
        "APP_DEBUG",
        "ENABLE_DEBUG",
    ]
    
    PRODUCTION_INDICATORS = [
        "PRODUCTION",
        "PROD",
        "LIVE",
    ]
    
    def __init__(self):
        """Initialize detector."""
        self._warnings_issued: Set[str] = set()
    
    def detect_debug_mode(self) -> bool:
        """Detect if debug mode is enabled."""
        for var in self.DEBUG_ENV_VARS:
            value = os.environ.get(var, "").lower()
            if value in ("true", "1", "yes", "on"):
                return True
        return False
    
    def detect_environment(self) -> Environment:
        """Detect current environment."""
        env_value = os.environ.get("ENVIRONMENT", "").lower()
        
        if not env_value:
            env_value = os.environ.get("APP_ENV", "").lower()
        if not env_value:
            env_value = os.environ.get("NODE_ENV", "").lower()
        
        env_mapping = {
            "local": Environment.LOCAL,
            "dev": Environment.DEVELOPMENT,
            "development": Environment.DEVELOPMENT,
            "test": Environment.TESTING,
            "testing": Environment.TESTING,
            "staging": Environment.STAGING,
            "stage": Environment.STAGING,
            "prod": Environment.PRODUCTION,
            "production": Environment.PRODUCTION,
            "live": Environment.PRODUCTION,
        }
        
        return env_mapping.get(env_value, Environment.PRODUCTION)
    
    def is_production(self) -> bool:
        """Check if running in production."""
        env = self.detect_environment()
        return env == Environment.PRODUCTION
    
    def validate_debug_settings(self) -> List[str]:
        """
        Validate debug settings for security issues.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        if self.detect_debug_mode():
            if self.is_production():
                warnings.append(
                    "CRITICAL: Debug mode is enabled in production! "
                    "This exposes sensitive information."
                )
        
        # Check for common debug indicators in production
        if self.is_production():
            for var in self.DEBUG_ENV_VARS:
                value = os.environ.get(var, "").lower()
                if value in ("true", "1", "yes", "on"):
                    warnings.append(
                        f"WARNING: {var}={value} in production environment"
                    )
        
        return warnings
    
    def warn_if_debug_in_production(self) -> None:
        """Issue warnings if debug is enabled in production."""
        if self.is_production() and self.detect_debug_mode():
            warning_key = "debug_in_production"
            if warning_key not in self._warnings_issued:
                self._warnings_issued.add(warning_key)
                warnings.warn(
                    "Debug mode is enabled in production. "
                    "This may expose sensitive information.",
                    SecurityWarning,
                )


class SecurityWarning(UserWarning):
    """Security-related warning."""
    pass


# =============================================================================
# Debug Access Controller
# =============================================================================

class DebugAccessController:
    """
    Controls access to debug functionality.
    
    Features:
    - IP-based access control
    - Authentication requirements
    - Access logging
    """
    
    def __init__(self, config: Optional[DebugConfig] = None):
        """Initialize controller."""
        self.config = config or DebugConfig()
        self._access_log: List[DebugAccessAttempt] = []
    
    def is_access_allowed(
        self,
        ip_address: str,
        user_id: Optional[str] = None,
        endpoint: str = "",
    ) -> tuple[bool, str]:
        """
        Check if debug access is allowed.
        
        Args:
            ip_address: Client IP address
            user_id: User identifier
            endpoint: Debug endpoint being accessed
            
        Returns:
            Tuple of (allowed, reason)
        """
        # Check if debug is enabled
        if not self.config.enabled:
            return False, "Debug mode is disabled"
        
        # Check environment
        if not self.config.is_debug_allowed():
            return False, f"Debug not allowed in {self.config.environment.value} environment"
        
        # Check IP
        if self.config.allowed_ips and ip_address not in self.config.allowed_ips:
            return False, f"IP {ip_address} not in allowed list"
        
        # Check authentication
        if self.config.require_auth and not user_id:
            return False, "Authentication required for debug access"
        
        return True, "Access granted"
    
    def record_access(
        self,
        ip_address: str,
        endpoint: str,
        user_id: Optional[str],
        allowed: bool,
        reason: str,
    ) -> None:
        """Record access attempt."""
        from datetime import datetime, timezone
        
        attempt = DebugAccessAttempt(
            timestamp=datetime.now(timezone.utc).isoformat(),
            ip_address=ip_address,
            endpoint=endpoint,
            user_id=user_id,
            allowed=allowed,
            reason=reason,
        )
        
        self._access_log.append(attempt)
        
        if self.config.log_access:
            log_func = logger.info if allowed else logger.warning
            log_func(
                f"Debug access {'granted' if allowed else 'denied'}: "
                f"ip={ip_address}, endpoint={endpoint}, reason={reason}"
            )
    
    def get_access_log(self) -> List[DebugAccessAttempt]:
        """Get access log."""
        return self._access_log.copy()


# =============================================================================
# Debug Endpoint Guard
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


class DebugEndpointGuard:
    """
    Guards debug endpoints from unauthorized access.
    """
    
    def __init__(
        self,
        controller: Optional[DebugAccessController] = None,
    ):
        """Initialize guard."""
        self.controller = controller or DebugAccessController()
    
    def protect(
        self,
        get_ip: Optional[Callable[[], str]] = None,
        get_user: Optional[Callable[[], Optional[str]]] = None,
    ) -> Callable[[F], F]:
        """
        Decorator to protect debug endpoints.
        
        Args:
            get_ip: Function to get client IP
            get_user: Function to get current user
        """
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args, **kwargs):
                ip = get_ip() if get_ip else "unknown"
                user = get_user() if get_user else None
                endpoint = func.__name__
                
                allowed, reason = self.controller.is_access_allowed(
                    ip_address=ip,
                    user_id=user,
                    endpoint=endpoint,
                )
                
                self.controller.record_access(
                    ip_address=ip,
                    endpoint=endpoint,
                    user_id=user,
                    allowed=allowed,
                    reason=reason,
                )
                
                if not allowed:
                    raise DebugAccessDenied(reason)
                
                return func(*args, **kwargs)
            
            return wrapper  # type: ignore
        
        return decorator
    
    def check_access(
        self,
        ip_address: str,
        user_id: Optional[str] = None,
        endpoint: str = "",
    ) -> bool:
        """Check access without decorator."""
        allowed, reason = self.controller.is_access_allowed(
            ip_address=ip_address,
            user_id=user_id,
            endpoint=endpoint,
        )
        
        self.controller.record_access(
            ip_address=ip_address,
            endpoint=endpoint,
            user_id=user_id,
            allowed=allowed,
            reason=reason,
        )
        
        return allowed


class DebugAccessDenied(Exception):
    """Raised when debug access is denied."""
    pass


# =============================================================================
# Debug Information Filter
# =============================================================================

class DebugInfoFilter:
    """
    Filters debug information based on environment.
    """
    
    def __init__(self, config: Optional[DebugConfig] = None):
        """Initialize filter."""
        self.config = config or DebugConfig()
    
    def filter_response(
        self,
        data: Dict[str, Any],
        include_debug: bool = False,
    ) -> Dict[str, Any]:
        """
        Filter response data based on debug settings.
        
        Args:
            data: Response data
            include_debug: Whether to include debug info
            
        Returns:
            Filtered data
        """
        if not include_debug or not self.config.enabled:
            return self._remove_debug_fields(data)
        
        if not self.config.is_debug_allowed():
            return self._remove_debug_fields(data)
        
        return data
    
    def _remove_debug_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove debug-related fields."""
        debug_fields = {
            "debug",
            "debug_info",
            "stack_trace",
            "internal_error",
            "query",
            "sql",
            "execution_time_ms",
            "memory_usage",
            "cache_hits",
        }
        
        result = {}
        for key, value in data.items():
            if key.lower() in debug_fields:
                continue
            if isinstance(value, dict):
                result[key] = self._remove_debug_fields(value)
            else:
                result[key] = value
        
        return result
    
    def get_error_detail_level(self) -> str:
        """Get appropriate error detail level."""
        if not self.config.enabled:
            return "minimal"
        
        if self.config.environment == Environment.PRODUCTION:
            return "minimal"
        
        level_map = {
            DebugLevel.DISABLED: "minimal",
            DebugLevel.MINIMAL: "basic",
            DebugLevel.STANDARD: "detailed",
            DebugLevel.VERBOSE: "full",
            DebugLevel.FULL: "full",
        }
        
        return level_map.get(self.config.level, "minimal")


# =============================================================================
# Debug Mode Service
# =============================================================================

class DebugModeService:
    """
    High-level debug mode security service.
    """
    
    _instance: Optional["DebugModeService"] = None
    
    def __init__(self, config: Optional[DebugConfig] = None):
        """Initialize service."""
        self.detector = DebugModeDetector()
        
        if config is None:
            # Auto-configure based on environment
            config = DebugConfig(
                enabled=self.detector.detect_debug_mode(),
                environment=self.detector.detect_environment(),
            )
        
        self.config = config
        self.controller = DebugAccessController(config)
        self.guard = DebugEndpointGuard(self.controller)
        self.filter = DebugInfoFilter(config)
        
        # Warn if debug in production
        self.detector.warn_if_debug_in_production()
    
    @classmethod
    def get_instance(cls) -> "DebugModeService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: DebugConfig) -> "DebugModeService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def is_debug_enabled(self) -> bool:
        """Check if debug is enabled."""
        return self.config.enabled and self.config.is_debug_allowed()
    
    def check_access(
        self,
        ip_address: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Check debug access."""
        return self.guard.check_access(ip_address, user_id)
    
    def filter_response(
        self,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Filter response data."""
        return self.filter.filter_response(data, self.is_debug_enabled())
    
    def get_security_warnings(self) -> List[str]:
        """Get any security warnings."""
        return self.detector.validate_debug_settings()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_debug_service() -> DebugModeService:
    """Get the global debug service."""
    return DebugModeService.get_instance()


def is_debug_enabled() -> bool:
    """Check if debug is enabled."""
    return get_debug_service().is_debug_enabled()


def is_production() -> bool:
    """Check if running in production."""
    return DebugModeDetector().is_production()


def protect_debug_endpoint(
    get_ip: Optional[Callable[[], str]] = None,
    get_user: Optional[Callable[[], Optional[str]]] = None,
) -> Callable[[F], F]:
    """Decorator to protect debug endpoints."""
    return get_debug_service().guard.protect(get_ip, get_user)
