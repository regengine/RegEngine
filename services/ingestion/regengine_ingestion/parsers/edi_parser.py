"""Schema-aware EDI parser."""

import re
from typing import Optional, Dict, Any, List
from .base import DocumentParser


class EDIParser(DocumentParser):
    """
    Schema-aware parser for EDI (X12/EDIFACT) documents.
    
    Performs validation against expected segment structures for common business documents.
    """
    
    # Simple schema definitions for validation
    SCHEMAS = {
        "X12_856": {
            "name": "Ship Notice/Manifest (ASN)",
            "required_segments": ["ISA", "GS", "ST", "BSN", "HL", "SE", "GE", "IEA"]
        },
        "X12_850": {
            "name": "Purchase Order",
            "required_segments": ["ISA", "GS", "ST", "BEG", "PO1", "SE", "GE", "IEA"]
        },
        "EDIFACT_ORDERS": {
            "name": "Purchase Order Message",
            "required_segments": ["UNB", "UNH", "BGM", "LIN", "UNT", "UNZ"]
        }
    }
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is EDI."""
        try:
            sample = content[:500].decode("utf-8", errors="ignore")
            return (
                sample.startswith("ISA") or 
                sample.startswith("UNA") or 
                sample.startswith("UNB") or
                "ISA*" in sample or
                "UNB+" in sample
            )
        except Exception:
            return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract text and validate EDI structure.
        """
        try:
            edi_text = content.decode("utf-8", errors="ignore")
            is_x12 = edi_text.startswith("ISA") or "ISA*" in edi_text[:100]
            
            if is_x12:
                return self._parse_and_validate_x12(edi_text)
            else:
                return self._parse_and_validate_edifact(edi_text)
                
        except Exception as e:
            return content.decode("utf-8", errors="ignore")
            
    def _parse_and_validate_x12(self, content: str) -> str:
        # Detect delimiters
        element_sep = content[3] if len(content) > 3 else "*"
        segment_term = content[105] if len(content) > 105 else "~"
        
        segments = content.replace("\n", "").replace("\r", "").split(segment_term)
        found_segments = [s.split(element_sep)[0].strip() for s in segments if s.strip()]
        
        # Identify document type (ST segment element 1)
        doc_type_code = ""
        for seg in segments:
            if seg.startswith("ST"):
                parts = seg.split(element_sep)
                if len(parts) > 1:
                    doc_type_code = parts[1]
                    break
        
        schema_key = f"X12_{doc_type_code}"
        schema = self.SCHEMAS.get(schema_key)
        
        validation_report = "--- EDI VALIDATION REPORT ---\n"
        if schema:
            validation_report += f"Document Type Identified: {schema['name']} ({doc_type_code})\n"
            missing = [s for s in schema["required_segments"] if s not in found_segments]
            if not missing:
                validation_report += "Status: VALID (All required segments present)\n"
            else:
                validation_report += f"Status: INVALID (Missing segments: {', '.join(missing)})\n"
        else:
            validation_report += f"Document Type: Unknown X12 ({doc_type_code})\n"
            validation_report += "Status: UNVERIFIED (No schema available)\n"
        
        validation_report += "-----------------------------\n\n"
        
        # Use existing parsing logic for text
        from app.format_extractors import _parse_x12
        text, _, _ = _parse_x12(content, content.encode("utf-8"))
        
        return validation_report + text

    def _parse_and_validate_edifact(self, content: str) -> str:
        # Basic EDIFACT validation
        element_sep = "+"
        segment_term = "'"
        
        if content.startswith("UNA"):
            element_sep = content[4]
            segment_term = content[8]
            
        segments = content.replace("\n", "").replace("\r", "").split(segment_term)
        found_segments = [s.split(element_sep)[0].strip() for s in segments if s.strip()]
        
        validation_report = "--- EDI VALIDATION REPORT ---\n"
        validation_report += "Format: EDIFACT\n"
        # Logic for EDIFACT doc type identification would go here
        validation_report += "Status: UNVERIFIED (EDIFACT schema validation pending)\n"
        validation_report += "-----------------------------\n\n"
        
        from app.format_extractors import _parse_edifact
        text, _, _ = _parse_edifact(content, content.encode("utf-8"))
        
        return validation_report + text

    def get_parser_name(self) -> str:
        return "edi_parser"
