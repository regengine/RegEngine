"""Plain text parser."""

from typing import Optional, Dict, Any

from .base import DocumentParser


class TextParser(DocumentParser):
    """
    Parser for plain text documents.
    
    Handles UTF-8 text with fallback encoding detection.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is plain text."""
        # Always can attempt to parse as text (fallback parser)
        return "text/plain" in content_type.lower()
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text with encoding detection.
        
        Args:
            content: Text document bytes
            metadata: Optional metadata
            
        Returns:
            Decoded text
        """
        # Try UTF-8 first
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass
        
        # Try Latin-1 (never fails)
        try:
            return content.decode("latin-1")
        except Exception:
            pass
        
        # Last resort: ignore errors
        return content.decode("utf-8", errors="ignore")
    
    def get_parser_name(self) -> str:
        return "text_parser"
