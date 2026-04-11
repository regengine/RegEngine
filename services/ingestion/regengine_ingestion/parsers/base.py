"""Base parser interface for document text extraction."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger("parsers-base")


class DocumentParser(ABC):
    """
    Base class for document parsers.
    
    Parsers extract structured text from various document formats.
    """
    
    @abstractmethod
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """
        Check if this parser can handle the given content.
        
        Args:
            content_type: MIME type
            content: Raw document bytes
            
        Returns:
            True if parser can handle this content
        """
        pass
    
    @abstractmethod
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text from document.
        
        Args:
            content: Raw document bytes
            metadata: Optional metadata about the document
            
        Returns:
            Extracted text content
        """
        pass
    
    @abstractmethod
    def get_parser_name(self) -> str:
        """Get the parser name for audit logging."""
        pass


class ParserRegistry:
    """
    Registry for managing document parsers.
    
    Automatically selects the appropriate parser based on content type.
    """
    
    def __init__(self):
        self.parsers = []
    
    def register(self, parser: DocumentParser) -> None:
        """Register a parser."""
        self.parsers.append(parser)
    
    def get_parser(self, content_type: str, content: bytes) -> Optional[DocumentParser]:
        """
        Get appropriate parser for content.
        
        Args:
            content_type: MIME type
            content: Raw document bytes
            
        Returns:
            Parser instance or None
        """
        for parser in self.parsers:
            if parser.can_parse(content_type, content):
                return parser
        return None
    
    def parse(self, content: bytes, content_type: str, metadata: Optional[Dict] = None) -> tuple[str, str]:
        """
        Parse content using appropriate parser.
        
        Args:
            content: Raw document bytes
            content_type: MIME type
            metadata: Optional metadata
            
        Returns:
            Tuple of (extracted_text, parser_name)
        """
        parser = self.get_parser(content_type, content)
        
        if parser:
            try:
                text = parser.parse(content, metadata)
                return text, parser.get_parser_name()
            except Exception as e:
                # Provide graceful degradation instead of a 500 error
                return f"Error extracting content via {parser.get_parser_name()}: {str(e)}", f"{parser.get_parser_name()}_failed"
        
        # Fallback to UTF-8 decode
        try:
            text = content.decode("utf-8", errors="ignore")
            return text, "utf8_fallback"
        except Exception:
            logger.warning("Content parse failed completely", exc_info=True)
            return "", "parse_failed"
