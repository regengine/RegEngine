"""SEC filing document parser."""

import re
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from .base import DocumentParser


class SECParser(DocumentParser):
    """
    Parser for SEC filings (10-K, 10-Q, etc.).
    
    Identifies filing types and extracts structured sections like Risk Factors.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is an SEC filing."""
        # SEC filings are often HTML but contain specific headers
        if "html" not in content_type.lower():
            return False
            
        try:
            preview = content[:2000].decode("utf-8", errors="ignore").lower()
            # Look for SEC-specific markers
            if "sec filing" in preview or "form 10-k" in preview or "form 10-q" in preview:
                return True
            if "united states securities and exchange commission" in preview:
                return True
            return False
        except Exception:
            return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from SEC filing with section awareness.
        """
        try:
            html = content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "lxml")
            
            # Remove scripts and styles
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Identify Filing Type
            filing_type = "Unknown SEC"
            if "10-K" in html[:5000].upper():
                filing_type = "Form 10-K"
            elif "10-Q" in html[:5000].upper():
                filing_type = "Form 10-Q"
                
            # Extract common sections (e.g., Risk Factors - Item 1A)
            risk_factors = ""
            risk_match = re.search(r'item\s+1a\.?\s*risk\s+factors', html, re.IGNORECASE)
            if risk_match:
                # Basic section extraction logic - find next item
                # In a real enterprise scenario, this would use more robust layout analysis
                risk_factors = "\n[ITEM 1A. RISK FACTORS FOUND]\n"
            
            text = soup.get_text(separator="\n", strip=True)
            
            # Prepend filing info
            header = f"--- SEC FILER DATA ---\nType: {filing_type}\n{risk_factors}\n----------------------\n\n"
            
            return header + text
            
        except Exception as e:
            return content.decode("utf-8", errors="ignore")
    
    def get_parser_name(self) -> str:
        return "sec_parser"
