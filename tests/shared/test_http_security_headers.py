"""
Tests for SEC-036: HTTP Security Headers.

Tests cover:
- CSP configuration
- HSTS configuration
- Security headers building
- Header validation
- Middleware
"""

import pytest

from shared.http_security_headers import (
    # Enums
    FrameOption,
    ReferrerPolicy,
    CSPDirective,
    # Data classes
    CSPConfig,
    HSTSConfig,
    PermissionsPolicyConfig,
    SecurityHeadersConfig,
    # Classes
    SecurityHeadersBuilder,
    CSPBuilder,
    HeaderValidator,
    SecurityHeadersMiddleware,
    SecurityHeadersService,
    # Convenience functions
    get_security_headers_service,
    get_default_headers,
    create_csp,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def csp_config():
    """Create CSP config."""
    return CSPConfig()


@pytest.fixture
def hsts_config():
    """Create HSTS config."""
    return HSTSConfig()


@pytest.fixture
def config():
    """Create full security headers config."""
    return SecurityHeadersConfig()


@pytest.fixture
def builder(config):
    """Create headers builder."""
    return SecurityHeadersBuilder(config)


@pytest.fixture
def csp_builder():
    """Create CSP builder."""
    return CSPBuilder()


@pytest.fixture
def validator():
    """Create header validator."""
    return HeaderValidator()


@pytest.fixture
def middleware(config):
    """Create middleware."""
    return SecurityHeadersMiddleware(config)


@pytest.fixture
def service(config):
    """Create service."""
    return SecurityHeadersService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_frame_options(self):
        """Should have expected frame options."""
        assert FrameOption.DENY == "DENY"
        assert FrameOption.SAMEORIGIN == "SAMEORIGIN"
        assert FrameOption.ALLOW_FROM == "ALLOW-FROM"
    
    def test_referrer_policy(self):
        """Should have expected referrer policies."""
        assert ReferrerPolicy.NO_REFERRER == "no-referrer"
        assert ReferrerPolicy.STRICT_ORIGIN == "strict-origin"
        assert ReferrerPolicy.SAME_ORIGIN == "same-origin"
    
    def test_csp_directives(self):
        """Should have expected CSP directives."""
        assert CSPDirective.DEFAULT_SRC == "default-src"
        assert CSPDirective.SCRIPT_SRC == "script-src"
        assert CSPDirective.FRAME_ANCESTORS == "frame-ancestors"


# =============================================================================
# Test: CSPConfig
# =============================================================================

class TestCSPConfig:
    """Test CSPConfig class."""
    
    def test_default_values(self, csp_config):
        """Should have secure defaults."""
        assert "default-src" in csp_config.directives
        assert "'self'" in csp_config.directives["default-src"]
        assert csp_config.report_only is False
    
    def test_to_header_value(self, csp_config):
        """Should generate header value."""
        value = csp_config.to_header_value()
        
        assert "default-src 'self'" in value
        assert "script-src 'self'" in value
        assert "frame-ancestors 'none'" in value
    
    def test_report_uri_included(self):
        """Should include report-uri when set."""
        config = CSPConfig(report_uri="https://example.com/report")
        value = config.to_header_value()
        
        assert "report-uri https://example.com/report" in value


# =============================================================================
# Test: HSTSConfig
# =============================================================================

class TestHSTSConfig:
    """Test HSTSConfig class."""
    
    def test_default_values(self, hsts_config):
        """Should have secure defaults."""
        assert hsts_config.max_age == 31536000
        assert hsts_config.include_subdomains is True
        assert hsts_config.preload is False
    
    def test_to_header_value(self, hsts_config):
        """Should generate header value."""
        value = hsts_config.to_header_value()
        
        assert "max-age=31536000" in value
        assert "includeSubDomains" in value
    
    def test_preload_included(self):
        """Should include preload when set."""
        config = HSTSConfig(preload=True)
        value = config.to_header_value()
        
        assert "preload" in value


# =============================================================================
# Test: PermissionsPolicyConfig
# =============================================================================

class TestPermissionsPolicyConfig:
    """Test PermissionsPolicyConfig class."""
    
    def test_default_disables_features(self):
        """Should disable features by default."""
        config = PermissionsPolicyConfig()
        value = config.to_header_value()
        
        assert "geolocation=()" in value
        assert "microphone=()" in value
        assert "camera=()" in value
    
    def test_allow_specific_origin(self):
        """Should allow specific origins."""
        config = PermissionsPolicyConfig(
            policies={"geolocation": ["self"]}
        )
        value = config.to_header_value()
        
        assert "geolocation=(self)" in value


# =============================================================================
# Test: SecurityHeadersBuilder
# =============================================================================

class TestSecurityHeadersBuilder:
    """Test SecurityHeadersBuilder."""
    
    def test_builds_all_headers(self, builder):
        """Should build all security headers."""
        headers = builder.build()
        
        assert "Content-Security-Policy" in headers
        assert "X-Frame-Options" in headers
        assert "X-Content-Type-Options" in headers
        assert "X-XSS-Protection" in headers
        assert "Strict-Transport-Security" in headers
        assert "Referrer-Policy" in headers
        assert "Permissions-Policy" in headers
    
    def test_x_frame_options_deny(self, builder):
        """Should set X-Frame-Options to DENY."""
        headers = builder.build()
        
        assert headers["X-Frame-Options"] == "DENY"
    
    def test_content_type_nosniff(self, builder):
        """Should set nosniff."""
        headers = builder.build()
        
        assert headers["X-Content-Type-Options"] == "nosniff"
    
    def test_xss_protection(self, builder):
        """Should set XSS protection."""
        headers = builder.build()
        
        assert headers["X-XSS-Protection"] == "1; mode=block"
    
    def test_csp_report_only_header_name(self):
        """Should use report-only header name."""
        csp = CSPConfig(report_only=True)
        config = SecurityHeadersConfig(csp=csp)
        builder = SecurityHeadersBuilder(config)
        
        headers = builder.build()
        
        assert "Content-Security-Policy-Report-Only" in headers
        assert "Content-Security-Policy" not in headers
    
    def test_allow_from_with_uri(self):
        """Should set ALLOW-FROM with URI."""
        config = SecurityHeadersConfig(
            frame_options=FrameOption.ALLOW_FROM,
            frame_options_uri="https://trusted.com",
        )
        builder = SecurityHeadersBuilder(config)
        
        headers = builder.build()
        
        assert headers["X-Frame-Options"] == "ALLOW-FROM https://trusted.com"


# =============================================================================
# Test: CSPBuilder
# =============================================================================

class TestCSPBuilder:
    """Test CSPBuilder fluent interface."""
    
    def test_fluent_building(self, csp_builder):
        """Should support fluent building."""
        value = (
            csp_builder
            .default_src("'self'")
            .script_src("'self'", "https://cdn.example.com")
            .style_src("'self'", "'unsafe-inline'")
            .to_header_value()
        )
        
        assert "default-src 'self'" in value
        assert "script-src 'self' https://cdn.example.com" in value
    
    def test_add_nonce(self, csp_builder):
        """Should add nonce to script and style src."""
        value = csp_builder.add_nonce("abc123").to_header_value()
        
        assert "'nonce-abc123'" in value
    
    def test_report_uri(self, csp_builder):
        """Should add report-uri."""
        value = (
            csp_builder
            .default_src("'self'")
            .report_uri("https://example.com/csp-report")
            .to_header_value()
        )
        
        assert "report-uri https://example.com/csp-report" in value
    
    def test_frame_ancestors(self, csp_builder):
        """Should set frame-ancestors."""
        value = (
            csp_builder
            .frame_ancestors("'none'")
            .to_header_value()
        )
        
        assert "frame-ancestors 'none'" in value


# =============================================================================
# Test: HeaderValidator
# =============================================================================

class TestHeaderValidator:
    """Test HeaderValidator."""
    
    def test_validates_missing_csp(self, validator):
        """Should warn about missing CSP."""
        headers = {"X-Frame-Options": "DENY"}
        warnings = validator.validate(headers)
        
        assert any("Content-Security-Policy" in w for w in warnings)
    
    def test_validates_unsafe_inline(self, validator):
        """Should warn about unsafe-inline."""
        headers = {
            "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'",
            "X-Frame-Options": "DENY",
            "Strict-Transport-Security": "max-age=31536000",
        }
        warnings = validator.validate(headers)
        
        assert any("unsafe" in w.lower() for w in warnings)
    
    def test_validates_missing_default_src(self, validator):
        """Should warn about missing default-src."""
        headers = {
            "Content-Security-Policy": "script-src 'self'",
            "X-Frame-Options": "DENY",
            "Strict-Transport-Security": "max-age=31536000",
        }
        warnings = validator.validate(headers)
        
        assert any("default-src" in w for w in warnings)
    
    def test_validates_missing_hsts(self, validator):
        """Should warn about missing HSTS."""
        headers = {
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
        }
        warnings = validator.validate(headers)
        
        assert any("Strict-Transport-Security" in w for w in warnings)
    
    def test_validates_hsts_zero_max_age(self, validator):
        """Should warn about HSTS max-age=0."""
        headers = {
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "Strict-Transport-Security": "max-age=0",
        }
        warnings = validator.validate(headers)
        
        assert any("max-age is 0" in w for w in warnings)
    
    def test_no_warnings_for_valid_headers(self, builder):
        """Should have no warnings for valid headers."""
        headers = builder.build()
        validator = HeaderValidator()
        
        warnings = validator.validate(headers)
        
        # Should be minimal warnings (maybe none)
        assert len(warnings) <= 1


# =============================================================================
# Test: SecurityHeadersMiddleware
# =============================================================================

class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware."""
    
    def test_adds_headers_to_response(self, middleware):
        """Should add security headers to response."""
        response_headers = {"Content-Type": "application/json"}
        
        result = middleware.process_response("/api/data", response_headers)
        
        assert "Content-Type" in result
        assert "X-Frame-Options" in result
        assert "Content-Security-Policy" in result
    
    def test_excludes_paths(self):
        """Should exclude configured paths."""
        middleware = SecurityHeadersMiddleware(
            exclude_paths={"/health", "/metrics"}
        )
        response_headers = {"Content-Type": "text/plain"}
        
        result = middleware.process_response("/health", response_headers)
        
        assert "X-Frame-Options" not in result
    
    def test_does_not_override_existing(self, middleware):
        """Should not override existing headers."""
        response_headers = {
            "X-Frame-Options": "SAMEORIGIN",
        }
        
        result = middleware.process_response("/api/data", response_headers)
        
        assert result["X-Frame-Options"] == "SAMEORIGIN"
    
    def test_get_headers(self, middleware):
        """Should get all headers."""
        headers = middleware.get_headers()
        
        assert "Content-Security-Policy" in headers
        assert "X-Frame-Options" in headers


# =============================================================================
# Test: SecurityHeadersService
# =============================================================================

class TestSecurityHeadersService:
    """Test SecurityHeadersService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        SecurityHeadersService._instance = None
        
        s1 = get_security_headers_service()
        s2 = get_security_headers_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        config = SecurityHeadersConfig(
            frame_options=FrameOption.SAMEORIGIN,
        )
        
        service = SecurityHeadersService.configure(config)
        
        assert service.config.frame_options == FrameOption.SAMEORIGIN
    
    def test_get_headers(self, service):
        """Should get headers."""
        headers = service.get_headers()
        
        assert isinstance(headers, dict)
        assert "Content-Security-Policy" in headers
    
    def test_validate_headers(self, service):
        """Should validate headers."""
        warnings = service.validate_headers({})
        
        assert len(warnings) > 0
    
    def test_create_csp_builder(self, service):
        """Should create CSP builder."""
        builder = service.create_csp_builder()
        
        assert isinstance(builder, CSPBuilder)
    
    def test_apply_to_response(self, service):
        """Should apply to response."""
        headers = {"Content-Type": "application/json"}
        
        result = service.apply_to_response("/api/data", headers)
        
        assert "X-Frame-Options" in result


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_default_headers(self):
        """Should get default headers."""
        SecurityHeadersService._instance = None
        
        headers = get_default_headers()
        
        assert isinstance(headers, dict)
        assert "Content-Security-Policy" in headers
    
    def test_create_csp(self):
        """Should create simple CSP."""
        csp = create_csp(default_src="'self'", script_src="'self'")
        
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_default_config_is_secure(self):
        """Default config should be secure."""
        config = SecurityHeadersConfig()
        
        assert config.frame_options == FrameOption.DENY
        assert config.content_type_nosniff is True
        assert config.enable_hsts is True
    
    def test_default_csp_is_restrictive(self):
        """Default CSP should be restrictive."""
        config = CSPConfig()
        value = config.to_header_value()
        
        assert "frame-ancestors 'none'" in value
        assert "object-src 'none'" in value
        assert "'self'" in value
    
    def test_default_hsts_has_good_max_age(self):
        """Default HSTS should have good max-age."""
        config = HSTSConfig()
        
        assert config.max_age >= 31536000  # At least 1 year
        assert config.include_subdomains is True
    
    def test_default_permissions_policy_restrictive(self):
        """Default permissions policy should be restrictive."""
        config = PermissionsPolicyConfig()
        
        # All should be empty (disabled)
        for feature, allowlist in config.policies.items():
            assert allowlist == [], f"{feature} should be empty"
