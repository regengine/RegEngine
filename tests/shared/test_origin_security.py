"""
Tests for SEC-040: Request Origin Validation.

Tests cover:
- Origin header validation
- Referer header validation
- CORS preflight handling
- Domain whitelist management
"""

import pytest

from shared.origin_security import (
    # Enums
    OriginValidationResult,
    CORSMode,
    # Data classes
    OriginConfig,
    CORSConfig,
    OriginValidation,
    CORSHeaders,
    # Classes
    OriginValidator,
    CORSHandler,
    OriginSecurityService,
    # Convenience functions
    get_origin_service,
    validate_origin,
    get_cors_headers,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def origin_config():
    """Create origin config."""
    return OriginConfig(
        allowed_origins={"https://example.com", "https://trusted.com"},
    )


@pytest.fixture
def cors_config():
    """Create CORS config."""
    return CORSConfig()


@pytest.fixture
def validator(origin_config):
    """Create origin validator."""
    return OriginValidator(origin_config)


@pytest.fixture
def cors_handler(origin_config, cors_config):
    """Create CORS handler."""
    return CORSHandler(origin_config, cors_config)


@pytest.fixture
def service(origin_config, cors_config):
    """Create origin service."""
    return OriginSecurityService(origin_config, cors_config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_validation_results(self):
        """Should have expected validation results."""
        assert OriginValidationResult.VALID == "valid"
        assert OriginValidationResult.MISSING_ORIGIN == "missing_origin"
        assert OriginValidationResult.BLOCKED_ORIGIN == "blocked_origin"
    
    def test_cors_modes(self):
        """Should have expected CORS modes."""
        assert CORSMode.DISABLED == "disabled"
        assert CORSMode.ALLOW_ALL == "allow_all"
        assert CORSMode.WHITELIST == "whitelist"


# =============================================================================
# Test: OriginConfig
# =============================================================================

class TestOriginConfig:
    """Test OriginConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = OriginConfig()
        
        assert config.cors_mode == CORSMode.WHITELIST
        assert config.allow_null_origin is False
        assert config.require_origin_header is True


# =============================================================================
# Test: CORSHeaders
# =============================================================================

class TestCORSHeaders:
    """Test CORSHeaders class."""
    
    def test_to_dict(self):
        """Should convert to dict."""
        headers = CORSHeaders(
            access_control_allow_origin="https://example.com",
            access_control_allow_methods="GET, POST",
        )
        
        result = headers.to_dict()
        
        assert result["Access-Control-Allow-Origin"] == "https://example.com"
        assert result["Access-Control-Allow-Methods"] == "GET, POST"
        assert "Vary" in result


# =============================================================================
# Test: OriginValidator
# =============================================================================

class TestOriginValidator:
    """Test OriginValidator."""
    
    def test_validates_allowed_origin(self, validator):
        """Should validate allowed origin."""
        result = validator.validate("https://example.com")
        
        assert result.is_valid is True
        assert result.result == OriginValidationResult.VALID
    
    def test_rejects_unknown_origin(self, validator):
        """Should reject unknown origin."""
        result = validator.validate("https://evil.com")
        
        assert result.is_valid is False
        assert result.result == OriginValidationResult.INVALID_ORIGIN
    
    def test_rejects_missing_origin(self, validator):
        """Should reject missing origin when required."""
        result = validator.validate(None)
        
        assert result.is_valid is False
        assert result.result == OriginValidationResult.MISSING_ORIGIN
    
    def test_rejects_null_origin(self, validator):
        """Should reject null origin by default."""
        result = validator.validate("null")
        
        assert result.is_valid is False
    
    def test_allows_null_origin_when_configured(self):
        """Should allow null origin when configured."""
        config = OriginConfig(
            allowed_origins={"https://example.com"},
            allow_null_origin=True,
        )
        validator = OriginValidator(config)
        
        result = validator.validate("null")
        
        assert result.is_valid is True
    
    def test_validates_invalid_format(self, validator):
        """Should reject invalid format."""
        result = validator.validate("not-a-valid-origin")
        
        assert result.is_valid is False
        assert result.result == OriginValidationResult.INVALID_FORMAT
    
    def test_fallback_to_referer(self, validator):
        """Should fallback to referer header."""
        result = validator.validate(
            None,
            referer="https://example.com/page"
        )
        
        assert result.is_valid is True
        assert result.origin == "https://example.com"
    
    def test_blocked_origin(self):
        """Should block blocked origins."""
        config = OriginConfig(
            allowed_origins=set(),
            blocked_origins={"https://evil.com"},
        )
        validator = OriginValidator(config)
        
        result = validator.validate("https://evil.com")
        
        assert result.is_valid is False
        assert result.result == OriginValidationResult.BLOCKED_ORIGIN
    
    def test_allow_all_mode(self):
        """Should allow all in ALLOW_ALL mode."""
        config = OriginConfig(cors_mode=CORSMode.ALLOW_ALL)
        validator = OriginValidator(config)
        
        result = validator.validate("https://any-domain.com")
        
        assert result.is_valid is True
    
    def test_subdomain_matching(self):
        """Should match subdomains when enabled."""
        config = OriginConfig(
            allowed_origins={"https://example.com"},
            allow_subdomains=True,
        )
        validator = OriginValidator(config)
        
        result = validator.validate("https://sub.example.com")
        
        assert result.is_valid is True


# =============================================================================
# Test: CORSHandler
# =============================================================================

class TestCORSHandler:
    """Test CORSHandler."""
    
    def test_handle_preflight(self, cors_handler):
        """Should handle preflight request."""
        is_allowed, headers = cors_handler.handle_preflight(
            "https://example.com",
            request_method="POST",
        )
        
        assert is_allowed is True
        assert headers.access_control_allow_origin == "https://example.com"
        assert headers.access_control_allow_methods is not None
    
    def test_preflight_rejected_origin(self, cors_handler):
        """Should reject preflight with invalid origin."""
        is_allowed, headers = cors_handler.handle_preflight(
            "https://evil.com",
        )
        
        assert is_allowed is False
    
    def test_preflight_invalid_method(self, cors_handler):
        """Should reject preflight with invalid method."""
        is_allowed, headers = cors_handler.handle_preflight(
            "https://example.com",
            request_method="CUSTOM",
        )
        
        assert is_allowed is False
    
    def test_handle_request(self, cors_handler):
        """Should handle actual request."""
        is_allowed, headers = cors_handler.handle_request("https://example.com")
        
        assert is_allowed is True
        assert headers.access_control_allow_origin == "https://example.com"
    
    def test_allow_all_returns_wildcard(self):
        """Should return * for ALLOW_ALL mode."""
        config = OriginConfig(cors_mode=CORSMode.ALLOW_ALL)
        handler = CORSHandler(config)
        
        _, headers = handler.handle_request("https://any.com")
        
        assert headers.access_control_allow_origin == "*"
    
    def test_credentials_header(self):
        """Should set credentials header."""
        origin_config = OriginConfig(
            allowed_origins={"https://example.com"},
        )
        cors_config = CORSConfig(allow_credentials=True)
        handler = CORSHandler(origin_config, cors_config)
        
        _, headers = handler.handle_request("https://example.com")
        
        assert headers.access_control_allow_credentials == "true"


# =============================================================================
# Test: OriginSecurityService
# =============================================================================

class TestOriginSecurityService:
    """Test OriginSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        OriginSecurityService._instance = None
        
        s1 = get_origin_service()
        s2 = get_origin_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        config = OriginConfig(
            allowed_origins={"https://custom.com"},
        )
        
        service = OriginSecurityService.configure(config)
        
        assert "https://custom.com" in service.origin_config.allowed_origins
    
    def test_validate_origin(self, service):
        """Should validate origin."""
        result = service.validate_origin("https://example.com")
        
        assert result.is_valid is True
    
    def test_handle_preflight(self, service):
        """Should handle preflight."""
        is_allowed, headers = service.handle_preflight(
            "https://example.com",
        )
        
        assert is_allowed is True
        assert "Access-Control-Allow-Origin" in headers
    
    def test_handle_cors(self, service):
        """Should get CORS headers."""
        headers = service.handle_cors("https://example.com")
        
        assert "Access-Control-Allow-Origin" in headers
    
    def test_add_allowed_origin(self, service):
        """Should add allowed origin."""
        service.add_allowed_origin("https://new.com")
        
        assert "https://new.com" in service.origin_config.allowed_origins
    
    def test_remove_allowed_origin(self, service):
        """Should remove allowed origin."""
        service.remove_allowed_origin("https://example.com")
        
        assert "https://example.com" not in service.origin_config.allowed_origins


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_validate_origin(self):
        """Should validate via convenience function."""
        OriginSecurityService._instance = None
        OriginSecurityService.configure(OriginConfig(
            allowed_origins={"https://example.com"},
        ))
        
        assert validate_origin("https://example.com") is True
        assert validate_origin("https://evil.com") is False
    
    def test_get_cors_headers(self):
        """Should get headers via convenience function."""
        OriginSecurityService._instance = None
        OriginSecurityService.configure(OriginConfig(
            allowed_origins={"https://example.com"},
        ))
        
        headers = get_cors_headers("https://example.com")
        
        assert isinstance(headers, dict)


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_default_rejects_all(self):
        """Default config should reject unknown origins."""
        validator = OriginValidator()
        
        result = validator.validate("https://any-domain.com")
        
        # With empty allowed list, should reject
        assert result.is_valid is False
    
    def test_blocks_null_origin_by_default(self):
        """Should block null origin by default."""
        validator = OriginValidator()
        
        result = validator.validate("null")
        
        assert result.is_valid is False
    
    def test_requires_origin_by_default(self):
        """Should require origin header by default."""
        config = OriginConfig(allowed_origins={"https://example.com"})
        validator = OriginValidator(config)
        
        result = validator.validate(None)
        
        assert result.is_valid is False
        assert result.result == OriginValidationResult.MISSING_ORIGIN
