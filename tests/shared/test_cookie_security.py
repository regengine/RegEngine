"""
Tests for SEC-037: Cookie Security.

Tests cover:
- Cookie configuration
- Cookie building
- Cookie parsing
- Cookie validation
- Signed cookies
"""

import pytest
from datetime import datetime, timedelta, timezone

from shared.cookie_security import (
    # Enums
    SameSite,
    CookiePriority,
    # Data classes
    CookieConfig,
    Cookie,
    ParsedCookie,
    # Classes
    CookieBuilder,
    CookieParser,
    CookieValidator,
    SecureCookieManager,
    CookieSecurityService,
    # Convenience functions
    get_cookie_service,
    create_secure_cookie,
    parse_cookies,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create cookie config."""
    return CookieConfig()


@pytest.fixture
def cookie(config):
    """Create a cookie."""
    return Cookie(name="test", value="value", config=config)


@pytest.fixture
def builder():
    """Create cookie builder."""
    return CookieBuilder("session", "abc123")


@pytest.fixture
def parser():
    """Create cookie parser."""
    return CookieParser()


@pytest.fixture
def validator():
    """Create cookie validator."""
    return CookieValidator()


@pytest.fixture
def manager():
    """Create cookie manager."""
    return SecureCookieManager("test-secret-key-12345")


@pytest.fixture
def service():
    """Create cookie service."""
    return CookieSecurityService("test-secret-key-12345")


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_same_site_values(self):
        """Should have expected SameSite values."""
        assert SameSite.STRICT == "Strict"
        assert SameSite.LAX == "Lax"
        assert SameSite.NONE == "None"
    
    def test_cookie_priority_values(self):
        """Should have expected priority values."""
        assert CookiePriority.LOW == "Low"
        assert CookiePriority.MEDIUM == "Medium"
        assert CookiePriority.HIGH == "High"


# =============================================================================
# Test: CookieConfig
# =============================================================================

class TestCookieConfig:
    """Test CookieConfig class."""
    
    def test_default_values(self, config):
        """Should have secure defaults."""
        assert config.secure is True
        assert config.http_only is True
        assert config.same_site == SameSite.LAX
        assert config.path == "/"
    
    def test_validate_same_site_none_requires_secure(self):
        """Should validate SameSite=None requires Secure."""
        config = CookieConfig(same_site=SameSite.NONE, secure=False)
        errors = config.validate()
        
        assert len(errors) > 0
        assert any("Secure" in e for e in errors)
    
    def test_validate_negative_max_age(self):
        """Should validate negative max_age."""
        config = CookieConfig(max_age=-1)
        errors = config.validate()
        
        assert len(errors) > 0
        assert any("negative" in e for e in errors)


# =============================================================================
# Test: Cookie
# =============================================================================

class TestCookie:
    """Test Cookie class."""
    
    def test_to_header_value_basic(self, cookie):
        """Should generate basic header value."""
        value = cookie.to_header_value()
        
        assert "test=value" in value
        assert "Secure" in value
        assert "HttpOnly" in value
        assert "SameSite=Lax" in value
    
    def test_to_header_value_with_max_age(self):
        """Should include Max-Age."""
        config = CookieConfig(max_age=3600)
        cookie = Cookie("test", "value", config)
        value = cookie.to_header_value()
        
        assert "Max-Age=3600" in value
    
    def test_to_header_value_with_expires(self):
        """Should include Expires."""
        expires = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        config = CookieConfig(expires=expires)
        cookie = Cookie("test", "value", config)
        value = cookie.to_header_value()
        
        assert "Expires=" in value
        assert "2025" in value
    
    def test_to_header_value_with_domain(self):
        """Should include Domain."""
        config = CookieConfig(domain=".example.com")
        cookie = Cookie("test", "value", config)
        value = cookie.to_header_value()
        
        assert "Domain=.example.com" in value
    
    def test_to_header_value_encodes_special_chars(self):
        """Should encode special characters."""
        cookie = Cookie("test", "value with spaces", CookieConfig())
        value = cookie.to_header_value()
        
        assert "value%20with%20spaces" in value


# =============================================================================
# Test: CookieBuilder
# =============================================================================

class TestCookieBuilder:
    """Test CookieBuilder fluent interface."""
    
    def test_fluent_building(self, builder):
        """Should support fluent building."""
        cookie = (
            builder
            .secure(True)
            .http_only(True)
            .same_site(SameSite.STRICT)
            .path("/app")
            .max_age(3600)
            .build()
        )
        
        assert cookie.name == "session"
        assert cookie.value == "abc123"
        assert cookie.config.secure is True
        assert cookie.config.same_site == SameSite.STRICT
        assert cookie.config.max_age == 3600
    
    def test_expires_in(self, builder):
        """Should set expiration relative to now."""
        cookie = builder.expires_in(timedelta(hours=1)).build()
        
        assert cookie.config.expires is not None
        # Should be approximately 1 hour from now
        delta = cookie.config.expires - datetime.now(timezone.utc)
        assert 3500 < delta.total_seconds() < 3700
    
    def test_session_cookie(self, builder):
        """Should create session cookie."""
        cookie = builder.session().build()
        
        assert cookie.config.max_age is None
        assert cookie.config.expires is None
    
    def test_to_header_value(self, builder):
        """Should return header value directly."""
        value = builder.secure(True).to_header_value()
        
        assert "Secure" in value


# =============================================================================
# Test: CookieParser
# =============================================================================

class TestCookieParser:
    """Test CookieParser."""
    
    def test_parse_single_cookie(self, parser):
        """Should parse single cookie."""
        cookies = parser.parse("session=abc123")
        
        assert cookies["session"] == "abc123"
    
    def test_parse_multiple_cookies(self, parser):
        """Should parse multiple cookies."""
        cookies = parser.parse("session=abc123; user=john; theme=dark")
        
        assert cookies["session"] == "abc123"
        assert cookies["user"] == "john"
        assert cookies["theme"] == "dark"
    
    def test_parse_empty_header(self, parser):
        """Should handle empty header."""
        cookies = parser.parse("")
        
        assert cookies == {}
    
    def test_parse_url_encoded(self, parser):
        """Should decode URL-encoded values."""
        cookies = parser.parse("name=hello%20world")
        
        assert cookies["name"] == "hello world"
    
    def test_parse_to_list(self, parser):
        """Should parse to list of ParsedCookie."""
        cookies = parser.parse_to_list("a=1; b=2")
        
        assert len(cookies) == 2
        assert isinstance(cookies[0], ParsedCookie)
        assert cookies[0].name == "a"
        assert cookies[0].value == "1"


# =============================================================================
# Test: CookieValidator
# =============================================================================

class TestCookieValidator:
    """Test CookieValidator."""
    
    def test_warns_missing_secure(self, validator):
        """Should warn about missing Secure flag."""
        config = CookieConfig(secure=False)
        cookie = Cookie("test", "value", config)
        
        warnings = validator.validate(cookie)
        
        assert any("Secure" in w for w in warnings)
    
    def test_warns_sensitive_cookie_no_httponly(self, validator):
        """Should warn about sensitive cookie without HttpOnly."""
        config = CookieConfig(http_only=False)
        cookie = Cookie("session", "abc123", config)
        
        warnings = validator.validate(cookie)
        
        assert any("HttpOnly" in w for w in warnings)
    
    def test_warns_same_site_none(self, validator):
        """Should warn about SameSite=None."""
        config = CookieConfig(same_site=SameSite.NONE)
        cookie = Cookie("test", "value", config)
        
        warnings = validator.validate(cookie)
        
        assert any("SameSite=None" in w for w in warnings)
    
    def test_no_warnings_for_secure_cookie(self, validator):
        """Should have no warnings for secure cookie."""
        config = CookieConfig(
            secure=True,
            http_only=True,
            same_site=SameSite.STRICT,
        )
        cookie = Cookie("data", "value", config)
        
        warnings = validator.validate(cookie)
        
        assert len(warnings) == 0


# =============================================================================
# Test: SecureCookieManager
# =============================================================================

class TestSecureCookieManager:
    """Test SecureCookieManager."""
    
    def test_create_cookie(self, manager):
        """Should create cookie with default config."""
        cookie = manager.create("test", "value")
        
        assert cookie.name == "test"
        assert cookie.value == "value"
        assert cookie.config.secure is True
    
    def test_create_signed_cookie(self, manager):
        """Should create signed cookie."""
        cookie = manager.create_signed("test", "value")
        
        assert "." in cookie.value
        parts = cookie.value.split(".")
        assert len(parts) == 2
        assert parts[0] == "value"
    
    def test_verify_signed_valid(self, manager):
        """Should verify valid signed cookie."""
        cookie = manager.create_signed("test", "original_value")
        
        result = manager.verify_signed(cookie.value)
        
        assert result == "original_value"
    
    def test_verify_signed_invalid(self, manager):
        """Should reject invalid signed cookie."""
        result = manager.verify_signed("tampered.invalidsig")
        
        assert result is None
    
    def test_verify_signed_no_dot(self, manager):
        """Should reject unsigned value."""
        result = manager.verify_signed("no_signature")
        
        assert result is None
    
    def test_create_with_host_prefix(self, manager):
        """Should create __Host- cookie."""
        cookie = manager.create_with_host_prefix("session", "abc123")
        
        assert cookie.name.startswith("__Host-")
        assert cookie.config.secure is True
        assert cookie.config.domain is None
        assert cookie.config.path == "/"
    
    def test_create_with_secure_prefix(self, manager):
        """Should create __Secure- cookie."""
        cookie = manager.create_with_secure_prefix("token", "xyz789")
        
        assert cookie.name.startswith("__Secure-")
        assert cookie.config.secure is True
    
    def test_create_session_cookie(self, manager):
        """Should create secure session cookie."""
        cookie = manager.create_session_cookie("session_id_123")
        
        assert "__Host-session" in cookie.name
        assert cookie.config.secure is True
        assert cookie.config.http_only is True
        assert cookie.config.same_site == SameSite.STRICT
    
    def test_delete_cookie(self, manager):
        """Should create deletion cookie."""
        cookie = manager.delete_cookie("old_cookie")
        
        assert cookie.value == ""
        assert cookie.config.max_age == 0


# =============================================================================
# Test: CookieSecurityService
# =============================================================================

class TestCookieSecurityService:
    """Test CookieSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        CookieSecurityService._instance = None
        
        s1 = get_cookie_service()
        s2 = get_cookie_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        service = CookieSecurityService.configure(
            "new-secret-key",
            CookieConfig(same_site=SameSite.STRICT),
        )
        
        assert service.default_config.same_site == SameSite.STRICT
    
    def test_create(self, service):
        """Should create cookie."""
        cookie = service.create("test", "value")
        
        assert cookie.name == "test"
    
    def test_create_signed(self, service):
        """Should create signed cookie."""
        cookie = service.create_signed("test", "value")
        
        assert "." in cookie.value
    
    def test_verify_signed(self, service):
        """Should verify signed cookie."""
        cookie = service.create_signed("test", "original")
        
        result = service.verify_signed(cookie.value)
        
        assert result == "original"
    
    def test_parse(self, service):
        """Should parse cookies."""
        cookies = service.parse("a=1; b=2")
        
        assert cookies["a"] == "1"
        assert cookies["b"] == "2"
    
    def test_validate(self, service):
        """Should validate cookie."""
        cookie = Cookie("test", "value", CookieConfig(secure=False))
        
        warnings = service.validate(cookie)
        
        assert len(warnings) > 0
    
    def test_builder(self, service):
        """Should get builder."""
        builder = service.builder("test", "value")
        
        assert isinstance(builder, CookieBuilder)


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_secure_cookie(self):
        """Should create secure cookie via convenience function."""
        CookieSecurityService._instance = None
        
        header = create_secure_cookie("test", "value")
        
        assert "test=value" in header
        assert "Secure" in header
    
    def test_parse_cookies(self):
        """Should parse cookies via convenience function."""
        CookieSecurityService._instance = None
        
        cookies = parse_cookies("session=abc; theme=dark")
        
        assert cookies["session"] == "abc"
        assert cookies["theme"] == "dark"


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_default_config_is_secure(self):
        """Default config should be secure."""
        config = CookieConfig()
        
        assert config.secure is True
        assert config.http_only is True
        assert config.same_site in (SameSite.STRICT, SameSite.LAX)
    
    def test_signed_cookies_detect_tampering(self, manager):
        """Signed cookies should detect tampering."""
        cookie = manager.create_signed("test", "original")
        
        # Tamper with value
        tampered = cookie.value.replace("original", "modified")
        
        result = manager.verify_signed(tampered)
        
        assert result is None
    
    def test_host_prefix_requirements(self, manager):
        """__Host- prefix should enforce requirements."""
        cookie = manager.create_with_host_prefix("test", "value")
        
        assert cookie.config.secure is True
        assert cookie.config.domain is None
        assert cookie.config.path == "/"
    
    def test_session_cookie_is_secure(self, manager):
        """Session cookies should be maximally secure."""
        cookie = manager.create_session_cookie("session123")
        
        assert cookie.config.secure is True
        assert cookie.config.http_only is True
        assert cookie.config.same_site == SameSite.STRICT
