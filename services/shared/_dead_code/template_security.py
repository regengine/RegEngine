"""
SEC-049: Template Injection Prevention.

Secure template rendering with injection prevention,
sandbox execution, and context validation.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class TemplateThreatType(str, Enum):
    """Types of template threats."""
    SSTI = "ssti"  # Server-Side Template Injection
    CODE_EXECUTION = "code_execution"
    ATTRIBUTE_ACCESS = "attribute_access"
    BUILTIN_ACCESS = "builtin_access"
    IMPORT_ATTEMPT = "import_attempt"
    FILE_ACCESS = "file_access"


class TemplateValidationResult(str, Enum):
    """Validation result types."""
    SAFE = "safe"
    BLOCKED = "blocked"
    SANITIZED = "sanitized"


@dataclass
class TemplateSecurityConfig:
    """Configuration for template security."""
    
    # Feature controls
    allow_attribute_access: bool = False
    allow_method_calls: bool = False
    allow_filters: bool = True
    sandbox_enabled: bool = True
    
    # Limits
    max_template_length: int = 100000
    max_variable_depth: int = 5
    max_iterations: int = 1000
    max_output_length: int = 1000000
    
    # Blocked patterns
    blocked_attributes: list = field(default_factory=lambda: [
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__code__",
        "__builtins__",
        "__import__",
        "__getattribute__",
        "__dict__",
        "__init__",
        "__new__",
        "__call__",
        "_module",
    ])
    
    # Allowed variable names pattern
    allowed_variable_pattern: str = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


@dataclass
class TemplateValidationReport:
    """Result of template validation."""
    
    status: TemplateValidationResult
    is_safe: bool
    original_template: str
    sanitized_template: Optional[str] = None
    threats_detected: list = field(default_factory=list)
    threat_details: dict = field(default_factory=dict)
    error_message: Optional[str] = None


class TemplateThreatDetector:
    """Detects threats in templates."""
    
    # SSTI patterns for various template engines
    SSTI_PATTERNS = [
        # Jinja2/Twig patterns
        r"\{\{\s*[^}]*\.__class__",
        r"\{\{\s*[^}]*\.__mro__",
        r"\{\{\s*[^}]*\.__subclasses__",
        r"\{\{\s*[^}]*\.__globals__",
        r"\{\{\s*[^}]*\.__builtins__",
        r"\{\{\s*[^}]*\.__import__",
        r"\{\{.*\|attr\s*\(",
        r"\{\%\s*for.*in.*\.__",
        
        # Python code execution
        r"exec\s*\(",
        r"eval\s*\(",
        r"compile\s*\(",
        r"__import__\s*\(",
        r"importlib",
        r"subprocess",
        r"os\.system",
        r"os\.popen",
        
        # File access
        r"open\s*\(",
        r"file\s*\(",
        r"read\s*\(",
        r"write\s*\(",
        
        # Config/request access
        r"config\s*\[",
        r"request\s*\.",
        r"self\s*\.",
        
        # Lipsum/cycler tricks
        r"lipsum\.__globals__",
        r"cycler\.__init__",
        r"joiner\.__init__",
        r"namespace\.__init__",
    ]
    
    # Dangerous attribute patterns
    ATTRIBUTE_PATTERNS = [
        r"\._[a-zA-Z_]",  # Private attributes
        r"\.__[a-zA-Z_]",  # Dunder attributes
        r"\[\s*['\"]__",  # Dict access to dunders
        r"getattr\s*\(",
        r"setattr\s*\(",
        r"delattr\s*\(",
    ]
    
    def __init__(self, config: Optional[TemplateSecurityConfig] = None):
        self.config = config or TemplateSecurityConfig()
        self._ssti_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.SSTI_PATTERNS
        ]
        self._attr_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.ATTRIBUTE_PATTERNS
        ]
    
    def detect_threats(self, template: str) -> TemplateValidationReport:
        """Detect threats in template."""
        threats = []
        details = {}
        
        # Check length
        if len(template) > self.config.max_template_length:
            return TemplateValidationReport(
                status=TemplateValidationResult.BLOCKED,
                is_safe=False,
                original_template=template,
                threats_detected=[TemplateThreatType.SSTI],
                error_message="Template exceeds maximum length",
            )
        
        # Check for SSTI patterns
        ssti_matches = self._detect_ssti(template)
        if ssti_matches:
            threats.append(TemplateThreatType.SSTI)
            details["ssti"] = ssti_matches
        
        # Check for dangerous attributes
        attr_matches = self._detect_attribute_access(template)
        if attr_matches:
            threats.append(TemplateThreatType.ATTRIBUTE_ACCESS)
            details["attributes"] = attr_matches
        
        # Check for blocked attributes
        for attr in self.config.blocked_attributes:
            if attr in template:
                if TemplateThreatType.BUILTIN_ACCESS not in threats:
                    threats.append(TemplateThreatType.BUILTIN_ACCESS)
                details.setdefault("blocked", []).append(attr)
        
        # Check for import attempts
        if self._detect_import(template):
            threats.append(TemplateThreatType.IMPORT_ATTEMPT)
            details["import"] = "Import attempt detected"
        
        # Check for file access
        if self._detect_file_access(template):
            threats.append(TemplateThreatType.FILE_ACCESS)
            details["file"] = "File access attempt detected"
        
        return TemplateValidationReport(
            status=TemplateValidationResult.BLOCKED if threats else TemplateValidationResult.SAFE,
            is_safe=len(threats) == 0,
            original_template=template,
            threats_detected=threats,
            threat_details=details,
        )
    
    def _detect_ssti(self, template: str) -> list[str]:
        """Detect SSTI patterns."""
        matches = []
        for pattern in self._ssti_patterns:
            found = pattern.findall(template)
            if found:
                matches.extend(found)
        return matches
    
    def _detect_attribute_access(self, template: str) -> list[str]:
        """Detect dangerous attribute access."""
        if self.config.allow_attribute_access:
            return []
        
        matches = []
        for pattern in self._attr_patterns:
            found = pattern.findall(template)
            if found:
                matches.extend(found)
        return matches
    
    def _detect_import(self, template: str) -> bool:
        """Detect import attempts."""
        import_patterns = [
            r"__import__",
            r"importlib",
            r"from\s+\w+\s+import",
            r"import\s+\w+",
        ]
        for pattern in import_patterns:
            if re.search(pattern, template, re.IGNORECASE):
                return True
        return False
    
    def _detect_file_access(self, template: str) -> bool:
        """Detect file access attempts."""
        file_patterns = [
            r"open\s*\(",
            r"file\s*\(",
            r"\.read\s*\(",
            r"\.write\s*\(",
            r"\.readlines\s*\(",
            r"pathlib",
            r"os\.path",
        ]
        for pattern in file_patterns:
            if re.search(pattern, template, re.IGNORECASE):
                return True
        return False


class TemplateSanitizer:
    """Sanitizes template content."""
    
    def __init__(self, config: Optional[TemplateSecurityConfig] = None):
        self.config = config or TemplateSecurityConfig()
    
    def sanitize(self, template: str) -> str:
        """Sanitize template by removing dangerous patterns."""
        sanitized = template
        
        # Remove dangerous attribute access
        for attr in self.config.blocked_attributes:
            sanitized = sanitized.replace(attr, "")
        
        # Remove private/dunder attribute access
        sanitized = re.sub(r"\.__[a-zA-Z_]+__", "", sanitized)
        sanitized = re.sub(r"\._[a-zA-Z_]+", "", sanitized)
        
        # Remove suspicious function calls
        dangerous_functions = [
            "exec", "eval", "compile", "open", "file",
            "getattr", "setattr", "delattr", "globals", "locals",
        ]
        for func in dangerous_functions:
            sanitized = re.sub(
                rf"\b{func}\s*\(",
                f"blocked_{func}(",
                sanitized,
                flags=re.IGNORECASE,
            )
        
        return sanitized
    
    def escape_html(self, value: str) -> str:
        """Escape HTML special characters."""
        escapes = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#x27;",
        }
        for char, escape in escapes.items():
            value = value.replace(char, escape)
        return value


class TemplateContextValidator:
    """Validates template context/variables."""
    
    def __init__(self, config: Optional[TemplateSecurityConfig] = None):
        self.config = config or TemplateSecurityConfig()
        self._var_pattern = re.compile(self.config.allowed_variable_pattern)
    
    def validate_context(self, context: dict) -> tuple[bool, list[str]]:
        """Validate template context."""
        errors = []
        
        for key in context.keys():
            if not self._var_pattern.match(str(key)):
                errors.append(f"Invalid variable name: {key}")
        
        # Check for dangerous values
        for key, value in context.items():
            if self._is_dangerous_value(value):
                errors.append(f"Dangerous value for {key}")
        
        return len(errors) == 0, errors
    
    def _is_dangerous_value(self, value: Any, depth: int = 0) -> bool:
        """Check if value is dangerous."""
        if depth > self.config.max_variable_depth:
            return True
        
        # Check for callable
        if callable(value) and not isinstance(value, type):
            return True
        
        # Check for modules
        if hasattr(value, "__module__"):
            module = getattr(value, "__module__", "")
            if module in ["os", "subprocess", "sys", "builtins"]:
                return True
        
        # Recurse for containers
        if isinstance(value, dict):
            for v in value.values():
                if self._is_dangerous_value(v, depth + 1):
                    return True
        elif isinstance(value, (list, tuple)):
            for v in value:
                if self._is_dangerous_value(v, depth + 1):
                    return True
        
        return False
    
    def sanitize_context(self, context: dict) -> dict:
        """Sanitize context by removing dangerous values."""
        sanitized = {}
        
        for key, value in context.items():
            if self._var_pattern.match(str(key)):
                if not self._is_dangerous_value(value):
                    sanitized[key] = self._sanitize_value(value)
        
        return sanitized
    
    def _sanitize_value(self, value: Any, depth: int = 0) -> Any:
        """Sanitize a single value."""
        if depth > self.config.max_variable_depth:
            return None
        
        if isinstance(value, str):
            return value
        elif isinstance(value, (int, float, bool, type(None))):
            return value
        elif isinstance(value, dict):
            return {
                k: self._sanitize_value(v, depth + 1)
                for k, v in value.items()
                if isinstance(k, str) and self._var_pattern.match(k)
            }
        elif isinstance(value, (list, tuple)):
            return [
                self._sanitize_value(v, depth + 1)
                for v in value
            ]
        else:
            # Convert to string for safety
            return str(value)


class SafeTemplateRenderer:
    """Safe template renderer with sandbox."""
    
    def __init__(self, config: Optional[TemplateSecurityConfig] = None):
        self.config = config or TemplateSecurityConfig()
        self.detector = TemplateThreatDetector(self.config)
        self.sanitizer = TemplateSanitizer(self.config)
        self.context_validator = TemplateContextValidator(self.config)
    
    def render_simple(
        self,
        template: str,
        context: dict,
    ) -> tuple[bool, str]:
        """Render a simple template with variable substitution.
        
        Returns (success, result/error).
        """
        # Validate template
        validation = self.detector.detect_threats(template)
        if not validation.is_safe:
            return False, f"Template blocked: {validation.threats_detected}"
        
        # Sanitize context
        safe_context = self.context_validator.sanitize_context(context)
        
        # Simple variable substitution
        result = template
        for key, value in safe_context.items():
            # Replace {{ var }} style
            result = re.sub(
                rf"\{{\{{\s*{key}\s*\}}\}}",
                self.sanitizer.escape_html(str(value)),
                result,
            )
            # Replace {var} style
            result = re.sub(
                rf"\{{{key}\}}",
                self.sanitizer.escape_html(str(value)),
                result,
            )
        
        # Check output length
        if len(result) > self.config.max_output_length:
            return False, "Output exceeds maximum length"
        
        return True, result
    
    def validate_and_sanitize(
        self,
        template: str,
    ) -> tuple[bool, str]:
        """Validate and optionally sanitize template.
        
        Returns (is_safe, sanitized_or_original).
        """
        validation = self.detector.detect_threats(template)
        
        if validation.is_safe:
            return True, template
        
        # Try to sanitize
        sanitized = self.sanitizer.sanitize(template)
        revalidation = self.detector.detect_threats(sanitized)
        
        if revalidation.is_safe:
            return True, sanitized
        
        return False, template


class TemplateSecurityService:
    """Comprehensive template security service."""
    
    _instance: Optional["TemplateSecurityService"] = None
    
    def __init__(self, config: Optional[TemplateSecurityConfig] = None):
        self.config = config or TemplateSecurityConfig()
        self.detector = TemplateThreatDetector(self.config)
        self.sanitizer = TemplateSanitizer(self.config)
        self.context_validator = TemplateContextValidator(self.config)
        self.renderer = SafeTemplateRenderer(self.config)
    
    @classmethod
    def get_instance(cls) -> "TemplateSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: TemplateSecurityConfig) -> "TemplateSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def is_safe(self, template: str) -> bool:
        """Check if template is safe."""
        result = self.detector.detect_threats(template)
        return result.is_safe
    
    def validate(self, template: str) -> TemplateValidationReport:
        """Validate template."""
        return self.detector.detect_threats(template)
    
    def sanitize(self, template: str) -> str:
        """Sanitize template."""
        return self.sanitizer.sanitize(template)
    
    def validate_context(self, context: dict) -> tuple[bool, list[str]]:
        """Validate context."""
        return self.context_validator.validate_context(context)
    
    def render(
        self,
        template: str,
        context: dict,
    ) -> tuple[bool, str]:
        """Render template safely."""
        return self.renderer.render_simple(template, context)


# Convenience functions
def get_template_service() -> TemplateSecurityService:
    """Get template service instance."""
    return TemplateSecurityService.get_instance()


def is_template_safe(template: str) -> bool:
    """Check if template is safe."""
    return get_template_service().is_safe(template)


def sanitize_template(template: str) -> str:
    """Sanitize template."""
    return get_template_service().sanitize(template)


def render_template_safe(template: str, context: dict) -> tuple[bool, str]:
    """Render template safely."""
    return get_template_service().render(template, context)
