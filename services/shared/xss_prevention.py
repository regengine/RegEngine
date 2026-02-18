"""
SEC-012: XSS (Cross-Site Scripting) Prevention for RegEngine.

This module provides comprehensive XSS protection:
- HTML entity encoding
- JavaScript escaping
- URL encoding
- CSS escaping
- Context-aware output encoding
- Content Security Policy helpers

Usage:
    from shared.xss_prevention import XSSPrevention, escape_html, escape_js
    
    # Simple escaping
    safe_html = escape_html(user_input)
    safe_js = escape_js(user_input)
    
    # Context-aware escaping
    xss = XSSPrevention()
    safe = xss.escape_for_context(user_input, OutputContext.HTML_BODY)
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger("xss_prevention")


# =============================================================================
# Output Contexts
# =============================================================================

class OutputContext(str, Enum):
    """Context where output will be rendered."""
    
    # HTML contexts
    HTML_BODY = "html_body"  # Inside HTML body
    HTML_ATTRIBUTE = "html_attribute"  # Inside HTML attribute
    HTML_ATTRIBUTE_UNQUOTED = "html_attribute_unquoted"  # Unquoted attribute
    HTML_COMMENT = "html_comment"  # Inside HTML comment
    
    # JavaScript contexts
    JS_STRING = "js_string"  # Inside JS string literal
    JS_BLOCK = "js_block"  # Inside JS code block
    JS_HTML_ATTRIBUTE = "js_html_attribute"  # onclick, onload, etc.
    
    # URL contexts
    URL = "url"  # Full URL
    URL_PARAM = "url_param"  # URL parameter value
    URL_PATH = "url_path"  # URL path segment
    
    # CSS contexts
    CSS_STRING = "css_string"  # Inside CSS string
    CSS_STYLE = "css_style"  # Inside style attribute
    
    # Data contexts
    JSON = "json"  # JSON output


# =============================================================================
# XSS Patterns for Detection
# =============================================================================

class XSSPatterns:
    """Patterns for detecting potential XSS."""
    
    # Common XSS attack patterns
    SCRIPT_TAGS: list[re.Pattern] = [
        re.compile(r'<\s*script', re.IGNORECASE),
        re.compile(r'<\s*/\s*script', re.IGNORECASE),
    ]
    
    EVENT_HANDLERS: list[re.Pattern] = [
        re.compile(r'\bon\w+\s*=', re.IGNORECASE),  # onclick=, onload=, etc.
    ]
    
    JAVASCRIPT_URLS: list[re.Pattern] = [
        re.compile(r'javascript\s*:', re.IGNORECASE),
        re.compile(r'vbscript\s*:', re.IGNORECASE),
        re.compile(r'data\s*:\s*text/html', re.IGNORECASE),
    ]
    
    DANGEROUS_TAGS: list[re.Pattern] = [
        re.compile(r'<\s*iframe', re.IGNORECASE),
        re.compile(r'<\s*object', re.IGNORECASE),
        re.compile(r'<\s*embed', re.IGNORECASE),
        re.compile(r'<\s*applet', re.IGNORECASE),
        re.compile(r'<\s*form', re.IGNORECASE),
        re.compile(r'<\s*meta', re.IGNORECASE),
        re.compile(r'<\s*link', re.IGNORECASE),
        re.compile(r'<\s*style', re.IGNORECASE),
        re.compile(r'<\s*base', re.IGNORECASE),
        re.compile(r'<\s*svg', re.IGNORECASE),
        re.compile(r'<\s*math', re.IGNORECASE),
    ]
    
    EXPRESSION_PATTERNS: list[re.Pattern] = [
        re.compile(r'expression\s*\(', re.IGNORECASE),  # CSS expression
        re.compile(r'url\s*\(', re.IGNORECASE),  # CSS url()
        re.compile(r'eval\s*\(', re.IGNORECASE),
        re.compile(r'Function\s*\(', re.IGNORECASE),
        re.compile(r'setTimeout\s*\(', re.IGNORECASE),
        re.compile(r'setInterval\s*\(', re.IGNORECASE),
    ]
    
    # Obfuscation patterns
    OBFUSCATION: list[re.Pattern] = [
        re.compile(r'&#', re.IGNORECASE),  # HTML entities
        re.compile(r'\\x[0-9a-f]{2}', re.IGNORECASE),  # Hex encoding
        re.compile(r'\\u[0-9a-f]{4}', re.IGNORECASE),  # Unicode encoding
        re.compile(r'%[0-9a-f]{2}', re.IGNORECASE),  # URL encoding
    ]


# =============================================================================
# Encoding Functions
# =============================================================================

def escape_html(value: str) -> str:
    """Escape HTML special characters.
    
    Converts: & < > " ' to HTML entities
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Use html.escape with quote=True to escape both " and '
    escaped = html.escape(value, quote=True)
    # html.escape doesn't escape single quotes by default, add it
    escaped = escaped.replace("'", "&#x27;")
    return escaped


def escape_html_attribute(value: str) -> str:
    """Escape for HTML attribute context.
    
    More aggressive escaping for attribute values.
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Escape all non-alphanumeric characters
    result = []
    for char in value:
        if char.isalnum():
            result.append(char)
        else:
            result.append(f"&#x{ord(char):02X};")
    return ''.join(result)


def escape_js(value: str) -> str:
    """Escape for JavaScript string context.
    
    Makes value safe for inclusion in JS string literals.
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Escape characters that could break out of JS string
    replacements = {
        '\\': '\\\\',
        "'": "\\'",
        '"': '\\"',
        '\n': '\\n',
        '\r': '\\r',
        '\t': '\\t',
        '<': '\\x3C',  # Prevent </script> injection
        '>': '\\x3E',
        '/': '\\/',  # Prevent </script> injection
        '\u2028': '\\u2028',  # Line separator
        '\u2029': '\\u2029',  # Paragraph separator
    }
    
    result = value
    for char, escape in replacements.items():
        result = result.replace(char, escape)
    return result


def escape_js_html_attr(value: str) -> str:
    """Escape for JavaScript in HTML attribute (onclick, etc.).
    
    Double escaping: JS first, then HTML.
    """
    # First escape for JS
    js_escaped = escape_js(value)
    # Then escape for HTML attribute
    return escape_html_attribute(js_escaped)


def escape_url(value: str) -> str:
    """Escape for URL context.
    
    URL encodes the value for safe inclusion in URLs.
    """
    if not isinstance(value, str):
        value = str(value)
    return urllib.parse.quote(value, safe='')


def escape_url_param(value: str) -> str:
    """Escape for URL parameter value context."""
    if not isinstance(value, str):
        value = str(value)
    return urllib.parse.quote_plus(value)


def escape_css(value: str) -> str:
    """Escape for CSS string context."""
    if not isinstance(value, str):
        value = str(value)
    
    result = []
    for char in value:
        if char.isalnum():
            result.append(char)
        else:
            # CSS escape: \HH where HH is hex code
            result.append(f"\\{ord(char):06X}")
    return ''.join(result)


def escape_json(value: Any) -> str:
    """Escape for JSON context.
    
    Returns JSON-safe string with additional XSS protections.
    """
    # Use json.dumps which handles escaping
    json_str = json.dumps(value)
    # Additional escaping for HTML context
    return json_str.replace('<', '\\u003C').replace('>', '\\u003E').replace('&', '\\u0026')


# =============================================================================
# XSS Detection
# =============================================================================

@dataclass
class XSSDetectionResult:
    """Result of XSS detection."""
    
    is_suspicious: bool
    detected_patterns: list[str]
    risk_level: str  # "low", "medium", "high"
    
    def __bool__(self) -> bool:
        return self.is_suspicious


class XSSDetector:
    """Detect potential XSS attacks in input."""
    
    def __init__(self, strict: bool = True):
        """Initialize detector.
        
        Args:
            strict: If True, also check for obfuscation
        """
        self._strict = strict
    
    def detect(self, value: str) -> XSSDetectionResult:
        """Detect XSS patterns in value.
        
        Args:
            value: Input to check
            
        Returns:
            Detection result
        """
        if not isinstance(value, str):
            value = str(value)
        
        detected: list[str] = []
        risk_level = "low"
        
        # Check script tags (highest risk)
        for pattern in XSSPatterns.SCRIPT_TAGS:
            if pattern.search(value):
                detected.append("script_tag")
                risk_level = "high"
        
        # Check event handlers (high risk)
        for pattern in XSSPatterns.EVENT_HANDLERS:
            if pattern.search(value):
                detected.append("event_handler")
                risk_level = "high"
        
        # Check javascript URLs (high risk)
        for pattern in XSSPatterns.JAVASCRIPT_URLS:
            if pattern.search(value):
                detected.append("javascript_url")
                risk_level = "high"
        
        # Check dangerous tags (medium risk)
        for pattern in XSSPatterns.DANGEROUS_TAGS:
            if pattern.search(value):
                detected.append("dangerous_tag")
                if risk_level == "low":
                    risk_level = "medium"
        
        # Check expression patterns (medium risk)
        for pattern in XSSPatterns.EXPRESSION_PATTERNS:
            if pattern.search(value):
                detected.append("expression_pattern")
                if risk_level == "low":
                    risk_level = "medium"
        
        # Check obfuscation in strict mode
        if self._strict:
            for pattern in XSSPatterns.OBFUSCATION:
                if pattern.search(value):
                    detected.append("obfuscation")
                    if risk_level == "low":
                        risk_level = "medium"
                    break
        
        if detected:
            logger.warning(
                "xss_detected",
                patterns=detected,
                risk=risk_level,
            )
        
        return XSSDetectionResult(
            is_suspicious=len(detected) > 0,
            detected_patterns=detected,
            risk_level=risk_level,
        )


# =============================================================================
# HTML Sanitizer
# =============================================================================

class HTMLSanitizer:
    """Sanitize HTML content by removing dangerous elements.
    
    This is for cases where HTML input is expected but needs to be safe.
    """
    
    # Tags that are allowed by default
    DEFAULT_ALLOWED_TAGS = {
        'a', 'abbr', 'acronym', 'address', 'b', 'big', 'blockquote', 'br',
        'center', 'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'dfn',
        'dir', 'div', 'dl', 'dt', 'em', 'font', 'h1', 'h2', 'h3', 'h4',
        'h5', 'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'ol', 'p', 'pre',
        'q', 's', 'samp', 'small', 'span', 'strike', 'strong', 'sub', 'sup',
        'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u',
        'ul', 'var',
    }
    
    # Attributes allowed per tag
    DEFAULT_ALLOWED_ATTRS = {
        '*': {'class', 'id', 'title'},
        'a': {'href', 'target', 'rel'},
        'img': {'src', 'alt', 'width', 'height'},
        'font': {'color', 'face', 'size'},
        'table': {'border', 'cellpadding', 'cellspacing', 'width'},
        'td': {'colspan', 'rowspan', 'width'},
        'th': {'colspan', 'rowspan', 'width'},
        'col': {'span', 'width'},
    }
    
    # URL schemes allowed in href/src
    ALLOWED_URL_SCHEMES = {'http', 'https', 'mailto', 'tel'}
    
    def __init__(
        self,
        allowed_tags: Optional[set[str]] = None,
        allowed_attrs: Optional[dict[str, set[str]]] = None,
    ):
        """Initialize sanitizer.
        
        Args:
            allowed_tags: Set of allowed tag names
            allowed_attrs: Dict mapping tag names to allowed attributes
        """
        self._allowed_tags = allowed_tags or self.DEFAULT_ALLOWED_TAGS
        self._allowed_attrs = allowed_attrs or self.DEFAULT_ALLOWED_ATTRS
    
    def sanitize(self, html_content: str) -> str:
        """Sanitize HTML content.
        
        Args:
            html_content: HTML to sanitize
            
        Returns:
            Sanitized HTML
        """
        if not html_content:
            return ""
        
        # Remove script tags and content
        html_content = re.sub(
            r'<script[^>]*>.*?</script>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        
        # Remove style tags and content
        html_content = re.sub(
            r'<style[^>]*>.*?</style>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        
        # Remove event handlers
        html_content = re.sub(
            r'\s+on\w+\s*=\s*["\'][^"\']*["\']',
            '',
            html_content,
            flags=re.IGNORECASE,
        )
        
        # Remove javascript: URLs
        html_content = re.sub(
            r'(href|src)\s*=\s*["\']?\s*javascript:[^"\'>\s]*["\']?',
            r'\1=""',
            html_content,
            flags=re.IGNORECASE,
        )
        
        # Remove disallowed tags (keep content)
        def remove_tag(match):
            tag = match.group(1).lower()
            if tag in self._allowed_tags:
                return match.group(0)
            return ''
        
        html_content = re.sub(
            r'<(/?)(\w+)([^>]*)>',
            lambda m: f'<{m.group(1)}{m.group(2)}{m.group(3)}>' if m.group(2).lower() in self._allowed_tags else '',
            html_content,
            flags=re.IGNORECASE,
        )
        
        logger.debug("html_sanitized", length=len(html_content))
        return html_content
    
    def strip_all_tags(self, html_content: str) -> str:
        """Remove all HTML tags, keeping only text content."""
        if not html_content:
            return ""
        
        # Remove tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = html.unescape(text)
        return text


# =============================================================================
# Main XSS Prevention Class
# =============================================================================

class XSSPrevention:
    """Main XSS prevention utility class."""
    
    def __init__(
        self,
        auto_detect: bool = True,
        strict_detection: bool = True,
    ):
        """Initialize XSS prevention.
        
        Args:
            auto_detect: If True, log warnings for detected XSS
            strict_detection: Strict mode for detection
        """
        self._auto_detect = auto_detect
        self._detector = XSSDetector(strict=strict_detection)
        self._sanitizer = HTMLSanitizer()
    
    def escape_for_context(
        self,
        value: str,
        context: OutputContext,
    ) -> str:
        """Escape value for specific output context.
        
        Args:
            value: Value to escape
            context: Output context
            
        Returns:
            Safely escaped value
        """
        if not isinstance(value, str):
            value = str(value)
        
        # Detect XSS if enabled
        if self._auto_detect:
            detection = self._detector.detect(value)
            if detection.is_suspicious:
                logger.warning(
                    "xss_in_value_escaped",
                    context=context.value,
                    patterns=detection.detected_patterns,
                )
        
        # Escape based on context
        if context == OutputContext.HTML_BODY:
            return escape_html(value)
        
        elif context == OutputContext.HTML_ATTRIBUTE:
            return escape_html_attribute(value)
        
        elif context == OutputContext.HTML_ATTRIBUTE_UNQUOTED:
            return escape_html_attribute(value)
        
        elif context == OutputContext.HTML_COMMENT:
            # Remove -- to prevent comment injection
            return value.replace('--', '').replace('>', '').replace('<', '')
        
        elif context == OutputContext.JS_STRING:
            return escape_js(value)
        
        elif context == OutputContext.JS_BLOCK:
            # For JS block, we need JSON encoding
            return escape_json(value)
        
        elif context == OutputContext.JS_HTML_ATTRIBUTE:
            return escape_js_html_attr(value)
        
        elif context == OutputContext.URL:
            return escape_url(value)
        
        elif context == OutputContext.URL_PARAM:
            return escape_url_param(value)
        
        elif context == OutputContext.URL_PATH:
            return escape_url(value)
        
        elif context == OutputContext.CSS_STRING:
            return escape_css(value)
        
        elif context == OutputContext.CSS_STYLE:
            return escape_css(value)
        
        elif context == OutputContext.JSON:
            return escape_json(value)
        
        else:
            # Default to most restrictive
            return escape_html_attribute(value)
    
    def detect_xss(self, value: str) -> XSSDetectionResult:
        """Detect potential XSS in value."""
        return self._detector.detect(value)
    
    def sanitize_html(self, html_content: str) -> str:
        """Sanitize HTML content."""
        return self._sanitizer.sanitize(html_content)
    
    def strip_tags(self, html_content: str) -> str:
        """Remove all HTML tags."""
        return self._sanitizer.strip_all_tags(html_content)
    
    def is_safe_url(self, url: str) -> bool:
        """Check if URL is safe (no javascript:, etc.)."""
        if not url:
            return True
        
        url_lower = url.lower().strip()
        
        # Check for dangerous schemes
        dangerous_schemes = ['javascript:', 'vbscript:', 'data:']
        for scheme in dangerous_schemes:
            if url_lower.startswith(scheme):
                return False
        
        return True
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a URL, removing dangerous parts."""
        if not url:
            return ""
        
        if not self.is_safe_url(url):
            logger.warning("dangerous_url_blocked", url=url[:50])
            return ""
        
        return url


# =============================================================================
# Template Helpers
# =============================================================================

class TemplateHelpers:
    """Helper functions for templates."""
    
    @staticmethod
    def safe_html(value: str) -> str:
        """Make value safe for HTML body."""
        return escape_html(value)
    
    @staticmethod
    def safe_attr(value: str) -> str:
        """Make value safe for HTML attribute."""
        return escape_html_attribute(value)
    
    @staticmethod
    def safe_js(value: str) -> str:
        """Make value safe for JavaScript string."""
        return escape_js(value)
    
    @staticmethod
    def safe_url(value: str) -> str:
        """Make value safe for URL."""
        return escape_url(value)
    
    @staticmethod
    def safe_json(value: Any) -> str:
        """Make value safe for JSON in HTML."""
        return escape_json(value)


# =============================================================================
# CSP Helper
# =============================================================================

class CSPBuilder:
    """Helper for building Content Security Policy headers."""
    
    def __init__(self):
        self._directives: dict[str, list[str]] = {}
    
    def add_directive(self, directive: str, *sources: str) -> "CSPBuilder":
        """Add CSP directive."""
        if directive not in self._directives:
            self._directives[directive] = []
        self._directives[directive].extend(sources)
        return self
    
    def default_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("default-src", *sources)
    
    def script_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("script-src", *sources)
    
    def style_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("style-src", *sources)
    
    def img_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("img-src", *sources)
    
    def font_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("font-src", *sources)
    
    def connect_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("connect-src", *sources)
    
    def frame_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("frame-src", *sources)
    
    def object_src(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("object-src", *sources)
    
    def base_uri(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("base-uri", *sources)
    
    def form_action(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("form-action", *sources)
    
    def frame_ancestors(self, *sources: str) -> "CSPBuilder":
        return self.add_directive("frame-ancestors", *sources)
    
    def build(self) -> str:
        """Build CSP header value."""
        parts = []
        for directive, sources in self._directives.items():
            if sources:
                parts.append(f"{directive} {' '.join(sources)}")
            else:
                parts.append(directive)
        return "; ".join(parts)
    
    @classmethod
    def strict_policy(cls) -> "CSPBuilder":
        """Create a strict CSP policy."""
        return (
            cls()
            .default_src("'self'")
            .script_src("'self'")
            .style_src("'self'")
            .img_src("'self'", "data:")
            .font_src("'self'")
            .connect_src("'self'")
            .frame_src("'none'")
            .object_src("'none'")
            .base_uri("'self'")
            .form_action("'self'")
            .frame_ancestors("'none'")
        )
