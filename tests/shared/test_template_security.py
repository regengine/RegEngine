"""
Tests for SEC-049: Template Injection Prevention.

Tests cover:
- SSTI detection
- Attribute access prevention
- Context validation
- Safe rendering
- Template sanitization
"""

import pytest

from shared.template_security import (
    # Enums
    TemplateThreatType,
    TemplateValidationResult,
    # Data classes
    TemplateSecurityConfig,
    TemplateValidationReport,
    # Classes
    TemplateThreatDetector,
    TemplateSanitizer,
    TemplateContextValidator,
    SafeTemplateRenderer,
    TemplateSecurityService,
    # Convenience functions
    get_template_service,
    is_template_safe,
    sanitize_template,
    render_template_safe,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create template security config."""
    return TemplateSecurityConfig()


@pytest.fixture
def detector(config):
    """Create threat detector."""
    return TemplateThreatDetector(config)


@pytest.fixture
def sanitizer(config):
    """Create sanitizer."""
    return TemplateSanitizer(config)


@pytest.fixture
def context_validator(config):
    """Create context validator."""
    return TemplateContextValidator(config)


@pytest.fixture
def renderer(config):
    """Create renderer."""
    return SafeTemplateRenderer(config)


@pytest.fixture
def service(config):
    """Create service."""
    TemplateSecurityService._instance = None
    return TemplateSecurityService(config)


@pytest.fixture
def safe_template():
    """Safe template."""
    return "Hello, {{ name }}! Welcome to {{ site }}."


@pytest.fixture
def ssti_template():
    """SSTI attack template."""
    return "{{ ''.__class__.__mro__[1].__subclasses__() }}"


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert TemplateThreatType.SSTI == "ssti"
        assert TemplateThreatType.CODE_EXECUTION == "code_execution"
        assert TemplateThreatType.ATTRIBUTE_ACCESS == "attribute_access"
    
    def test_validation_results(self):
        """Should have expected validation results."""
        assert TemplateValidationResult.SAFE == "safe"
        assert TemplateValidationResult.BLOCKED == "blocked"


# =============================================================================
# Test: TemplateSecurityConfig
# =============================================================================

class TestTemplateSecurityConfig:
    """Test TemplateSecurityConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = TemplateSecurityConfig()
        
        assert config.allow_attribute_access is False
        assert config.sandbox_enabled is True
        assert "__class__" in config.blocked_attributes


# =============================================================================
# Test: TemplateThreatDetector
# =============================================================================

class TestTemplateThreatDetector:
    """Test TemplateThreatDetector."""
    
    def test_detects_safe_template(self, detector, safe_template):
        """Should pass safe template."""
        result = detector.detect_threats(safe_template)
        
        assert result.is_safe is True
        assert len(result.threats_detected) == 0
    
    def test_detects_ssti(self, detector, ssti_template):
        """Should detect SSTI."""
        result = detector.detect_threats(ssti_template)
        
        assert result.is_safe is False
        assert TemplateThreatType.SSTI in result.threats_detected
    
    def test_detects_class_access(self, detector):
        """Should detect __class__ access."""
        template = "{{ obj.__class__ }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_mro_access(self, detector):
        """Should detect __mro__ access."""
        template = "{{ obj.__mro__ }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_subclasses(self, detector):
        """Should detect __subclasses__ access."""
        template = "{{ obj.__subclasses__() }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_globals(self, detector):
        """Should detect __globals__ access."""
        template = "{{ obj.__globals__ }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_builtins(self, detector):
        """Should detect __builtins__ access."""
        template = "{{ obj.__builtins__ }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_eval(self, detector):
        """Should detect eval()."""
        template = "{{ eval('code') }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_exec(self, detector):
        """Should detect exec()."""
        template = "{{ exec('code') }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_import(self, detector):
        """Should detect __import__."""
        template = "{{ __import__('os') }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_open(self, detector):
        """Should detect open()."""
        template = "{{ open('/etc/passwd').read() }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_private_attrs(self, detector):
        """Should detect private attribute access."""
        template = "{{ obj._private }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_detects_getattr(self, detector):
        """Should detect getattr()."""
        template = "{{ getattr(obj, 'attr') }}"
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False
    
    def test_rejects_oversized_template(self, detector):
        """Should reject oversized template."""
        template = "x" * 200000
        
        result = detector.detect_threats(template)
        
        assert result.is_safe is False


# =============================================================================
# Test: TemplateSanitizer
# =============================================================================

class TestTemplateSanitizer:
    """Test TemplateSanitizer."""
    
    def test_removes_dunder_access(self, sanitizer):
        """Should remove dunder access."""
        template = "{{ obj.__class__.__mro__ }}"
        
        result = sanitizer.sanitize(template)
        
        assert "__class__" not in result
        assert "__mro__" not in result
    
    def test_removes_private_access(self, sanitizer):
        """Should remove private attribute access."""
        template = "{{ obj._private }}"
        
        result = sanitizer.sanitize(template)
        
        assert "._private" not in result
    
    def test_blocks_dangerous_functions(self, sanitizer):
        """Should block dangerous functions."""
        template = "{{ eval('code') }}"
        
        result = sanitizer.sanitize(template)
        
        assert "blocked_eval" in result
    
    def test_escapes_html(self, sanitizer):
        """Should escape HTML."""
        value = "<script>alert('xss')</script>"
        
        result = sanitizer.escape_html(value)
        
        assert "<" not in result
        assert ">" not in result
        assert "&lt;" in result
    
    def test_preserves_safe_content(self, sanitizer, safe_template):
        """Should preserve safe content."""
        result = sanitizer.sanitize(safe_template)
        
        assert "{{ name }}" in result
        assert "{{ site }}" in result


# =============================================================================
# Test: TemplateContextValidator
# =============================================================================

class TestTemplateContextValidator:
    """Test TemplateContextValidator."""
    
    def test_validates_safe_context(self, context_validator):
        """Should validate safe context."""
        context = {"name": "John", "age": 30}
        
        is_valid, errors = context_validator.validate_context(context)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_rejects_invalid_variable_name(self, context_validator):
        """Should reject invalid variable name."""
        # Names starting with numbers are invalid
        context = {"123invalid": "bad", "valid": "good"}
        
        is_valid, errors = context_validator.validate_context(context)
        
        assert is_valid is False
    
    def test_rejects_callable_value(self, context_validator):
        """Should reject callable value."""
        context = {"func": lambda: None}
        
        is_valid, errors = context_validator.validate_context(context)
        
        assert is_valid is False
    
    def test_sanitizes_context(self, context_validator):
        """Should sanitize context."""
        context = {
            "name": "John",
            "123invalid": "bad",  # Invalid: starts with number
            "func": lambda: None,
        }
        
        result = context_validator.sanitize_context(context)
        
        assert "name" in result
        assert "123invalid" not in result
        assert "func" not in result
    
    def test_handles_nested_context(self, context_validator):
        """Should handle nested context."""
        context = {
            "user": {"name": "John", "email": "john@example.com"},
            "items": ["a", "b", "c"],
        }
        
        is_valid, errors = context_validator.validate_context(context)
        
        assert is_valid is True


# =============================================================================
# Test: SafeTemplateRenderer
# =============================================================================

class TestSafeTemplateRenderer:
    """Test SafeTemplateRenderer."""
    
    def test_renders_safe_template(self, renderer, safe_template):
        """Should render safe template."""
        context = {"name": "John", "site": "Example"}
        
        success, result = renderer.render_simple(safe_template, context)
        
        assert success is True
        assert "John" in result
        assert "Example" in result
    
    def test_blocks_unsafe_template(self, renderer, ssti_template):
        """Should block unsafe template."""
        context = {}
        
        success, result = renderer.render_simple(ssti_template, context)
        
        assert success is False
        assert "blocked" in result.lower()
    
    def test_escapes_html_in_values(self, renderer):
        """Should escape HTML in values."""
        template = "Hello, {{ name }}!"
        context = {"name": "<script>evil</script>"}
        
        success, result = renderer.render_simple(template, context)
        
        assert success is True
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
    
    def test_validates_and_sanitizes(self, renderer, ssti_template):
        """Should validate and sanitize."""
        is_safe, result = renderer.validate_and_sanitize(ssti_template)
        
        # The sanitized version should not contain dangerous patterns
        assert "__class__" not in result or is_safe is False
    
    def test_renders_brace_style(self, renderer):
        """Should render {var} style."""
        template = "Hello, {name}!"
        context = {"name": "World"}
        
        success, result = renderer.render_simple(template, context)
        
        assert success is True
        assert "Hello, World!" == result


# =============================================================================
# Test: TemplateSecurityService
# =============================================================================

class TestTemplateSecurityService:
    """Test TemplateSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        TemplateSecurityService._instance = None
        
        s1 = get_template_service()
        s2 = get_template_service()
        
        assert s1 is s2
    
    def test_is_safe(self, service, safe_template, ssti_template):
        """Should check safety."""
        assert service.is_safe(safe_template) is True
        assert service.is_safe(ssti_template) is False
    
    def test_validate(self, service, ssti_template):
        """Should validate."""
        result = service.validate(ssti_template)
        
        assert result.is_safe is False
        assert len(result.threats_detected) > 0
    
    def test_sanitize(self, service):
        """Should sanitize."""
        template = "{{ obj.__class__ }}"
        
        result = service.sanitize(template)
        
        assert "__class__" not in result
    
    def test_validate_context(self, service):
        """Should validate context."""
        valid_ctx = {"name": "John"}
        invalid_ctx = {"func": lambda: None}
        
        is_valid1, _ = service.validate_context(valid_ctx)
        is_valid2, _ = service.validate_context(invalid_ctx)
        
        assert is_valid1 is True
        assert is_valid2 is False
    
    def test_render(self, service, safe_template):
        """Should render safely."""
        context = {"name": "John", "site": "Example"}
        
        success, result = service.render(safe_template, context)
        
        assert success is True
        assert "John" in result


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_is_template_safe(self, safe_template, ssti_template):
        """Should check safety."""
        TemplateSecurityService._instance = None
        
        assert is_template_safe(safe_template) is True
        assert is_template_safe(ssti_template) is False
    
    def test_sanitize_template(self):
        """Should sanitize."""
        TemplateSecurityService._instance = None
        
        result = sanitize_template("{{ obj.__class__ }}")
        
        assert "__class__" not in result
    
    def test_render_template_safe(self, safe_template):
        """Should render safely."""
        TemplateSecurityService._instance = None
        
        success, result = render_template_safe(
            safe_template,
            {"name": "World", "site": "Test"},
        )
        
        assert success is True


# =============================================================================
# Test: SSTI Attack Vectors
# =============================================================================

class TestSSTIVectors:
    """Test various SSTI attack vectors."""
    
    def test_jinja2_ssti(self, detector):
        """Should detect Jinja2 SSTI."""
        template = "{{''.__class__.__mro__[2].__subclasses__()[40]('/etc/passwd').read()}}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_lipsum_trick(self, detector):
        """Should detect lipsum trick."""
        template = "{{ lipsum.__globals__['os'].popen('id').read() }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_cycler_trick(self, detector):
        """Should detect cycler trick."""
        template = "{{ cycler.__init__.__globals__.os.popen('id').read() }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_config_access(self, detector):
        """Should detect config access."""
        template = "{{ config['SECRET_KEY'] }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_request_access(self, detector):
        """Should detect request access."""
        template = "{{ request.environ }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_attr_filter(self, detector):
        """Should detect attr filter abuse."""
        template = "{{ ''|attr('__class__') }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_dict_access_bypass(self, detector):
        """Should detect dict access bypass."""
        template = "{{ obj['__class__'] }}"
        
        assert not detector.detect_threats(template).is_safe
    
    def test_for_loop_ssti(self, detector):
        """Should detect for loop SSTI."""
        template = "{% for x in ''.__class__.__mro__ %}{{ x }}{% endfor %}"
        
        assert not detector.detect_threats(template).is_safe
