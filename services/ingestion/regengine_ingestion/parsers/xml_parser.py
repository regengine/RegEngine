"""XML document parser."""

from typing import Optional, Dict, Any

from lxml import etree

from .base import DocumentParser


class XMLParser(DocumentParser):
    """
    Parser for XML documents.
    
    Extracts text content from XML elements.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is XML."""
        if "xml" in content_type.lower():
            return True
        
        # Check for XML declaration
        try:
            preview = content[:200].decode("utf-8", errors="ignore")
            return preview.strip().startswith("<?xml")
        except Exception:
            return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from XML.
        
        Args:
            content: XML document bytes
            metadata: Optional metadata
            
        Returns:
            Extracted text from all text nodes
        """
        try:
            # Parse XML
            root = etree.fromstring(content)
            
            # Extract all text content
            text_parts = []
            
            for element in root.iter():
                if element.text and element.text.strip():
                    text_parts.append(element.text.strip())
                if element.tail and element.tail.strip():
                    text_parts.append(element.tail.strip())
            
            return "\n".join(text_parts)
            
        except Exception as e:
            # Fallback to plain text
            return content.decode("utf-8", errors="ignore")
    
    def get_parser_name(self) -> str:
        return "xml_parser"
