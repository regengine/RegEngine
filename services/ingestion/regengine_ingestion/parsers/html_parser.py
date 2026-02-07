"""HTML document parser."""

from typing import Optional, Dict, Any

from bs4 import BeautifulSoup

from .base import DocumentParser


class HTMLParser(DocumentParser):
    """
    Parser for HTML documents.
    
    Extracts clean text from HTML, removing scripts, styles, and tags.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is HTML."""
        if "html" in content_type.lower():
            return True
        
        # Check for HTML tags in first 500 bytes
        try:
            preview = content[:500].decode("utf-8", errors="ignore").lower()
            return "<html" in preview or "<!doctype html" in preview
        except Exception:
            return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from HTML.
        
        Args:
            content: HTML document bytes
            metadata: Optional metadata
            
        Returns:
            Extracted text with minimal whitespace
        """
        try:
            # Decode content
            html = content.decode("utf-8", errors="ignore")
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            
            # Remove script and style elements
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Extract text
            text = soup.get_text(separator="\n", strip=True)
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines()]
            lines = [line for line in lines if line]  # Remove empty lines
            
            return "\n".join(lines)
            
        except Exception as e:
            # Fallback to plain text extraction
            return content.decode("utf-8", errors="ignore")
    
    def get_parser_name(self) -> str:
        return "html_parser"
