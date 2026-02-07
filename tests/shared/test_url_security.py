"""
Tests for SEC-038: URL Validation and Sanitization.

Tests cover:
- URL validation
- Protocol whitelisting
- Domain validation
- Open redirect prevention
- URL sanitization
"""

import pytest

from shared.url_security import (
    # Enums
    URLValidationResult,
    # Data classes
    URLConfig,
    ParsedURL,
    RedirectValidation,
    # Classes
    URLValidator,
    OpenRedirectValidator,
    URLSanitizer,
    URLSecurityService,
    # Convenience functions
    get_url_service,
    validate_url,
    sanitize_url,
    is_safe_redirect,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create URL config."""
    return URLConfig()


@pytest.fixture
def validator(config):
    """Create URL validator."""
    return URLValidator(config)


@pytest.fixture
def redirect_validator():
    """Create redirect validator."""
    return OpenRedirectValidator(
        allowed_hosts={"trusted.com", "example.com"},
        allow_relative=True,
    )


@pytest.fixture
def sanitizer(config):
    """Create URL sanitizer."""
    return URLSanitizer(config)


@pytest.fixture
def service(config):
    """Create URL service."""
    return URLSecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_validation_results(self):
        """Should have expected validation results."""
        assert URLValidationResult.VALID == "valid"
        assert URLValidationResult.INVALID_SCHEME == "invalid_scheme"
        assert URLValidationResult.BLOCKED_DOMAIN == "blocked_domain"
        assert URLValidationResult.OPEN_REDIRECT == "open_redirect"


# =============================================================================
# Test: URLConfig
# =============================================================================

class TestURLConfig:
    """Test URLConfig class."""
    
    def test_default_values(self, config):
        """Should have secure defaults."""
        assert "https" in config.allowed_schemes
        assert "http" not in config.allowed_schemes
        assert "localhost" in config.blocked_hosts
        assert "127.0.0.1" in config.blocked_hosts
        assert config.allow_ip_addresses is False


# =============================================================================
# Test: URLValidator
# =============================================================================

class TestURLValidator:
    """Test URLValidator."""
    
    def test_valid_https_url(self, validator):
        """Should accept valid HTTPS URL."""
        is_valid, result = validator.validate("https://example.com/path")
        
        assert is_valid is True
        assert result == URLValidationResult.VALID
    
    def test_invalid_http_url(self, validator):
        """Should reject HTTP URL by default."""
        is_valid, result = validator.validate("http://example.com")
        
        assert is_valid is False
        assert result == URLValidationResult.INVALID_SCHEME
    
    def test_invalid_javascript_url(self, validator):
        """Should reject javascript: URL."""
        is_valid, result = validator.validate("javascript:alert(1)")
        
        assert is_valid is False
        assert result == URLValidationResult.INVALID_SCHEME
    
    def test_blocked_localhost(self, validator):
        """Should block localhost."""
        is_valid, result = validator.validate("https://localhost/api")
        
        assert is_valid is False
        assert result == URLValidationResult.BLOCKED_DOMAIN
    
    def test_blocked_127_0_0_1(self, validator):
        """Should block 127.0.0.1."""
        is_valid, result = validator.validate("https://127.0.0.1/api")
        
        assert is_valid is False
        assert result == URLValidationResult.BLOCKED_DOMAIN
    
    def test_blocked_ip_addresses(self, validator):
        """Should block IP addresses by default."""
        is_valid, result = validator.validate("https://192.168.1.1/api")
        
        assert is_valid is False
        assert result == URLValidationResult.INVALID_HOST
    
    def test_allow_ip_addresses_when_enabled(self):
        """Should allow IP when enabled."""
        config = URLConfig(allow_ip_addresses=True, blocked_hosts=set())
        validator = URLValidator(config)
        
        is_valid, result = validator.validate("https://192.168.1.1/api")
        
        assert is_valid is True
    
    def test_url_too_long(self, validator):
        """Should reject very long URLs."""
        long_url = "https://example.com/" + "a" * 3000
        
        is_valid, result = validator.validate(long_url)
        
        assert is_valid is False
        assert result == URLValidationResult.MALFORMED
    
    def test_parse_valid_url(self, validator):
        """Should parse valid URL."""
        parsed = validator.parse("https://example.com:8080/path?query=1#hash")
        
        assert parsed.is_valid is True
        assert parsed.scheme == "https"
        assert parsed.host == "example.com"
        assert parsed.port == 8080
        assert parsed.path == "/path"
        assert parsed.query == "query=1"
        assert parsed.fragment == "hash"
    
    def test_parse_invalid_url(self, validator):
        """Should mark invalid URL."""
        parsed = validator.parse("javascript:alert(1)")
        
        assert parsed.is_valid is False
        assert parsed.validation_result == URLValidationResult.INVALID_SCHEME


# =============================================================================
# Test: OpenRedirectValidator
# =============================================================================

class TestOpenRedirectValidator:
    """Test OpenRedirectValidator."""
    
    def test_same_host_allowed(self, redirect_validator):
        """Should allow redirect to same host."""
        result = redirect_validator.is_safe_redirect(
            "https://mysite.com/page",
            "mysite.com",
        )
        
        assert result.is_safe is True
    
    def test_relative_url_allowed(self, redirect_validator):
        """Should allow relative URLs."""
        result = redirect_validator.is_safe_redirect(
            "/dashboard",
            "mysite.com",
        )
        
        assert result.is_safe is True
    
    def test_allowed_host(self, redirect_validator):
        """Should allow configured hosts."""
        result = redirect_validator.is_safe_redirect(
            "https://trusted.com/page",
            "mysite.com",
        )
        
        assert result.is_safe is True
    
    def test_subdomain_of_allowed(self, redirect_validator):
        """Should allow subdomain of allowed host."""
        result = redirect_validator.is_safe_redirect(
            "https://sub.trusted.com/page",
            "mysite.com",
        )
        
        assert result.is_safe is True
    
    def test_blocks_evil_host(self, redirect_validator):
        """Should block unknown hosts."""
        result = redirect_validator.is_safe_redirect(
            "https://evil.com/phishing",
            "mysite.com",
        )
        
        assert result.is_safe is False
        assert "not in allowed" in result.reason
    
    def test_blocks_protocol_relative(self, redirect_validator):
        """Should block protocol-relative URLs."""
        result = redirect_validator.is_safe_redirect(
            "//evil.com/page",
            "mysite.com",
        )
        
        assert result.is_safe is False
        assert "Protocol-relative" in result.reason
    
    def test_blocks_javascript_scheme(self, redirect_validator):
        """Should block javascript: URLs."""
        result = redirect_validator.is_safe_redirect(
            "javascript:alert(document.cookie)",
            "mysite.com",
        )
        
        assert result.is_safe is False
        assert "Dangerous" in result.reason
    
    def test_blocks_data_scheme(self, redirect_validator):
        """Should block data: URLs."""
        result = redirect_validator.is_safe_redirect(
            "data:text/html,<script>alert(1)</script>",
            "mysite.com",
        )
        
        assert result.is_safe is False


# =============================================================================
# Test: URLSanitizer
# =============================================================================

class TestURLSanitizer:
    """Test URLSanitizer."""
    
    def test_removes_null_bytes(self, sanitizer):
        """Should remove null bytes."""
        result = sanitizer.sanitize("https://example.com/path\x00/file")
        
        assert "\x00" not in result
    
    def test_removes_path_traversal(self, sanitizer):
        """Should remove path traversal."""
        result = sanitizer.sanitize("https://example.com/../../../etc/passwd")
        
        assert "../" not in result
    
    def test_normalizes_scheme(self, sanitizer):
        """Should normalize scheme to lowercase."""
        result = sanitizer.sanitize("HTTPS://EXAMPLE.COM/Path")
        
        assert result.startswith("https://")
    
    def test_sanitizes_for_html(self, sanitizer):
        """Should HTML-encode for attributes."""
        result = sanitizer.sanitize_for_html(
            "https://example.com/?q=<script>"
        )
        
        # Should not contain raw < or >
        assert "<" not in result
        assert ">" not in result
    
    def test_preserves_valid_url(self, sanitizer):
        """Should preserve valid URLs."""
        url = "https://example.com/path?query=value"
        result = sanitizer.sanitize(url)
        
        assert "example.com" in result
        assert "/path" in result


# =============================================================================
# Test: URLSecurityService
# =============================================================================

class TestURLSecurityService:
    """Test URLSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        URLSecurityService._instance = None
        
        s1 = get_url_service()
        s2 = get_url_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        config = URLConfig(allowed_schemes={"https", "http"})
        
        service = URLSecurityService.configure(config)
        
        assert "http" in service.config.allowed_schemes
    
    def test_validate(self, service):
        """Should validate URLs."""
        is_valid, result = service.validate("https://example.com")
        
        assert is_valid is True
    
    def test_parse(self, service):
        """Should parse URLs."""
        parsed = service.parse("https://example.com/path")
        
        assert parsed.host == "example.com"
    
    def test_sanitize(self, service):
        """Should sanitize URLs."""
        result = service.sanitize("https://example.com/../path")
        
        assert "../" not in result
    
    def test_is_safe_redirect(self, service):
        """Should check redirect safety."""
        service.configure_redirect_validator({"trusted.com"})
        
        result = service.is_safe_redirect(
            "https://trusted.com/page",
            "mysite.com",
        )
        
        assert result.is_safe is True


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_validate_url(self):
        """Should validate via convenience function."""
        URLSecurityService._instance = None
        
        assert validate_url("https://example.com") is True
        assert validate_url("javascript:alert(1)") is False
    
    def test_sanitize_url(self):
        """Should sanitize via convenience function."""
        URLSecurityService._instance = None
        
        result = sanitize_url("https://example.com/../path")
        
        assert "../" not in result
    
    def test_is_safe_redirect(self):
        """Should check redirect via convenience function."""
        URLSecurityService._instance = None
        
        # Same host should be safe
        assert is_safe_redirect("/page", "example.com") is True


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_default_blocks_http(self):
        """Default should block HTTP."""
        validator = URLValidator()
        
        is_valid, _ = validator.validate("http://example.com")
        
        assert is_valid is False
    
    def test_default_blocks_localhost(self):
        """Default should block localhost."""
        validator = URLValidator()
        
        is_valid, _ = validator.validate("https://localhost")
        
        assert is_valid is False
    
    def test_default_blocks_ip(self):
        """Default should block IP addresses."""
        validator = URLValidator()
        
        is_valid, _ = validator.validate("https://10.0.0.1")
        
        assert is_valid is False
    
    def test_prevents_open_redirect(self):
        """Should prevent open redirect."""
        validator = OpenRedirectValidator(allowed_hosts=set())
        
        result = validator.is_safe_redirect(
            "https://evil.com",
            "good.com",
        )
        
        assert result.is_safe is False
    
    def test_blocks_ssrf_vectors(self):
        """Should block common SSRF vectors."""
        validator = URLValidator()
        
        ssrf_urls = [
            "https://localhost/admin",
            "https://127.0.0.1/",
            "https://0.0.0.0/",
            "https://[::1]/",
        ]
        
        for url in ssrf_urls:
            is_valid, _ = validator.validate(url)
            assert is_valid is False, f"Should block {url}"
