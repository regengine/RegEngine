"""
Tests for SEC-030: API Versioning.

Tests cover:
- Version parsing
- Version extraction (header, URL, query, accept)
- Version registration and lifecycle
- Version validation
- Version routing
- Deprecation and sunset handling
"""

import pytest
from datetime import datetime, timezone, timedelta

from shared.api_versioning import (
    # Enums
    VersionStatus,
    VersionLocation,
    # Data classes
    APIVersion,
    VersionInfo,
    VersionExtractionResult,
    VersionValidationResult,
    # Classes
    VersionExtractor,
    VersionRegistry,
    VersionValidator,
    VersionRouter,
    VersionService,
    # Convenience functions
    get_version_service,
    parse_version,
    validate_version,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def extractor():
    """Create version extractor."""
    return VersionExtractor()


@pytest.fixture
def registry():
    """Create version registry."""
    reg = VersionRegistry()
    reg.register(APIVersion(1), VersionStatus.DEPRECATED)
    reg.register(APIVersion(2), VersionStatus.CURRENT)
    reg.register(APIVersion(3), VersionStatus.SUPPORTED)
    return reg


@pytest.fixture
def validator(registry):
    """Create version validator."""
    return VersionValidator(registry)


@pytest.fixture
def service():
    """Create version service."""
    return VersionService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_version_statuses(self):
        """Should have expected statuses."""
        assert VersionStatus.CURRENT == "current"
        assert VersionStatus.SUPPORTED == "supported"
        assert VersionStatus.DEPRECATED == "deprecated"
        assert VersionStatus.SUNSET == "sunset"
    
    def test_version_locations(self):
        """Should have expected locations."""
        assert VersionLocation.HEADER == "header"
        assert VersionLocation.URL_PATH == "url_path"
        assert VersionLocation.QUERY_PARAM == "query_param"
        assert VersionLocation.ACCEPT_HEADER == "accept_header"


# =============================================================================
# Test: APIVersion
# =============================================================================

class TestAPIVersion:
    """Test APIVersion class."""
    
    def test_parse_simple(self):
        """Should parse simple version."""
        v = APIVersion.parse("v1")
        assert v.major == 1
        assert v.minor == 0
        assert v.patch == 0
    
    def test_parse_minor(self):
        """Should parse version with minor."""
        v = APIVersion.parse("v2.1")
        assert v.major == 2
        assert v.minor == 1
        assert v.patch == 0
    
    def test_parse_patch(self):
        """Should parse full version."""
        v = APIVersion.parse("v3.2.1")
        assert v.major == 3
        assert v.minor == 2
        assert v.patch == 1
    
    def test_parse_without_prefix(self):
        """Should parse without v prefix."""
        v = APIVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
    
    def test_parse_invalid(self):
        """Should return None for invalid."""
        assert APIVersion.parse("") is None
        assert APIVersion.parse("invalid") is None
    
    def test_str_representation(self):
        """Should format as string."""
        assert str(APIVersion(1)) == "v1"
        assert str(APIVersion(1, 2)) == "v1.2"
        assert str(APIVersion(1, 2, 3)) == "v1.2.3"
    
    def test_comparison(self):
        """Should compare versions."""
        v1 = APIVersion(1)
        v2 = APIVersion(2)
        v1_1 = APIVersion(1, 1)
        
        assert v1 < v2
        assert v2 > v1
        assert v1 < v1_1
        assert v1 <= APIVersion(1)
        assert v2 >= v1
    
    def test_equality(self):
        """Should check equality."""
        assert APIVersion(1) == APIVersion(1)
        assert APIVersion(1) != APIVersion(2)
        assert APIVersion(1, 0) == APIVersion(1, 0, 0)
    
    def test_hashable(self):
        """Should be hashable."""
        versions = {APIVersion(1), APIVersion(2)}
        assert len(versions) == 2
    
    def test_compatibility(self):
        """Should check major version compatibility."""
        v1 = APIVersion(1)
        v1_1 = APIVersion(1, 1)
        v2 = APIVersion(2)
        
        assert v1.is_compatible_with(v1_1) is True
        assert v1.is_compatible_with(v2) is False
    
    def test_to_dict(self):
        """Should convert to dict."""
        v = APIVersion(1, 2, 3)
        d = v.to_dict()
        
        assert d["major"] == 1
        assert d["minor"] == 2
        assert d["patch"] == 3


# =============================================================================
# Test: VersionInfo
# =============================================================================

class TestVersionInfo:
    """Test VersionInfo class."""
    
    def test_is_available(self):
        """Should check availability."""
        info = VersionInfo(
            version=APIVersion(1),
            status=VersionStatus.SUPPORTED,
            release_date=datetime.now(timezone.utc),
        )
        assert info.is_available() is True
        
        info.status = VersionStatus.SUNSET
        assert info.is_available() is False
    
    def test_days_until_sunset(self):
        """Should calculate days until sunset."""
        info = VersionInfo(
            version=APIVersion(1),
            status=VersionStatus.DEPRECATED,
            release_date=datetime.now(timezone.utc),
            sunset_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        
        days = info.days_until_sunset()
        assert 29 <= days <= 30
    
    def test_to_dict(self):
        """Should convert to dict."""
        info = VersionInfo(
            version=APIVersion(1),
            status=VersionStatus.CURRENT,
            release_date=datetime.now(timezone.utc),
        )
        
        d = info.to_dict()
        assert d["version"] == "v1"
        assert d["status"] == "current"


# =============================================================================
# Test: Version Extractor
# =============================================================================

class TestVersionExtractor:
    """Test VersionExtractor."""
    
    def test_extract_from_header(self, extractor):
        """Should extract from header."""
        result = extractor.extract(
            headers={"X-API-Version": "v2"},
            url_path="/api/users",
        )
        
        assert result.version == APIVersion(2)
        assert result.location == VersionLocation.HEADER
    
    def test_extract_from_url(self, extractor):
        """Should extract from URL path."""
        result = extractor.extract(
            headers={},
            url_path="/v1/api/users",
        )
        
        assert result.version == APIVersion(1)
        assert result.location == VersionLocation.URL_PATH
    
    def test_extract_from_query(self, extractor):
        """Should extract from query parameter."""
        result = extractor.extract(
            headers={},
            url_path="/api/users",
            query_params={"version": "3"},
        )
        
        assert result.version == APIVersion(3)
        assert result.location == VersionLocation.QUERY_PARAM
    
    def test_extract_from_accept_header(self, extractor):
        """Should extract from Accept header."""
        result = extractor.extract(
            headers={"Accept": "application/vnd.api+json; version=2"},
            url_path="/api/users",
        )
        
        assert result.version == APIVersion(2)
        assert result.location == VersionLocation.ACCEPT_HEADER
    
    def test_extract_priority(self, extractor):
        """Should respect extraction priority."""
        # Header takes priority over URL
        result = extractor.extract(
            headers={"X-API-Version": "v3"},
            url_path="/v1/api/users",
        )
        
        assert result.version == APIVersion(3)
        assert result.location == VersionLocation.HEADER
    
    def test_extract_no_version(self, extractor):
        """Should handle no version."""
        result = extractor.extract(
            headers={},
            url_path="/api/users",
        )
        
        assert result.version is None
        assert "No version" in result.error
    
    def test_custom_header_name(self):
        """Should use custom header name."""
        extractor = VersionExtractor(header_name="API-Version")
        
        result = extractor.extract(
            headers={"API-Version": "v1"},
            url_path="",
        )
        
        assert result.version == APIVersion(1)


# =============================================================================
# Test: Version Registry
# =============================================================================

class TestVersionRegistry:
    """Test VersionRegistry."""
    
    def test_register_version(self):
        """Should register version."""
        registry = VersionRegistry()
        
        info = registry.register(
            APIVersion(1),
            status=VersionStatus.SUPPORTED,
        )
        
        assert info.version == APIVersion(1)
        assert info.status == VersionStatus.SUPPORTED
    
    def test_set_current(self, registry):
        """Should set current version."""
        registry.set_current(APIVersion(3))
        
        assert registry.get_current() == APIVersion(3)
        assert registry.get_info(APIVersion(3)).status == VersionStatus.CURRENT
    
    def test_set_default(self, registry):
        """Should set default version."""
        registry.set_default(APIVersion(2))
        
        assert registry.get_default() == APIVersion(2)
    
    def test_deprecate(self, registry):
        """Should deprecate version."""
        registry.deprecate(
            APIVersion(2),
            sunset_date=datetime.now(timezone.utc) + timedelta(days=90),
        )
        
        info = registry.get_info(APIVersion(2))
        assert info.status == VersionStatus.DEPRECATED
        assert info.deprecation_date is not None
        assert info.sunset_date is not None
    
    def test_sunset(self, registry):
        """Should sunset version."""
        registry.sunset(APIVersion(1))
        
        info = registry.get_info(APIVersion(1))
        assert info.status == VersionStatus.SUNSET
    
    def test_list_versions(self, registry):
        """Should list versions."""
        versions = registry.list_versions()
        
        assert len(versions) == 3
        # Should be in descending order
        assert versions[0].version > versions[1].version
    
    def test_list_versions_exclude_sunset(self, registry):
        """Should exclude sunset versions."""
        registry.sunset(APIVersion(1))
        
        versions = registry.list_versions(include_sunset=False)
        
        assert all(v.status != VersionStatus.SUNSET for v in versions)
    
    def test_is_registered(self, registry):
        """Should check if registered."""
        assert registry.is_registered(APIVersion(1)) is True
        assert registry.is_registered(APIVersion(99)) is False


# =============================================================================
# Test: Version Validator
# =============================================================================

class TestVersionValidator:
    """Test VersionValidator."""
    
    def test_validate_supported(self, validator):
        """Should validate supported version."""
        result = validator.validate(APIVersion(3))
        
        assert result.valid is True
        assert result.version == APIVersion(3)
        assert result.warning is None
    
    def test_validate_current(self, validator):
        """Should validate current version."""
        result = validator.validate(APIVersion(2))
        
        assert result.valid is True
        assert "X-API-Version" in result.headers
    
    def test_validate_deprecated(self, validator, registry):
        """Should warn on deprecated version."""
        result = validator.validate(APIVersion(1))
        
        assert result.valid is True
        assert "deprecated" in result.warning.lower()
    
    def test_validate_sunset(self, validator, registry):
        """Should reject sunset version."""
        registry.sunset(APIVersion(1))
        
        result = validator.validate(APIVersion(1))
        
        assert result.valid is False
        assert "sunset" in result.error.lower()
    
    def test_validate_unknown(self, validator):
        """Should reject unknown version."""
        result = validator.validate(APIVersion(99))
        
        assert result.valid is False
        assert "not supported" in result.error
    
    def test_validate_default(self, validator, registry):
        """Should use default version."""
        registry.set_default(APIVersion(2))
        
        result = validator.validate(None)
        
        assert result.valid is True
        assert result.version == APIVersion(2)
    
    def test_sunset_header(self, validator, registry):
        """Should include Sunset header for deprecated."""
        registry.deprecate(
            APIVersion(3),
            sunset_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        
        result = validator.validate(APIVersion(3))
        
        assert "Sunset" in result.headers


# =============================================================================
# Test: Version Router
# =============================================================================

class TestVersionRouter:
    """Test VersionRouter."""
    
    def test_register_handler(self):
        """Should register handler."""
        router = VersionRouter()
        handler = lambda: "v1"
        
        router.register("/users", APIVersion(1), handler)
        
        result = router.get_handler("/users", APIVersion(1))
        assert result is handler
    
    def test_get_exact_version(self):
        """Should get exact version handler."""
        router = VersionRouter()
        router.register("/users", APIVersion(1), lambda: "v1")
        router.register("/users", APIVersion(2), lambda: "v2")
        
        handler = router.get_handler("/users", APIVersion(2))
        assert handler() == "v2"
    
    def test_fallback_compatible(self):
        """Should fallback to compatible version."""
        router = VersionRouter()
        router.register("/users", APIVersion(1, 0), lambda: "v1.0")
        router.register("/users", APIVersion(1, 2), lambda: "v1.2")
        
        # v1.3 should fall back to v1.2
        handler = router.get_handler("/users", APIVersion(1, 3))
        assert handler() == "v1.2"
    
    def test_no_fallback_across_major(self):
        """Should not fallback across major versions."""
        router = VersionRouter()
        router.register("/users", APIVersion(1), lambda: "v1")
        
        handler = router.get_handler("/users", APIVersion(2))
        assert handler is None
    
    def test_list_versions(self):
        """Should list versions for endpoint."""
        router = VersionRouter()
        router.register("/users", APIVersion(1), lambda: None)
        router.register("/users", APIVersion(2), lambda: None)
        
        versions = router.list_versions("/users")
        
        assert len(versions) == 2
        assert APIVersion(1) in versions


# =============================================================================
# Test: Version Service
# =============================================================================

class TestVersionService:
    """Test VersionService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        s1 = get_version_service()
        s2 = get_version_service()
        
        assert s1 is s2
    
    def test_register_version_string(self, service):
        """Should register from string."""
        info = service.register_version("v1", VersionStatus.SUPPORTED)
        
        assert info is not None
        assert info.version == APIVersion(1)
    
    def test_process_request(self, service):
        """Should process request."""
        service.register_version("v1", VersionStatus.SUPPORTED)
        service.registry.set_default(APIVersion(1))
        
        result = service.process_request(
            headers={"X-API-Version": "v1"},
            url_path="/api/users",
        )
        
        assert result.valid is True
    
    def test_get_supported_versions(self, service):
        """Should get supported versions."""
        service.register_version("v1")
        service.register_version("v2", VersionStatus.CURRENT)
        
        versions = service.get_supported_versions()
        
        assert len(versions) >= 2


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_parse_version(self):
        """Should parse version."""
        v = parse_version("v2.1")
        
        assert v.major == 2
        assert v.minor == 1
    
    def test_get_version_service(self):
        """Should get service."""
        service = get_version_service()
        assert service is not None
