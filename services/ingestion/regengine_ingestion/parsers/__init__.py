"""Document parser module."""

from .base import DocumentParser, ParserRegistry
from .html_parser import HTMLParser
from .xml_parser import XMLParser
from .pdf_parser import PDFParser
from .text_parser import TextParser
from .sec_parser import SECParser
from .fda_parser import FDAParser
from .edi_parser import EDIParser


def create_default_registry() -> ParserRegistry:
    """
    Create parser registry with all default parsers.
    
    Returns:
        Configured ParserRegistry
    """
    registry = ParserRegistry()
    
    # Register parsers in priority order
    registry.register(SECParser())
    registry.register(FDAParser())
    registry.register(EDIParser())
    registry.register(PDFParser())
    registry.register(HTMLParser())
    registry.register(XMLParser())
    registry.register(TextParser())  # Fallback
    
    return registry


__all__ = [
    "DocumentParser",
    "ParserRegistry",
    "HTMLParser",
    "XMLParser",
    "PDFParser",
    "TextParser",
    "SECParser",
    "FDAParser",
    "EDIParser",
    "create_default_registry",
]
