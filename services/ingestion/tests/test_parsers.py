"""Unit tests for the Advanced Ingestion Framework parsers."""

import pytest
from regengine_ingestion.parsers import create_default_registry, HTMLParser, XMLParser, TextParser, PDFParser

@pytest.fixture
def parser_registry():
    return create_default_registry()

class TestParserRegistry:
    def test_registry_initialization(self, parser_registry):
        assert parser_registry is not None
        # Check if basic parsers are registered
        assert any(isinstance(p, PDFParser) for p in parser_registry.parsers)
        assert any(isinstance(p, HTMLParser) for p in parser_registry.parsers)
        assert any(isinstance(p, XMLParser) for p in parser_registry.parsers)
        assert any(isinstance(p, TextParser) for p in parser_registry.parsers)

    def test_routing_html(self, parser_registry):
        html_content = b"<html><body><h1>Test</h1></body></html>"
        text, name = parser_registry.parse(html_content, "text/html")
        assert "Test" in text
        assert name == "html_parser"

    def test_routing_xml(self, parser_registry):
        xml_content = b"<?xml version='1.0'?><root><item>Value</item></root>"
        text, name = parser_registry.parse(xml_content, "application/xml")
        assert "Value" in text
        assert name == "xml_parser"

    def test_routing_text(self, parser_registry):
        text_content = b"Plain text content"
        text, name = parser_registry.parse(text_content, "text/plain")
        assert "Plain text" in text
        assert name == "text_parser"

class TestHTMLParser:
    def test_html_extraction(self):
        parser = HTMLParser()
        html = b"<html><head><title>Title</title></head><body><p>Paragraph</p></body></html>"
        text = parser.parse(html)
        assert "Title" in text
        assert "Paragraph" in text

class TestXMLParser:
    def test_xml_extraction(self):
        parser = XMLParser()
        xml = b"<root><title>XML Title</title><content>Some content</content></root>"
        text = parser.parse(xml)
        assert "XML Title" in text
        assert "Some content" in text

class TestTextParser:
    def test_text_extraction(self):
        parser = TextParser()
        content = b"Simple text"
        text = parser.parse(content)
        assert text == "Simple text"

class TestSECParser:
    def test_sec_extraction(self):
        from regengine_ingestion.parsers import SECParser
        parser = SECParser()
        html = b"<html><body><h1>SEC FILING</h1><p>FORM 10-K</p><p>Item 1A. Risk Factors</p></body></html>"
        text = parser.parse(html)
        assert "Form 10-K" in text
        assert "RISK FACTORS FOUND" in text

class TestFDAParser:
    def test_fda_extraction(self):
        from regengine_ingestion.parsers import FDAParser
        parser = FDAParser()
        html = b"<html><body><h1>FDA Warning Letter</h1><p>Violations found.</p></body></html>"
        text = parser.parse(html)
        assert "FDA Warning Letter" in text
        assert "Violations found" in text

class TestEDIParser:
    def test_x12_856_validation(self):
        from regengine_ingestion.parsers import EDIParser
        parser = EDIParser()
        # Mock X12 856 with all required segments
        x12 = b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *210101*1200*U*00401*000000001*0*P*>~GS*SH*SENDER*RECEIVER*20210101*1200*1*X*004010~ST*856*0001~BSN*00*SHIP001*20210101*1200~HL*1**S~SE*3*0001~GE*1*1~IEA*1*000000001~"
        text = parser.parse(x12)
        assert "VALID (All required segments present)" in text
        assert "Ship Notice/Manifest (ASN)" in text

    def test_x12_invalid_validation(self):
        from regengine_ingestion.parsers import EDIParser
        parser = EDIParser()
        # Missing HL segment for 856
        x12 = b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *210101*1200*U*00401*000000001*0*P*>~GS*SH*SENDER*RECEIVER*20210101*1200*1*X*004010~ST*856*0001~BSN*00*SHIP001*20210101*1200~SE*3*0001~GE*1*1~IEA*1*000000001~"
        text = parser.parse(x12)
        assert "INVALID (Missing segments: HL)" in text
