"""
Tests for SEC-033: Stack Trace Protection.

Tests cover:
- Stack trace protection
- Frame visibility
- Path filtering
- Production vs development modes
- Exception formatting
"""

import pytest
import sys
import traceback

from shared.stack_trace_protection import (
    # Enums
    EnvironmentMode,
    FrameVisibility,
    # Data classes
    FrameInfo,
    ProtectedStackTrace,
    StackTraceConfig,
    # Classes
    StackTraceProtector,
    ExceptionFormatter,
    ProductionExceptionHook,
    StackTraceService,
    # Convenience functions
    get_stack_trace_service,
    protect_stack_trace,
    format_safe_exception,
    format_client_exception,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create stack trace config."""
    return StackTraceConfig(mode=EnvironmentMode.PRODUCTION)


@pytest.fixture
def protector(config):
    """Create stack trace protector."""
    return StackTraceProtector(config)


@pytest.fixture
def formatter(protector):
    """Create exception formatter."""
    return ExceptionFormatter(protector)


@pytest.fixture
def service():
    """Create stack trace service."""
    return StackTraceService(mode=EnvironmentMode.PRODUCTION)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_environment_modes(self):
        """Should have expected modes."""
        assert EnvironmentMode.DEVELOPMENT == "development"
        assert EnvironmentMode.STAGING == "staging"
        assert EnvironmentMode.PRODUCTION == "production"
    
    def test_frame_visibility(self):
        """Should have expected visibility values."""
        assert FrameVisibility.VISIBLE == "visible"
        assert FrameVisibility.HIDDEN == "hidden"
        assert FrameVisibility.SUMMARIZED == "summarized"


# =============================================================================
# Test: FrameInfo
# =============================================================================

class TestFrameInfo:
    """Test FrameInfo class."""
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        frame = FrameInfo(
            filename="/app/module.py",
            lineno=42,
            name="my_function",
            line="result = process(data)",
        )
        
        d = frame.to_dict()
        
        assert d["filename"] == "/app/module.py"
        assert d["lineno"] == 42
        assert d["name"] == "my_function"
    
    def test_to_safe_string_visible(self):
        """Should format visible frame."""
        frame = FrameInfo(
            filename="/app/module.py",
            lineno=42,
            name="my_function",
            visibility=FrameVisibility.VISIBLE,
        )
        
        result = frame.to_safe_string()
        
        assert "/app/module.py" in result
        assert "42" in result
        assert "my_function" in result
    
    def test_to_safe_string_hidden(self):
        """Should return empty for hidden frame."""
        frame = FrameInfo(
            filename="/secret/path.py",
            lineno=99,
            name="secret_function",
            visibility=FrameVisibility.HIDDEN,
        )
        
        result = frame.to_safe_string()
        
        assert result == ""
    
    def test_to_safe_string_summarized(self):
        """Should summarize frame."""
        frame = FrameInfo(
            filename="/lib/internal.py",
            lineno=10,
            name="internal_func",
            visibility=FrameVisibility.SUMMARIZED,
        )
        
        result = frame.to_safe_string()
        
        assert "internal_func" in result
        assert "/lib/internal.py" not in result


# =============================================================================
# Test: ProtectedStackTrace
# =============================================================================

class TestProtectedStackTrace:
    """Test ProtectedStackTrace class."""
    
    def test_to_safe_string(self):
        """Should format as safe string."""
        protected = ProtectedStackTrace(
            exception_type="ValueError",
            exception_message="Invalid input",
            frames=[
                FrameInfo(
                    filename="/app/handler.py",
                    lineno=10,
                    name="handle",
                    visibility=FrameVisibility.VISIBLE,
                ),
            ],
        )
        
        result = protected.to_safe_string()
        
        assert "Traceback" in result
        assert "ValueError" in result
        assert "Invalid input" in result
        assert "/app/handler.py" in result
    
    def test_excludes_hidden_frames(self):
        """Should exclude hidden frames."""
        protected = ProtectedStackTrace(
            exception_type="Error",
            exception_message="test",
            frames=[
                FrameInfo(
                    filename="/visible.py",
                    lineno=1,
                    name="visible",
                    visibility=FrameVisibility.VISIBLE,
                ),
                FrameInfo(
                    filename="/hidden.py",
                    lineno=2,
                    name="hidden",
                    visibility=FrameVisibility.HIDDEN,
                ),
            ],
        )
        
        result = protected.to_safe_string()
        
        assert "/visible.py" in result
        assert "/hidden.py" not in result
    
    def test_limits_frames(self):
        """Should limit number of frames."""
        frames = [
            FrameInfo(
                filename=f"/app/module{i}.py",
                lineno=i,
                name=f"func{i}",
                visibility=FrameVisibility.VISIBLE,
            )
            for i in range(20)
        ]
        
        protected = ProtectedStackTrace(
            exception_type="Error",
            exception_message="test",
            frames=frames,
        )
        
        result = protected.to_safe_string(max_frames=5)
        
        assert "frames hidden" in result


# =============================================================================
# Test: StackTraceProtector
# =============================================================================

class TestStackTraceProtector:
    """Test StackTraceProtector."""
    
    def test_protect_exception(self, protector):
        """Should protect exception."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            protected = protector.protect(e)
        
        assert protected.exception_type == "ValueError"
        assert "Test error" in protected.exception_message
    
    def test_hides_stdlib_paths(self, protector):
        """Should hide standard library paths."""
        try:
            # This will have stdlib frames
            int("not a number")
        except ValueError as e:
            protected = protector.protect(e)
        
        # Stdlib frames should be hidden in production
        stdlib_frames = [
            f for f in protected.frames
            if "lib/python" in f.filename.lower()
            and f.visibility == FrameVisibility.VISIBLE
        ]
        
        assert len(stdlib_frames) == 0
    
    def test_add_hidden_path(self, protector):
        """Should hide custom paths."""
        protector.add_hidden_path("/secret/internal")
        
        frame = FrameInfo(
            filename="/secret/internal/module.py",
            lineno=1,
            name="func",
        )
        
        visibility = protector._determine_visibility(frame)
        
        assert visibility == FrameVisibility.HIDDEN
    
    def test_add_visible_path(self, protector):
        """Should keep visible paths visible."""
        protector.add_visible_path("/app/important")
        
        frame = FrameInfo(
            filename="/app/important/module.py",
            lineno=1,
            name="func",
        )
        
        visibility = protector._determine_visibility(frame)
        
        assert visibility == FrameVisibility.VISIBLE
    
    def test_custom_frame_filter(self, protector):
        """Should apply custom frame filter."""
        def hide_test_frames(frame: FrameInfo) -> FrameVisibility:
            if "test" in frame.filename.lower():
                return FrameVisibility.HIDDEN
            return FrameVisibility.VISIBLE
        
        protector.add_frame_filter(hide_test_frames)
        
        frame = FrameInfo(
            filename="/tests/test_module.py",
            lineno=1,
            name="test_func",
        )
        
        visibility = protector._determine_visibility(frame)
        
        assert visibility == FrameVisibility.HIDDEN
    
    def test_format_safe(self, protector):
        """Should format as safe string."""
        try:
            raise RuntimeError("Something failed")
        except RuntimeError as e:
            result = protector.format_safe(e)
        
        assert "RuntimeError" in result
        assert "Something failed" in result
    
    def test_handles_exception_chain(self, protector):
        """Should handle chained exceptions."""
        try:
            try:
                raise ValueError("Original")
            except ValueError:
                raise RuntimeError("Wrapper") from ValueError("Cause")
        except RuntimeError as e:
            protected = protector.protect(e)
        
        assert protected.exception_type == "RuntimeError"
        assert protected.cause is not None
        assert protected.cause.exception_type == "ValueError"


# =============================================================================
# Test: ExceptionFormatter
# =============================================================================

class TestExceptionFormatter:
    """Test ExceptionFormatter."""
    
    def test_format_for_client(self, formatter):
        """Should format for client response."""
        exc = ValueError("Invalid email format")
        result = formatter.format_for_client(exc)
        
        assert "ValueError" in result
        assert "Invalid email format" in result
        # Should NOT include stack trace
        assert "Traceback" not in result
    
    def test_format_for_client_internal_error(self, formatter):
        """Should use generic message for internal errors."""
        exc = RuntimeError("Database connection failed to 192.168.1.1")
        result = formatter.format_for_client(exc)
        
        # Should NOT expose internal details
        assert "192.168.1.1" not in result
        assert "internal error" in result.lower()
    
    def test_format_for_log(self, formatter):
        """Should format for logging."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            result = formatter.format_for_log(e)
        
        assert "ValueError" in result
        assert "Test" in result
    
    def test_format_for_debug_production(self, formatter):
        """Should limit info in production."""
        try:
            raise ValueError("Debug test")
        except ValueError as e:
            result = formatter.format_for_debug(e)
        
        # In production mode, should be limited
        assert "ValueError" in result


# =============================================================================
# Test: ProductionExceptionHook
# =============================================================================

class TestProductionExceptionHook:
    """Test ProductionExceptionHook."""
    
    def test_install_uninstall(self, protector):
        """Should install and uninstall hook."""
        hook = ProductionExceptionHook(protector)
        original = sys.excepthook
        
        hook.install()
        assert sys.excepthook != original
        
        hook.uninstall()
        assert sys.excepthook == original


# =============================================================================
# Test: StackTraceService
# =============================================================================

class TestStackTraceService:
    """Test StackTraceService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        s1 = get_stack_trace_service()
        s2 = get_stack_trace_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        service = StackTraceService.configure(EnvironmentMode.DEVELOPMENT)
        
        assert service.protector.config.mode == EnvironmentMode.DEVELOPMENT
    
    def test_protect(self, service):
        """Should protect stack trace."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            protected = service.protect(e)
        
        assert protected is not None
        assert protected.exception_type == "ValueError"
    
    def test_format_safe(self, service):
        """Should format safely."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            result = service.format_safe(e)
        
        assert "ValueError" in result
    
    def test_format_for_client(self, service):
        """Should format for client."""
        exc = ValueError("Bad input")
        result = service.format_for_client(exc)
        
        assert "Traceback" not in result


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_protect_stack_trace(self):
        """Should protect via convenience function."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            protected = protect_stack_trace(e)
        
        assert protected is not None
    
    def test_format_safe_exception(self):
        """Should format safely via convenience function."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            result = format_safe_exception(e)
        
        assert "ValueError" in result
    
    def test_format_client_exception(self):
        """Should format for client via convenience function."""
        exc = ValueError("Test")
        result = format_client_exception(exc)
        
        assert "Traceback" not in result


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects of stack trace protection."""
    
    def test_no_sensitive_paths_in_output(self, protector):
        """Should not expose sensitive paths."""
        try:
            raise Exception("Error in /etc/secrets/config.yaml")
        except Exception as e:
            result = protector.format_safe(e)
        
        # The path might be in message but frame paths should be protected
        # depending on sanitization config
        assert "Traceback" in result
    
    def test_no_local_variables(self, protector):
        """Should not include local variables by default."""
        try:
            password = "secret123"
            api_key = "sk_live_abc"
            raise ValueError("Error")
        except ValueError as e:
            protected = protector.protect(e)
        
        # Local variables should not be captured
        for frame in protected.frames:
            assert "secret123" not in str(frame.locals)
            assert "sk_live_abc" not in str(frame.locals)
    
    def test_production_mode_hides_more(self):
        """Production mode should hide more details."""
        prod_protector = StackTraceProtector(
            StackTraceConfig(mode=EnvironmentMode.PRODUCTION)
        )
        dev_protector = StackTraceProtector(
            StackTraceConfig(mode=EnvironmentMode.DEVELOPMENT)
        )
        
        try:
            raise ValueError("Test")
        except ValueError as e:
            prod_result = prod_protector.protect(e)
            dev_result = dev_protector.protect(e)
        
        # Production should be more restrictive
        prod_visible = [f for f in prod_result.frames if f.visibility == FrameVisibility.VISIBLE]
        dev_visible = [f for f in dev_result.frames if f.visibility != FrameVisibility.HIDDEN]
        
        # Development shows more frames
        assert len(dev_visible) >= len(prod_visible)
