"""
SEC-030: API Versioning.

Provides secure API versioning:
- Version extraction from headers, URL, and query parameters
- Version validation and deprecation handling
- Version routing
- Sunset header support
- API version lifecycle management
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class VersionStatus(str, Enum):
    """API version status."""
    CURRENT = "current"  # Recommended version
    SUPPORTED = "supported"  # Still supported
    DEPRECATED = "deprecated"  # Works but warns
    SUNSET = "sunset"  # No longer available


class VersionLocation(str, Enum):
    """Where version can be specified."""
    HEADER = "header"
    URL_PATH = "url_path"
    QUERY_PARAM = "query_param"
    ACCEPT_HEADER = "accept_header"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class APIVersion:
    """Represents an API version."""
    major: int
    minor: int = 0
    patch: int = 0
    
    def __str__(self) -> str:
        """Return string representation."""
        if self.patch > 0:
            return f"v{self.major}.{self.minor}.{self.patch}"
        if self.minor > 0:
            return f"v{self.major}.{self.minor}"
        return f"v{self.major}"
    
    def __eq__(self, other: object) -> bool:
        """Check equality."""
        if not isinstance(other, APIVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other: "APIVersion") -> bool:
        """Compare versions."""
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other: "APIVersion") -> bool:
        """Compare versions."""
        return self == other or self < other
    
    def __gt__(self, other: "APIVersion") -> bool:
        """Compare versions."""
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)
    
    def __ge__(self, other: "APIVersion") -> bool:
        """Compare versions."""
        return self == other or self > other
    
    def __hash__(self) -> int:
        """Make hashable."""
        return hash((self.major, self.minor, self.patch))
    
    @classmethod
    def parse(cls, version_str: str) -> Optional["APIVersion"]:
        """
        Parse version from string.
        
        Supports formats:
        - v1, v1.0, v1.0.0
        - 1, 1.0, 1.0.0
        """
        if not version_str:
            return None
        
        # Remove 'v' prefix if present
        version_str = version_str.lstrip("vV")
        
        # Parse components
        parts = version_str.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return cls(major=major, minor=minor, patch=patch)
        except (ValueError, IndexError):
            return None
    
    def is_compatible_with(self, other: "APIVersion") -> bool:
        """Check if versions are compatible (same major)."""
        return self.major == other.major
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary."""
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
        }


@dataclass
class VersionInfo:
    """Information about an API version."""
    version: APIVersion
    status: VersionStatus
    release_date: datetime
    sunset_date: Optional[datetime] = None
    deprecation_date: Optional[datetime] = None
    changelog_url: Optional[str] = None
    migration_guide_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_available(self) -> bool:
        """Check if version is available."""
        return self.status != VersionStatus.SUNSET
    
    def days_until_sunset(self) -> Optional[int]:
        """Get days until sunset, if scheduled."""
        if not self.sunset_date:
            return None
        delta = self.sunset_date - datetime.now(timezone.utc)
        return max(0, delta.days)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": str(self.version),
            "status": self.status.value,
            "release_date": self.release_date.isoformat(),
            "sunset_date": self.sunset_date.isoformat() if self.sunset_date else None,
            "deprecation_date": self.deprecation_date.isoformat() if self.deprecation_date else None,
            "changelog_url": self.changelog_url,
            "migration_guide_url": self.migration_guide_url,
        }


@dataclass
class VersionExtractionResult:
    """Result of version extraction."""
    version: Optional[APIVersion]
    location: Optional[VersionLocation]
    raw_value: Optional[str]
    error: Optional[str] = None


@dataclass
class VersionValidationResult:
    """Result of version validation."""
    valid: bool
    version: Optional[APIVersion]
    info: Optional[VersionInfo] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)


# =============================================================================
# Version Extractor
# =============================================================================

class VersionExtractor:
    """
    Extracts API version from request.
    
    Supports multiple extraction strategies:
    - Header (e.g., X-API-Version: v1)
    - URL path (e.g., /v1/users)
    - Query parameter (e.g., ?version=1)
    - Accept header (e.g., Accept: application/vnd.api+json; version=1)
    """
    
    DEFAULT_HEADER = "X-API-Version"
    DEFAULT_QUERY_PARAM = "version"
    URL_VERSION_PATTERN = re.compile(r"/v(\d+(?:\.\d+)*)")
    ACCEPT_VERSION_PATTERN = re.compile(r"version\s*=\s*(\d+(?:\.\d+)*)")
    
    def __init__(
        self,
        header_name: str = DEFAULT_HEADER,
        query_param: str = DEFAULT_QUERY_PARAM,
        priority: List[VersionLocation] = None,
    ):
        """
        Initialize extractor.
        
        Args:
            header_name: Custom version header name
            query_param: Query parameter name
            priority: Order to check for version (default: header, url, query, accept)
        """
        self.header_name = header_name
        self.query_param = query_param
        self.priority = priority or [
            VersionLocation.HEADER,
            VersionLocation.URL_PATH,
            VersionLocation.QUERY_PARAM,
            VersionLocation.ACCEPT_HEADER,
        ]
    
    def extract(
        self,
        headers: Dict[str, str],
        url_path: str = "",
        query_params: Dict[str, str] = None,
    ) -> VersionExtractionResult:
        """
        Extract version from request.
        
        Args:
            headers: Request headers
            url_path: URL path
            query_params: Query parameters
            
        Returns:
            VersionExtractionResult
        """
        query_params = query_params or {}
        
        # Normalize headers to lowercase
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        
        for location in self.priority:
            result = self._extract_from_location(
                location, normalized_headers, url_path, query_params
            )
            if result.version:
                return result
        
        return VersionExtractionResult(
            version=None,
            location=None,
            raw_value=None,
            error="No version specified",
        )
    
    def _extract_from_location(
        self,
        location: VersionLocation,
        headers: Dict[str, str],
        url_path: str,
        query_params: Dict[str, str],
    ) -> VersionExtractionResult:
        """Extract version from specific location."""
        if location == VersionLocation.HEADER:
            return self._extract_from_header(headers)
        elif location == VersionLocation.URL_PATH:
            return self._extract_from_url(url_path)
        elif location == VersionLocation.QUERY_PARAM:
            return self._extract_from_query(query_params)
        elif location == VersionLocation.ACCEPT_HEADER:
            return self._extract_from_accept(headers)
        
        return VersionExtractionResult(
            version=None,
            location=location,
            raw_value=None,
        )
    
    def _extract_from_header(self, headers: Dict[str, str]) -> VersionExtractionResult:
        """Extract version from header."""
        raw_value = headers.get(self.header_name.lower())
        if not raw_value:
            return VersionExtractionResult(
                version=None,
                location=VersionLocation.HEADER,
                raw_value=None,
            )
        
        version = APIVersion.parse(raw_value)
        return VersionExtractionResult(
            version=version,
            location=VersionLocation.HEADER,
            raw_value=raw_value,
            error=f"Invalid version format: {raw_value}" if not version else None,
        )
    
    def _extract_from_url(self, url_path: str) -> VersionExtractionResult:
        """Extract version from URL path."""
        match = self.URL_VERSION_PATTERN.search(url_path)
        if not match:
            return VersionExtractionResult(
                version=None,
                location=VersionLocation.URL_PATH,
                raw_value=None,
            )
        
        raw_value = match.group(1)
        version = APIVersion.parse(raw_value)
        return VersionExtractionResult(
            version=version,
            location=VersionLocation.URL_PATH,
            raw_value=raw_value,
        )
    
    def _extract_from_query(self, query_params: Dict[str, str]) -> VersionExtractionResult:
        """Extract version from query parameter."""
        raw_value = query_params.get(self.query_param)
        if not raw_value:
            return VersionExtractionResult(
                version=None,
                location=VersionLocation.QUERY_PARAM,
                raw_value=None,
            )
        
        version = APIVersion.parse(raw_value)
        return VersionExtractionResult(
            version=version,
            location=VersionLocation.QUERY_PARAM,
            raw_value=raw_value,
        )
    
    def _extract_from_accept(self, headers: Dict[str, str]) -> VersionExtractionResult:
        """Extract version from Accept header."""
        accept = headers.get("accept", "")
        match = self.ACCEPT_VERSION_PATTERN.search(accept)
        
        if not match:
            return VersionExtractionResult(
                version=None,
                location=VersionLocation.ACCEPT_HEADER,
                raw_value=None,
            )
        
        raw_value = match.group(1)
        version = APIVersion.parse(raw_value)
        return VersionExtractionResult(
            version=version,
            location=VersionLocation.ACCEPT_HEADER,
            raw_value=raw_value,
        )


# =============================================================================
# Version Registry
# =============================================================================

class VersionRegistry:
    """
    Manages registered API versions.
    
    Tracks version status, deprecation, and sunset dates.
    """
    
    def __init__(self):
        """Initialize registry."""
        self._versions: Dict[APIVersion, VersionInfo] = {}
        self._current: Optional[APIVersion] = None
        self._default: Optional[APIVersion] = None
    
    def register(
        self,
        version: APIVersion,
        status: VersionStatus = VersionStatus.SUPPORTED,
        release_date: Optional[datetime] = None,
        sunset_date: Optional[datetime] = None,
        deprecation_date: Optional[datetime] = None,
        changelog_url: Optional[str] = None,
        migration_guide_url: Optional[str] = None,
    ) -> VersionInfo:
        """
        Register an API version.
        
        Args:
            version: API version
            status: Version status
            release_date: When version was released
            sunset_date: When version will be sunset
            deprecation_date: When version became deprecated
            changelog_url: URL to changelog
            migration_guide_url: URL to migration guide
            
        Returns:
            VersionInfo
        """
        info = VersionInfo(
            version=version,
            status=status,
            release_date=release_date or datetime.now(timezone.utc),
            sunset_date=sunset_date,
            deprecation_date=deprecation_date,
            changelog_url=changelog_url,
            migration_guide_url=migration_guide_url,
        )
        
        self._versions[version] = info
        
        if status == VersionStatus.CURRENT:
            self._current = version
        
        return info
    
    def set_current(self, version: APIVersion) -> bool:
        """Set current recommended version."""
        if version not in self._versions:
            return False
        
        # Update old current
        if self._current and self._current in self._versions:
            old_info = self._versions[self._current]
            if old_info.status == VersionStatus.CURRENT:
                old_info.status = VersionStatus.SUPPORTED
        
        # Set new current
        self._current = version
        self._versions[version].status = VersionStatus.CURRENT
        return True
    
    def set_default(self, version: APIVersion) -> bool:
        """Set default version when none specified."""
        if version not in self._versions:
            return False
        self._default = version
        return True
    
    def deprecate(
        self,
        version: APIVersion,
        sunset_date: Optional[datetime] = None,
    ) -> bool:
        """Deprecate a version."""
        if version not in self._versions:
            return False
        
        info = self._versions[version]
        info.status = VersionStatus.DEPRECATED
        info.deprecation_date = datetime.now(timezone.utc)
        
        if sunset_date:
            info.sunset_date = sunset_date
        
        return True
    
    def sunset(self, version: APIVersion) -> bool:
        """Mark version as sunset (no longer available)."""
        if version not in self._versions:
            return False
        
        info = self._versions[version]
        info.status = VersionStatus.SUNSET
        info.sunset_date = datetime.now(timezone.utc)
        return True
    
    def get_info(self, version: APIVersion) -> Optional[VersionInfo]:
        """Get version info."""
        return self._versions.get(version)
    
    def get_current(self) -> Optional[APIVersion]:
        """Get current version."""
        return self._current
    
    def get_default(self) -> Optional[APIVersion]:
        """Get default version."""
        return self._default or self._current
    
    def list_versions(
        self,
        include_sunset: bool = False,
    ) -> List[VersionInfo]:
        """List all versions."""
        versions = []
        for info in self._versions.values():
            if not include_sunset and info.status == VersionStatus.SUNSET:
                continue
            versions.append(info)
        return sorted(versions, key=lambda x: x.version, reverse=True)
    
    def is_registered(self, version: APIVersion) -> bool:
        """Check if version is registered."""
        return version in self._versions


# =============================================================================
# Version Validator
# =============================================================================

class VersionValidator:
    """
    Validates API versions.
    
    Checks availability, deprecation, and generates appropriate headers.
    """
    
    def __init__(self, registry: VersionRegistry):
        """Initialize validator."""
        self.registry = registry
    
    def validate(self, version: Optional[APIVersion]) -> VersionValidationResult:
        """
        Validate a version.
        
        Args:
            version: Version to validate (or None for default)
            
        Returns:
            VersionValidationResult
        """
        headers = {}
        
        # Use default if not specified
        if version is None:
            default = self.registry.get_default()
            if default:
                version = default
            else:
                return VersionValidationResult(
                    valid=False,
                    version=None,
                    error="No version specified and no default configured",
                )
        
        # Check if registered
        info = self.registry.get_info(version)
        if not info:
            return VersionValidationResult(
                valid=False,
                version=version,
                error=f"Version {version} is not supported",
            )
        
        # Check if sunset
        if info.status == VersionStatus.SUNSET:
            return VersionValidationResult(
                valid=False,
                version=version,
                info=info,
                error=f"Version {version} has been sunset",
                headers={"Sunset": info.sunset_date.isoformat() if info.sunset_date else ""},
            )
        
        # Handle deprecated
        if info.status == VersionStatus.DEPRECATED:
            if info.sunset_date:
                headers["Sunset"] = info.sunset_date.strftime("%a, %d %b %Y %H:%M:%S GMT")
            
            if info.migration_guide_url:
                headers["Deprecation-Info"] = info.migration_guide_url
            
            current = self.registry.get_current()
            warning = f"Version {version} is deprecated"
            if current:
                warning += f". Please migrate to {current}"
            
            return VersionValidationResult(
                valid=True,
                version=version,
                info=info,
                warning=warning,
                headers=headers,
            )
        
        # Add API version header
        headers["X-API-Version"] = str(version)
        
        return VersionValidationResult(
            valid=True,
            version=version,
            info=info,
            headers=headers,
        )


# =============================================================================
# Version Router
# =============================================================================

class VersionRouter:
    """
    Routes requests to version-specific handlers.
    """
    
    def __init__(self):
        """Initialize router."""
        self._routes: Dict[str, Dict[APIVersion, Callable]] = {}
    
    def register(
        self,
        endpoint: str,
        version: APIVersion,
        handler: Callable,
    ) -> None:
        """Register version-specific handler."""
        if endpoint not in self._routes:
            self._routes[endpoint] = {}
        self._routes[endpoint][version] = handler
    
    def get_handler(
        self,
        endpoint: str,
        version: APIVersion,
    ) -> Optional[Callable]:
        """
        Get handler for endpoint and version.
        
        Falls back to closest compatible version if exact not found.
        """
        if endpoint not in self._routes:
            return None
        
        handlers = self._routes[endpoint]
        
        # Try exact match
        if version in handlers:
            return handlers[version]
        
        # Find closest compatible version (same major, highest minor)
        compatible = [v for v in handlers.keys() if v.is_compatible_with(version) and v <= version]
        if compatible:
            closest = max(compatible)
            return handlers[closest]
        
        return None
    
    def list_versions(self, endpoint: str) -> List[APIVersion]:
        """List available versions for endpoint."""
        if endpoint not in self._routes:
            return []
        return sorted(self._routes[endpoint].keys())


# =============================================================================
# Version Service
# =============================================================================

class VersionService:
    """
    High-level API versioning service.
    
    Combines extraction, validation, and routing.
    """
    
    _instance: Optional["VersionService"] = None
    
    def __init__(self):
        """Initialize service."""
        self.extractor = VersionExtractor()
        self.registry = VersionRegistry()
        self.validator = VersionValidator(self.registry)
        self.router = VersionRouter()
    
    @classmethod
    def get_instance(cls) -> "VersionService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_version(
        self,
        version_str: str,
        status: VersionStatus = VersionStatus.SUPPORTED,
        **kwargs,
    ) -> Optional[VersionInfo]:
        """Register a version from string."""
        version = APIVersion.parse(version_str)
        if not version:
            return None
        return self.registry.register(version, status, **kwargs)
    
    def process_request(
        self,
        headers: Dict[str, str],
        url_path: str = "",
        query_params: Dict[str, str] = None,
    ) -> VersionValidationResult:
        """
        Process request for versioning.
        
        Args:
            headers: Request headers
            url_path: URL path
            query_params: Query parameters
            
        Returns:
            VersionValidationResult
        """
        # Extract version
        extraction = self.extractor.extract(headers, url_path, query_params)
        
        # Validate
        return self.validator.validate(extraction.version)
    
    def get_supported_versions(self) -> List[Dict[str, Any]]:
        """Get list of supported versions."""
        return [info.to_dict() for info in self.registry.list_versions()]


# =============================================================================
# Convenience Functions
# =============================================================================

def get_version_service() -> VersionService:
    """Get the global version service."""
    return VersionService.get_instance()


def parse_version(version_str: str) -> Optional[APIVersion]:
    """Parse version string."""
    return APIVersion.parse(version_str)


def validate_version(version_str: str) -> VersionValidationResult:
    """Validate a version string."""
    version = APIVersion.parse(version_str)
    return get_version_service().validator.validate(version)
