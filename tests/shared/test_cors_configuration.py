"""
Tests for SEC-029: CORS Configuration.

Tests cover:
- CORS mode handling
- Origin validation
- Preflight requests
- Header and method validation
- Credentials handling
- Policy builder
- Predefined policies
"""

import pytest

from shared.cors_configuration import (
    # Enums
    CORSMode,
    CredentialsMode,
    # Data classes
    CORSConfig,
    CORSRequest,
    CORSResponse,
    CORSValidationResult,
    # Classes
    CORSValidator,
    CORSMiddleware,
    CORSPolicyBuilder,
    CORSService,
    # Predefined policies
    strict_cors_policy,
    permissive_cors_policy,
    api_cors_policy,
    # Convenience functions
    get_cors_service,
    check_cors_origin,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def strict_config():
    """Create strict CORS config."""
    return CORSConfig(
        mode=CORSMode.STRICT,
        allowed_origins={"https://example.com", "https://api.example.com"},
        allowed_methods={"GET", "POST", "PUT", "DELETE"},
        allowed_headers={"Content-Type", "Authorization"},
    )


@pytest.fixture
def validator(strict_config):
    """Create CORS validator."""
    return CORSValidator(strict_config)


@pytest.fixture
def middleware(strict_config):
    """Create CORS middleware."""
    return CORSMiddleware(strict_config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_cors_modes(self):
        """Should have expected CORS modes."""
        assert CORSMode.DISABLED == "disabled"
        assert CORSMode.PERMISSIVE == "permissive"
        assert CORSMode.STRICT == "strict"
        assert CORSMode.REFLECT == "reflect"
    
    def test_credentials_modes(self):
        """Should have expected credentials modes."""
        assert CredentialsMode.OMIT == "omit"
        assert CredentialsMode.SAME_ORIGIN == "same-origin"
        assert CredentialsMode.INCLUDE == "include"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""
    
    def test_cors_config_defaults(self):
        """Should have sensible defaults."""
        config = CORSConfig()
        
        assert config.mode == CORSMode.STRICT
        assert "GET" in config.allowed_methods
        assert "Content-Type" in config.allowed_headers
        assert config.max_age == 86400
    
    def test_cors_config_to_dict(self):
        """Should convert to dictionary."""
        config = CORSConfig(
            mode=CORSMode.STRICT,
            allowed_origins={"https://example.com"},
        )
        
        data = config.to_dict()
        
        assert data["mode"] == "strict"
        assert "https://example.com" in data["allowed_origins"]
    
    def test_cors_request_from_headers(self):
        """Should parse request headers."""
        headers = {
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        }
        
        request = CORSRequest.from_headers(headers, "OPTIONS")
        
        assert request.origin == "https://example.com"
        assert request.is_cors is True
        assert request.is_preflight is True
        assert request.request_method == "POST"
        assert "Content-Type" in request.request_headers
    
    def test_cors_request_non_cors(self):
        """Should identify non-CORS requests."""
        headers = {}
        
        request = CORSRequest.from_headers(headers)
        
        assert request.is_cors is False
        assert request.is_preflight is False
    
    def test_cors_response_to_headers(self):
        """Should convert to response headers."""
        response = CORSResponse(
            allow_origin="https://example.com",
            allow_methods="GET, POST",
            allow_credentials="true",
            max_age="3600",
        )
        
        headers = response.to_headers()
        
        assert headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert headers["Access-Control-Allow-Methods"] == "GET, POST"
        assert headers["Access-Control-Allow-Credentials"] == "true"
        assert headers["Access-Control-Max-Age"] == "3600"


# =============================================================================
# Test: CORS Validator
# =============================================================================

class TestCORSValidator:
    """Test CORSValidator."""
    
    def test_allowed_origin_exact_match(self, validator):
        """Should allow exact origin match."""
        assert validator.is_origin_allowed("https://example.com") is True
        assert validator.is_origin_allowed("https://api.example.com") is True
        assert validator.is_origin_allowed("https://other.com") is False
    
    def test_allowed_origin_pattern(self):
        """Should allow pattern matching."""
        config = CORSConfig(
            mode=CORSMode.STRICT,
            allowed_origin_patterns=["https://*.example.com"],
        )
        validator = CORSValidator(config)
        
        assert validator.is_origin_allowed("https://app.example.com") is True
        assert validator.is_origin_allowed("https://api.example.com") is True
        assert validator.is_origin_allowed("https://other.com") is False
    
    def test_permissive_mode(self):
        """Should allow all origins in permissive mode."""
        config = CORSConfig(mode=CORSMode.PERMISSIVE)
        validator = CORSValidator(config)
        
        assert validator.is_origin_allowed("https://any-origin.com") is True
    
    def test_disabled_mode(self):
        """Should block all in disabled mode."""
        config = CORSConfig(mode=CORSMode.DISABLED)
        validator = CORSValidator(config)
        
        assert validator.is_origin_allowed("https://example.com") is False
    
    def test_reflect_mode(self):
        """Should reflect all origins in reflect mode."""
        config = CORSConfig(mode=CORSMode.REFLECT)
        validator = CORSValidator(config)
        
        assert validator.is_origin_allowed("https://any-origin.com") is True
    
    def test_is_method_allowed(self, validator):
        """Should validate methods."""
        assert validator.is_method_allowed("GET") is True
        assert validator.is_method_allowed("POST") is True
        assert validator.is_method_allowed("CUSTOM") is False
    
    def test_are_headers_allowed(self, validator):
        """Should validate headers."""
        assert validator.are_headers_allowed({"Content-Type"}) is True
        assert validator.are_headers_allowed({"Content-Type", "Authorization"}) is True
        assert validator.are_headers_allowed({"X-Custom-Header"}) is False
    
    def test_validate_non_cors_request(self, validator):
        """Should allow non-CORS requests."""
        request = CORSRequest(is_cors=False)
        
        result = validator.validate_request(request)
        
        assert result.allowed is True
    
    def test_validate_cors_request_allowed(self, validator):
        """Should allow valid CORS request."""
        request = CORSRequest(
            origin="https://example.com",
            is_cors=True,
            is_preflight=False,
        )
        
        result = validator.validate_request(request)
        
        assert result.allowed is True
        assert result.response.allow_origin == "https://example.com"
    
    def test_validate_cors_request_blocked(self, validator):
        """Should block invalid origin."""
        request = CORSRequest(
            origin="https://malicious.com",
            is_cors=True,
            is_preflight=False,
        )
        
        result = validator.validate_request(request)
        
        assert result.allowed is False
        assert "not allowed" in result.error
    
    def test_validate_preflight_allowed(self, validator):
        """Should handle valid preflight."""
        request = CORSRequest(
            origin="https://example.com",
            is_cors=True,
            is_preflight=True,
            request_method="POST",
            request_headers={"Content-Type"},
        )
        
        result = validator.validate_request(request)
        
        assert result.allowed is True
        assert result.response.allow_methods is not None
        assert result.response.max_age is not None
    
    def test_validate_preflight_method_blocked(self, validator):
        """Should block disallowed method."""
        request = CORSRequest(
            origin="https://example.com",
            is_cors=True,
            is_preflight=True,
            request_method="CUSTOM",
        )
        
        result = validator.validate_request(request)
        
        assert result.allowed is False
        assert "Method" in result.error
    
    def test_validate_preflight_headers_blocked(self, validator):
        """Should block disallowed headers."""
        request = CORSRequest(
            origin="https://example.com",
            is_cors=True,
            is_preflight=True,
            request_method="POST",
            request_headers={"X-Custom-Header"},
        )
        
        result = validator.validate_request(request)
        
        assert result.allowed is False
        assert "headers" in result.error
    
    def test_add_remove_origin(self, validator):
        """Should add and remove origins."""
        validator.add_origin("https://new.com")
        assert validator.is_origin_allowed("https://new.com") is True
        
        validator.remove_origin("https://new.com")
        assert validator.is_origin_allowed("https://new.com") is False
    
    def test_credentials_handling(self):
        """Should handle credentials correctly."""
        config = CORSConfig(
            mode=CORSMode.STRICT,
            allowed_origins={"https://example.com"},
            credentials=CredentialsMode.INCLUDE,
        )
        validator = CORSValidator(config)
        
        request = CORSRequest(
            origin="https://example.com",
            is_cors=True,
            is_preflight=True,
            request_method="POST",
        )
        
        result = validator.validate_request(request)
        
        assert result.response.allow_credentials == "true"


# =============================================================================
# Test: CORS Middleware
# =============================================================================

class TestCORSMiddleware:
    """Test CORSMiddleware."""
    
    def test_process_non_cors_request(self, middleware):
        """Should pass through non-CORS requests."""
        should_continue, headers, error = middleware.process_request(
            method="GET",
            headers={},
        )
        
        assert should_continue is True
        assert error is None
    
    def test_process_valid_cors_request(self, middleware):
        """Should process valid CORS request."""
        should_continue, headers, error = middleware.process_request(
            method="GET",
            headers={"Origin": "https://example.com"},
        )
        
        assert should_continue is True
        assert "Access-Control-Allow-Origin" in headers
    
    def test_process_invalid_cors_request(self, middleware):
        """Should block invalid CORS request."""
        should_continue, headers, error = middleware.process_request(
            method="GET",
            headers={"Origin": "https://malicious.com"},
        )
        
        assert should_continue is False
        assert error is not None
    
    def test_process_preflight(self, middleware):
        """Should handle preflight request."""
        should_continue, headers, error = middleware.process_request(
            method="OPTIONS",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        
        # Preflight should not continue to handler
        assert should_continue is False
        assert error is None
        assert "Access-Control-Allow-Methods" in headers


# =============================================================================
# Test: Policy Builder
# =============================================================================

class TestCORSPolicyBuilder:
    """Test CORSPolicyBuilder."""
    
    def test_fluent_interface(self):
        """Should support fluent interface."""
        config = (
            CORSPolicyBuilder()
            .mode(CORSMode.STRICT)
            .allow_origin("https://example.com")
            .allow_method("GET")
            .allow_header("Content-Type")
            .max_age(3600)
            .build()
        )
        
        assert config.mode == CORSMode.STRICT
        assert "https://example.com" in config.allowed_origins
        assert "GET" in config.allowed_methods
        assert "Content-Type" in config.allowed_headers
        assert config.max_age == 3600
    
    def test_allow_credentials(self):
        """Should enable credentials."""
        config = (
            CORSPolicyBuilder()
            .allow_credentials()
            .build()
        )
        
        assert config.credentials == CredentialsMode.INCLUDE
    
    def test_expose_headers(self):
        """Should set exposed headers."""
        config = (
            CORSPolicyBuilder()
            .expose_headers(["X-Request-ID", "X-Rate-Limit"])
            .build()
        )
        
        assert "X-Request-ID" in config.exposed_headers
        assert "X-Rate-Limit" in config.exposed_headers
    
    def test_allow_origin_pattern(self):
        """Should add origin patterns."""
        config = (
            CORSPolicyBuilder()
            .allow_origin_pattern("https://*.example.com")
            .build()
        )
        
        assert "https://*.example.com" in config.allowed_origin_patterns


# =============================================================================
# Test: Predefined Policies
# =============================================================================

class TestPredefinedPolicies:
    """Test predefined CORS policies."""
    
    def test_strict_policy(self):
        """Should create strict policy."""
        config = strict_cors_policy(["https://example.com"])
        
        assert config.mode == CORSMode.STRICT
        assert "https://example.com" in config.allowed_origins
        assert "OPTIONS" not in config.allowed_methods
    
    def test_permissive_policy(self):
        """Should create permissive policy."""
        config = permissive_cors_policy()
        
        assert config.mode == CORSMode.PERMISSIVE
        assert "OPTIONS" in config.allowed_methods
    
    def test_api_policy(self):
        """Should create API policy."""
        config = api_cors_policy(
            allowed_origins=["https://api.example.com"],
            allow_credentials=True,
        )
        
        assert config.mode == CORSMode.STRICT
        assert config.credentials == CredentialsMode.INCLUDE
        assert "X-RegEngine-API-Key" in config.allowed_headers
        assert "X-Request-ID" in config.exposed_headers


# =============================================================================
# Test: CORS Service
# =============================================================================

class TestCORSService:
    """Test CORSService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        service1 = get_cors_service()
        service2 = get_cors_service()
        
        assert service1 is service2
    
    def test_configure(self):
        """Should configure service."""
        config = CORSConfig(mode=CORSMode.PERMISSIVE)
        service = CORSService.configure(config)
        
        assert service.config.mode == CORSMode.PERMISSIVE
    
    def test_add_remove_origin(self):
        """Should add and remove origins."""
        service = CORSService()
        
        service.add_origin("https://test.com")
        assert service.check_origin("https://test.com") is True
        
        service.remove_origin("https://test.com")
        assert service.check_origin("https://test.com") is False
    
    def test_process_request(self):
        """Should process request."""
        config = CORSConfig(
            mode=CORSMode.STRICT,
            allowed_origins={"https://example.com"},
        )
        service = CORSService(config)
        
        should_continue, headers, error = service.process_request(
            method="GET",
            headers={"Origin": "https://example.com"},
        )
        
        assert should_continue is True


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_cors_service(self):
        """Should return service instance."""
        service = get_cors_service()
        assert service is not None
    
    def test_check_cors_origin(self):
        """Should check origin."""
        # Configure with known origin
        CORSService.configure(CORSConfig(
            mode=CORSMode.STRICT,
            allowed_origins={"https://allowed.com"},
        ))
        
        assert check_cors_origin("https://allowed.com") is True
        assert check_cors_origin("https://blocked.com") is False
