"""PDF document parser."""

from typing import Optional, Dict, Any

from pdfminer.high_level import extract_text as pdf_extract_text

from .base import DocumentParser


class PDFParser(DocumentParser):
    """
    Parser for PDF documents.
    
    Extracts text using pdfminer.six.
    """
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is PDF."""
        if "pdf" in content_type.lower():
            return True
        
        # Check for PDF magic bytes
        return content.startswith(b"%PDF")
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from PDF.
        
        Args:
            content: PDF document bytes
            metadata: Optional metadata
            
        Returns:
            Extracted text
        """
        try:
            # Create BytesIO object
            from io import BytesIO
            pdf_file = BytesIO(content)
            
            # Extract text
            text = pdf_extract_text(pdf_file)
            
            # Clean up
            lines = [line.strip() for line in text.splitlines()]
            lines = [line for line in lines if line]
            
            return "\n".join(lines)
            
        except Exception as e:
            # PDF parsing failed
            return f"[PDF parsing failed: {str(e)}]"
    
    def get_parser_name(self) -> str:
        return "pdf_parser"
