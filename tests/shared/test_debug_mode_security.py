"""
Tests for SEC-034: Debug Mode Security.

Tests cover:
- Debug mode detection
- Environment validation
- Debug access control
- Information filtering
- Security warnings
"""

import pytest
import os
from unittest.mock import patch

from shared.debug_mode_security import (
    # Enums
    DebugLevel,
    Environment,
    # Data classes
    DebugConfig,
    DebugAccessAttempt,
    # Classes
    DebugModeDetector,
    DebugAccessController,
    DebugEndpointGuard,
    DebugInfoFilter,
    DebugModeService,
    DebugAccessDenied,
    SecurityWarning,
    # Convenience functions
    get_debug_service,
    is_debug_enabled,
    is_production,
    protect_debug_endpoint,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def detector():
    """Create debug mode detector."""
    return DebugModeDetector()


@pytest.fixture
def config():
    """Create debug config."""
    return DebugConfig(
        enabled=True,
        level=DebugLevel.STANDARD,
        environment=Environment.DEVELOPMENT,
    )


@pytest.fixture
def controller(config):
    """Create debug access controller."""
    return DebugAccessController(config)


@pytest.fixture
def guard(controller):
    """Create debug endpoint guard."""
    return DebugEndpointGuard(controller)


@pytest.fixture
def filter(config):
    """Create debug info filter."""
    return DebugInfoFilter(config)


@pytest.fixture
def service(config):
    """Create debug mode service."""
    return DebugModeService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_debug_levels(self):
        """Should have expected debug levels."""
        assert DebugLevel.DISABLED == "disabled"
        assert DebugLevel.MINIMAL == "minimal"
        assert DebugLevel.STANDARD == "standard"
        assert DebugLevel.VERBOSE == "verbose"
        assert DebugLevel.FULL == "full"
    
    def test_environments(self):
        """Should have expected environments."""
        assert Environment.LOCAL == "local"
        assert Environment.DEVELOPMENT == "development"
        assert Environment.TESTING == "testing"
        assert Environment.STAGING == "staging"
        assert Environment.PRODUCTION == "production"


# =============================================================================
# Test: DebugConfig
# =============================================================================

class TestDebugConfig:
    """Test DebugConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = DebugConfig()
        
        assert config.enabled is False
        assert config.level == DebugLevel.DISABLED
        assert config.environment == Environment.PRODUCTION
        assert config.require_auth is True
    
    def test_is_debug_allowed_dev(self):
        """Should allow debug in development."""
        config = DebugConfig(environment=Environment.DEVELOPMENT)
        
        assert config.is_debug_allowed() is True
    
    def test_is_debug_allowed_prod(self):
        """Should not allow debug in production."""
        config = DebugConfig(environment=Environment.PRODUCTION)
        
        assert config.is_debug_allowed() is False


# =============================================================================
# Test: DebugModeDetector
# =============================================================================

class TestDebugModeDetector:
    """Test DebugModeDetector."""
    
    def test_detect_debug_false_by_default(self, detector):
        """Should not detect debug by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert detector.detect_debug_mode() is False
    
    def test_detect_debug_from_env(self, detector):
        """Should detect debug from environment variable."""
        with patch.dict(os.environ, {"DEBUG": "true"}):
            assert detector.detect_debug_mode() is True
    
    def test_detect_debug_from_flask(self, detector):
        """Should detect Flask debug mode."""
        with patch.dict(os.environ, {"FLASK_DEBUG": "1"}):
            assert detector.detect_debug_mode() is True
    
    def test_detect_environment_default(self, detector):
        """Should default to production."""
        with patch.dict(os.environ, {}, clear=True):
            assert detector.detect_environment() == Environment.PRODUCTION
    
    def test_detect_environment_development(self, detector):
        """Should detect development environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert detector.detect_environment() == Environment.DEVELOPMENT
    
    def test_detect_environment_from_app_env(self, detector):
        """Should detect from APP_ENV."""
        with patch.dict(os.environ, {"APP_ENV": "staging"}, clear=True):
            assert detector.detect_environment() == Environment.STAGING
    
    def test_is_production(self, detector):
        """Should detect production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            assert detector.is_production() is True
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert detector.is_production() is False
    
    def test_validate_debug_settings_warns_in_prod(self, detector):
        """Should warn about debug in production."""
        with patch.dict(os.environ, {"DEBUG": "true", "ENVIRONMENT": "production"}):
            warnings = detector.validate_debug_settings()
            
            assert len(warnings) > 0
            assert any("CRITICAL" in w for w in warnings)
    
    def test_validate_debug_settings_ok_in_dev(self, detector):
        """Should not warn in development."""
        with patch.dict(os.environ, {"DEBUG": "true", "ENVIRONMENT": "development"}):
            warnings = detector.validate_debug_settings()
            
            assert not any("CRITICAL" in w for w in warnings)


# =============================================================================
# Test: DebugAccessController
# =============================================================================

class TestDebugAccessController:
    """Test DebugAccessController."""
    
    def test_access_denied_when_disabled(self):
        """Should deny access when debug disabled."""
        config = DebugConfig(enabled=False)
        controller = DebugAccessController(config)
        
        allowed, reason = controller.is_access_allowed("127.0.0.1")
        
        assert allowed is False
        assert "disabled" in reason.lower()
    
    def test_access_denied_in_production(self):
        """Should deny access in production."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        controller = DebugAccessController(config)
        
        allowed, reason = controller.is_access_allowed("127.0.0.1")
        
        assert allowed is False
        assert "not allowed" in reason.lower()
    
    def test_access_denied_wrong_ip(self):
        """Should deny access from wrong IP."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.DEVELOPMENT,
            allowed_ips={"127.0.0.1"},
        )
        controller = DebugAccessController(config)
        
        allowed, reason = controller.is_access_allowed("192.168.1.100")
        
        assert allowed is False
        assert "not in allowed" in reason.lower()
    
    def test_access_denied_no_auth(self):
        """Should deny access without auth when required."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.DEVELOPMENT,
            require_auth=True,
            allowed_ips=set(),  # Allow any IP
        )
        controller = DebugAccessController(config)
        
        allowed, reason = controller.is_access_allowed("127.0.0.1", user_id=None)
        
        assert allowed is False
        assert "authentication" in reason.lower()
    
    def test_access_allowed(self, controller):
        """Should allow valid access."""
        allowed, reason = controller.is_access_allowed(
            ip_address="127.0.0.1",
            user_id="admin",
        )
        
        assert allowed is True
    
    def test_records_access(self, controller):
        """Should record access attempts."""
        controller.is_access_allowed("127.0.0.1", user_id="admin")
        controller.record_access(
            ip_address="127.0.0.1",
            endpoint="/debug",
            user_id="admin",
            allowed=True,
            reason="test",
        )
        
        log = controller.get_access_log()
        
        assert len(log) > 0
        assert log[-1].ip_address == "127.0.0.1"


# =============================================================================
# Test: DebugEndpointGuard
# =============================================================================

class TestDebugEndpointGuard:
    """Test DebugEndpointGuard."""
    
    def test_protect_decorator_allows(self, guard):
        """Should allow decorated endpoint access."""
        @guard.protect(
            get_ip=lambda: "127.0.0.1",
            get_user=lambda: "admin",
        )
        def debug_endpoint():
            return "debug_data"
        
        result = debug_endpoint()
        
        assert result == "debug_data"
    
    def test_protect_decorator_denies(self):
        """Should deny unauthorized access."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        guard = DebugEndpointGuard(DebugAccessController(config))
        
        @guard.protect(
            get_ip=lambda: "127.0.0.1",
            get_user=lambda: "admin",
        )
        def debug_endpoint():
            return "debug_data"
        
        with pytest.raises(DebugAccessDenied):
            debug_endpoint()
    
    def test_check_access(self, guard):
        """Should check access without decorator."""
        result = guard.check_access("127.0.0.1", "admin")
        
        assert result is True


# =============================================================================
# Test: DebugInfoFilter
# =============================================================================

class TestDebugInfoFilter:
    """Test DebugInfoFilter."""
    
    def test_removes_debug_fields_when_disabled(self):
        """Should remove debug fields when debug disabled."""
        config = DebugConfig(enabled=False)
        filter = DebugInfoFilter(config)
        
        data = {
            "result": "success",
            "debug_info": "sensitive",
            "stack_trace": "Error at line 42",
        }
        
        filtered = filter.filter_response(data)
        
        assert "result" in filtered
        assert "debug_info" not in filtered
        assert "stack_trace" not in filtered
    
    def test_keeps_debug_fields_when_enabled(self, filter):
        """Should keep debug fields when enabled in dev."""
        data = {
            "result": "success",
            "debug_info": "info",
        }
        
        # filter fixture uses dev config with debug enabled
        filtered = filter.filter_response(data, include_debug=True)
        
        assert "result" in filtered
        assert "debug_info" in filtered
    
    def test_removes_nested_debug_fields(self):
        """Should remove nested debug fields."""
        config = DebugConfig(enabled=False)
        filter = DebugInfoFilter(config)
        
        data = {
            "data": {
                "value": 1,
                "sql": "SELECT * FROM users",
            }
        }
        
        filtered = filter.filter_response(data)
        
        assert "value" in filtered["data"]
        assert "sql" not in filtered["data"]
    
    def test_get_error_detail_level_production(self):
        """Should return minimal in production."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        filter = DebugInfoFilter(config)
        
        assert filter.get_error_detail_level() == "minimal"
    
    def test_get_error_detail_level_development(self, filter):
        """Should return based on debug level."""
        assert filter.get_error_detail_level() == "detailed"


# =============================================================================
# Test: DebugModeService
# =============================================================================

class TestDebugModeService:
    """Test DebugModeService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        # Reset singleton for test
        DebugModeService._instance = None
        
        s1 = get_debug_service()
        s2 = get_debug_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.DEVELOPMENT,
        )
        
        service = DebugModeService.configure(config)
        
        assert service.config.enabled is True
    
    def test_is_debug_enabled(self, service):
        """Should check if debug enabled."""
        assert service.is_debug_enabled() is True
    
    def test_is_debug_enabled_false_in_prod(self):
        """Should return false in production."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        service = DebugModeService(config)
        
        assert service.is_debug_enabled() is False
    
    def test_check_access(self, service):
        """Should check access."""
        result = service.check_access("127.0.0.1", "admin")
        
        assert result is True
    
    def test_filter_response(self, service):
        """Should filter response."""
        data = {"result": "ok", "debug": "info"}
        
        # Since debug is enabled in dev, debug field should be kept
        filtered = service.filter_response(data)
        
        assert "result" in filtered
    
    def test_get_security_warnings(self):
        """Should get security warnings."""
        with patch.dict(os.environ, {"DEBUG": "true", "ENVIRONMENT": "production"}):
            service = DebugModeService()
            warnings = service.get_security_warnings()
            
            assert len(warnings) > 0


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_is_debug_enabled(self):
        """Should check via convenience function."""
        DebugModeService._instance = None
        
        with patch.dict(os.environ, {"DEBUG": "false"}, clear=True):
            result = is_debug_enabled()
            # Default to production where debug not allowed
            assert result is False
    
    def test_is_production(self):
        """Should check production via convenience function."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            assert is_production() is True
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert is_production() is False


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_default_config_is_secure(self):
        """Default config should be secure."""
        config = DebugConfig()
        
        assert config.enabled is False
        assert config.environment == Environment.PRODUCTION
        assert config.require_auth is True
        assert config.is_debug_allowed() is False
    
    def test_production_blocks_debug_access(self):
        """Production should block all debug access."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        controller = DebugAccessController(config)
        
        # Even with valid credentials
        allowed, _ = controller.is_access_allowed(
            ip_address="127.0.0.1",
            user_id="admin",
        )
        
        assert allowed is False
    
    def test_cannot_bypass_with_ip_in_production(self):
        """Should not allow IP bypass in production."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
            allowed_ips={"127.0.0.1"},
        )
        controller = DebugAccessController(config)
        
        allowed, _ = controller.is_access_allowed("127.0.0.1")
        
        assert allowed is False
    
    def test_debug_fields_removed_in_production(self):
        """Debug fields should be removed in production."""
        config = DebugConfig(
            enabled=True,
            environment=Environment.PRODUCTION,
        )
        filter = DebugInfoFilter(config)
        
        data = {
            "result": "ok",
            "debug_info": "sensitive info",
            "stack_trace": "internal trace",
        }
        
        filtered = filter.filter_response(data, include_debug=True)
        
        assert "debug_info" not in filtered
        assert "stack_trace" not in filtered
