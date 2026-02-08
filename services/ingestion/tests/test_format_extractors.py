"""
Unit tests for format extractors.

Tests cover: HTML, XML, CSV, Excel, DOCX, EDI (X12/EDIFACT)
"""

import sys
from pathlib import Path

# Ensure ingestion service's 'app' package is resolved first
_ingestion_dir = Path(__file__).resolve().parent.parent
# Clear any cached 'app' modules from other services
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.')]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(_ingestion_dir))

import pytest
from app.format_extractors import (
    extract_from_html,
    extract_from_xml,
    extract_from_csv,
    extract_from_edi,
    detect_format,
    is_edi_content,
)


class TestHTMLExtraction:
    """Test HTML text extraction."""

    def test_basic_html(self):
        html = b"""
        <html>
        <head><title>Test Document</title></head>
        <body>
            <h1>Main Heading</h1>
            <p>This is a paragraph of text.</p>
            <ul>
                <li>Item one</li>
                <li>Item two</li>
            </ul>
        </body>
        </html>
        """
        text, meta, pos_map = extract_from_html(html)
        
        assert "Test Document" in text
        assert "Main Heading" in text
        assert "paragraph of text" in text
        assert meta.engine == "beautifulsoup"
        assert meta.confidence_mean > 0.9

    def test_html_removes_scripts(self):
        html = b"""
        <html>
        <body>
            <script>alert('evil');</script>
            <p>Real content</p>
            <style>.hidden { display: none; }</style>
        </body>
        </html>
        """
        text, meta, _ = extract_from_html(html)
        
        assert "Real content" in text
        assert "alert" not in text
        assert ".hidden" not in text


class TestXMLExtraction:
    """Test XML text extraction."""

    def test_basic_xml(self):
        xml = b"""<?xml version="1.0"?>
        <regulation>
            <title>FDA Regulation 21 CFR</title>
            <section id="1">
                <heading>General Provisions</heading>
                <content>This section contains general provisions.</content>
            </section>
        </regulation>
        """
        text, meta, pos_map = extract_from_xml(xml)
        
        assert "FDA Regulation" in text
        assert "General Provisions" in text
        assert meta.engine == "lxml"
        assert meta.confidence_mean > 0.95

    def test_xml_with_namespaces(self):
        xml = b"""<?xml version="1.0"?>
        <reg:document xmlns:reg="http://example.com/regulation">
            <reg:title>Namespaced Document</reg:title>
            <reg:body>Body content here</reg:body>
        </reg:document>
        """
        text, meta, _ = extract_from_xml(xml)
        
        assert "Namespaced Document" in text
        assert "Body content" in text


class TestCSVExtraction:
    """Test CSV text extraction."""

    def test_basic_csv(self):
        csv = b"""product_id,name,category,status
001,Romaine Lettuce,Produce,Active
002,Ground Beef,Meat,Active
003,Shell Eggs,Dairy,Active
"""
        text, meta, pos_map = extract_from_csv(csv)
        
        assert "Columns:" in text
        assert "product_id" in text
        assert "Romaine Lettuce" in text
        assert meta.engine == "pandas"
        assert meta.confidence_mean > 0.95

    def test_tsv_detection(self):
        tsv = b"col1\tcol2\tcol3\nval1\tval2\tval3"
        text, meta, _ = extract_from_csv(tsv)
        
        assert "col1" in text
        assert "val1" in text


class TestEDIExtraction:
    """Test EDI (X12/EDIFACT) extraction."""

    def test_x12_edi(self):
        # Simple X12 ASN/856 segment
        x12 = b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *210101*1200*U*00401*000000001*0*P*>~GS*SH*SENDER*RECEIVER*20210101*1200*1*X*004010~ST*856*0001~BSN*00*SHIP001*20210101*1200~SE*3*0001~GE*1*1~IEA*1*000000001~"
        text, meta, pos_map = extract_from_edi(x12)
        
        assert "X12 EDI Document" in text
        assert "[ISA] Interchange Control Header" in text
        assert "[BSN] Beginning Segment for Ship Notice" in text
        assert meta.engine == "x12-parser"

    def test_edifact_edi(self):
        edifact = b"UNB+UNOC:3+SENDER+RECEIVER+210101:1200+REF001++ORDERS'UNH+1+ORDERS:D:96A:UN'BGM+220+PO123+9'UNT+3+1'UNZ+1+REF001'"
        text, meta, pos_map = extract_from_edi(edifact)
        
        assert "EDIFACT Document" in text
        assert "[UNB] Interchange Header" in text
        assert "[BGM] Beginning of Message" in text
        assert meta.engine == "edifact-parser"


class TestFormatDetection:
    """Test format detection from content type and bytes."""

    def test_content_type_detection(self):
        assert detect_format("text/html") == "html"
        assert detect_format("application/xml") == "xml"
        assert detect_format("text/csv") == "csv"
        assert detect_format("application/vnd.ms-excel") == "excel"
        assert detect_format("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == "excel"
        assert detect_format("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "docx"
        assert detect_format("application/pdf") == "pdf"
        assert detect_format("application/json") == "json"

    def test_magic_bytes_detection(self):
        # PDF magic bytes
        assert detect_format(None, b"%PDF-1.4...") == "pdf"
        
        # XML declaration
        assert detect_format(None, b"<?xml version=\"1.0\"?>") == "xml"
        
        # HTML doctype
        assert detect_format(None, b"<!DOCTYPE html><html>") == "html"

    def test_edi_content_detection(self):
        assert is_edi_content(b"ISA*00*test") is True
        assert is_edi_content(b"UNB+UNOC:3+test") is True
        assert is_edi_content(b"Just regular text") is False


class TestFallbackExtraction:
    """Test fallback behavior when parsers are unavailable."""

    def test_unknown_format_fallback(self):
        content = b"This is some unknown binary content"
        text, meta, _ = extract_from_html(content)  # Will fallback
        
        # Should still extract something
        assert len(text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
