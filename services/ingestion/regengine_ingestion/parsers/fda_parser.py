"""FDA document parser."""

from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from .base import DocumentParser


class FDAParser(DocumentParser):
    """
    Parser for FDA regulatory documents (Warning Letters, 483s).
    
    Extracts clean text and identifies specific violation themes.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is an FDA regulatory document."""
        try:
            preview = content[:2000].decode("utf-8", errors="ignore").lower()
            # Look for FDA-specific markers
            if "warning letter" in preview and "fda" in preview:
                return True
            if "form fda 483" in preview or "inspectional observations" in preview:
                return True
            return False
        except Exception:
            return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from FDA document.
        """
        try:
            # FDA letters are often HTML/Text
            html = content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "lxml")
            
            # Remove scripts and styles
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Identify FDA Doc Type
            doc_type = "FDA General"
            if "warning letter" in html.lower():
                doc_type = "FDA Warning Letter"
            elif "form fda 483" in html.lower():
                doc_type = "FDA Form 483"
                
            text = soup.get_text(separator="\n", strip=True)
            
            # Prepend FDA info
            header = f"--- FDA REGULATORY DATA ---\nType: {doc_type}\n---------------------------\n\n"
            
            return header + text
            
        except Exception as e:
            return content.decode("utf-8", errors="ignore")
    
    def get_parser_name(self) -> str:
        return "fda_parser"
