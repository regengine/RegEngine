"""
SEC-047: XML/XXE Prevention.

Secure XML parsing with XXE (XML External Entity) prevention,
DTD blocking, and entity expansion limits.
"""

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class XMLThreatType(str, Enum):
    """Types of XML threats."""
    XXE = "xxe"  # XML External Entity
    SSRF = "ssrf"  # Server-Side Request Forgery
    BILLION_LAUGHS = "billion_laughs"  # Entity expansion DoS
    DTD_RETRIEVAL = "dtd_retrieval"
    ENTITY_EXPANSION = "entity_expansion"
    MALFORMED = "malformed"


class XMLParseResult(str, Enum):
    """XML parse result types."""
    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass
class XMLSecurityConfig:
    """Configuration for XML security."""
    
    # Feature controls
    allow_dtd: bool = False
    allow_external_entities: bool = False
    allow_parameter_entities: bool = False
    resolve_entities: bool = False
    
    # Limits
    max_entity_expansions: int = 1000
    max_entity_depth: int = 10
    max_document_size: int = 10485760  # 10MB
    max_element_depth: int = 100
    max_attributes_per_element: int = 50
    max_attribute_length: int = 10000
    
    # Detection
    detect_xxe_patterns: bool = True
    detect_ssrf_patterns: bool = True
    detect_billion_laughs: bool = True


@dataclass
class XMLValidationResult:
    """Result of XML validation."""
    
    is_safe: bool
    threats_detected: list = field(default_factory=list)
    threat_details: dict = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class XMLParseResultData:
    """Result of XML parsing."""
    
    status: XMLParseResult
    root: Optional[ET.Element] = None
    threats: list = field(default_factory=list)
    error_message: Optional[str] = None


class XMLThreatDetector:
    """Detects threats in XML content."""
    
    # XXE patterns
    XXE_PATTERNS = [
        r"<!ENTITY\s+\w+\s+SYSTEM",          # System entity
        r"<!ENTITY\s+\w+\s+PUBLIC",          # Public entity
        r"<!ENTITY\s+%\s*\w+\s+SYSTEM",      # Parameter entity
        r"<!ENTITY\s+%\s*\w+\s+PUBLIC",      # Parameter entity
        r'<!ENTITY\s+\w+\s+"file://',        # File protocol
        r'<!ENTITY\s+\w+\s+"http://',        # HTTP protocol
        r'<!ENTITY\s+\w+\s+"https://',       # HTTPS protocol
        r'<!ENTITY\s+\w+\s+"ftp://',         # FTP protocol
        r'<!ENTITY\s+\w+\s+"gopher://',      # Gopher protocol
        r'<!ENTITY\s+\w+\s+"expect://',      # Expect protocol (PHP)
        r'<!ENTITY\s+\w+\s+"php://',         # PHP filter
    ]
    
    # SSRF patterns
    SSRF_PATTERNS = [
        r"file://",
        r"http://localhost",
        r"http://127\.",
        r"http://0\.",
        r"http://\[::1\]",
        r"http://169\.254\.",  # AWS metadata
        r"http://metadata\.",
        r"http://internal",
        r"dict://",
        r"gopher://",
    ]
    
    # Billion laughs pattern (entity recursion)
    BILLION_LAUGHS_PATTERNS = [
        r"<!ENTITY\s+lol\d*\s+",
        r"&lol\d*;",
    ]
    
    def __init__(self, config: Optional[XMLSecurityConfig] = None):
        self.config = config or XMLSecurityConfig()
        
        self._xxe_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.XXE_PATTERNS
        ]
        self._ssrf_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.SSRF_PATTERNS
        ]
        self._billion_laughs_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.BILLION_LAUGHS_PATTERNS
        ]
    
    def detect_threats(self, xml_content: str) -> XMLValidationResult:
        """Detect threats in XML content."""
        threats = []
        details = {}
        
        # Check size
        if len(xml_content) > self.config.max_document_size:
            return XMLValidationResult(
                is_safe=False,
                threats_detected=[XMLThreatType.MALFORMED],
                error_message="Document exceeds maximum size",
            )
        
        # Check for DTD
        if not self.config.allow_dtd:
            if "<!DOCTYPE" in xml_content.upper():
                threats.append(XMLThreatType.DTD_RETRIEVAL)
                details["dtd"] = "DOCTYPE declaration detected"
        
        # Check for XXE
        if self.config.detect_xxe_patterns:
            xxe_matches = self._detect_xxe(xml_content)
            if xxe_matches:
                threats.append(XMLThreatType.XXE)
                details["xxe"] = xxe_matches
        
        # Check for SSRF
        if self.config.detect_ssrf_patterns:
            ssrf_matches = self._detect_ssrf(xml_content)
            if ssrf_matches:
                threats.append(XMLThreatType.SSRF)
                details["ssrf"] = ssrf_matches
        
        # Check for billion laughs
        if self.config.detect_billion_laughs:
            if self._detect_billion_laughs(xml_content):
                threats.append(XMLThreatType.BILLION_LAUGHS)
                details["billion_laughs"] = "Entity expansion attack detected"
        
        # Check for entity expansion
        entity_count = xml_content.count("<!ENTITY")
        if entity_count > self.config.max_entity_expansions:
            threats.append(XMLThreatType.ENTITY_EXPANSION)
            details["entities"] = f"Too many entities: {entity_count}"
        
        return XMLValidationResult(
            is_safe=len(threats) == 0,
            threats_detected=threats,
            threat_details=details,
        )
    
    def _detect_xxe(self, content: str) -> list[str]:
        """Detect XXE patterns."""
        matches = []
        for pattern in self._xxe_patterns:
            found = pattern.findall(content)
            if found:
                matches.extend(found)
        return matches
    
    def _detect_ssrf(self, content: str) -> list[str]:
        """Detect SSRF patterns."""
        matches = []
        for pattern in self._ssrf_patterns:
            found = pattern.findall(content)
            if found:
                matches.extend(found)
        return matches
    
    def _detect_billion_laughs(self, content: str) -> bool:
        """Detect billion laughs attack."""
        lol_count = 0
        for pattern in self._billion_laughs_patterns:
            matches = pattern.findall(content)
            lol_count += len(matches)
        return lol_count > 10  # Threshold for detection


class XMLSanitizer:
    """Sanitizes XML content."""
    
    def __init__(self, config: Optional[XMLSecurityConfig] = None):
        self.config = config or XMLSecurityConfig()
    
    def sanitize(self, xml_content: str) -> str:
        """Sanitize XML content by removing dangerous elements."""
        # Remove DOCTYPE declarations
        sanitized = re.sub(
            r"<!DOCTYPE[^>]*>",
            "",
            xml_content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        
        # Remove ENTITY declarations
        sanitized = re.sub(
            r"<!ENTITY[^>]*>",
            "",
            sanitized,
            flags=re.IGNORECASE | re.DOTALL,
        )
        
        # Remove CDATA if needed (optional)
        # sanitized = re.sub(r"<!\[CDATA\[.*?\]\]>", "", sanitized, flags=re.DOTALL)
        
        # Remove processing instructions except XML declaration
        sanitized = re.sub(
            r"<\?(?!xml)[^?]*\?>",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        
        return sanitized
    
    def strip_namespaces(self, xml_content: str) -> str:
        """Strip namespace declarations."""
        # Remove xmlns declarations
        stripped = re.sub(r'\s+xmlns:[a-z]+="[^"]*"', "", xml_content)
        stripped = re.sub(r'\s+xmlns="[^"]*"', "", stripped)
        
        # Remove namespace prefixes from tags
        stripped = re.sub(r"<([a-z]+):", r"<", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"</([a-z]+):", r"</", stripped, flags=re.IGNORECASE)
        
        return stripped


class SafeXMLParser:
    """Safe XML parser with XXE prevention."""
    
    def __init__(self, config: Optional[XMLSecurityConfig] = None):
        self.config = config or XMLSecurityConfig()
        self.detector = XMLThreatDetector(self.config)
        self.sanitizer = XMLSanitizer(self.config)
    
    def parse(
        self,
        xml_content: str,
        sanitize: bool = True,
    ) -> XMLParseResultData:
        """Parse XML safely."""
        # Detect threats first
        validation = self.detector.detect_threats(xml_content)
        
        if not validation.is_safe:
            return XMLParseResultData(
                status=XMLParseResult.BLOCKED,
                threats=validation.threats_detected,
                error_message=f"Threats detected: {validation.threats_detected}",
            )
        
        # Sanitize if requested
        if sanitize:
            xml_content = self.sanitizer.sanitize(xml_content)
        
        # Parse with safe parser
        try:
            root = ET.fromstring(xml_content)
            
            # Validate structure
            if not self._validate_structure(root):
                return XMLParseResultData(
                    status=XMLParseResult.ERROR,
                    error_message="XML structure validation failed",
                )
            
            return XMLParseResultData(
                status=XMLParseResult.SUCCESS,
                root=root,
            )
        except ET.ParseError as e:
            return XMLParseResultData(
                status=XMLParseResult.ERROR,
                error_message=f"Parse error: {e}",
            )
    
    def _validate_structure(
        self,
        element: ET.Element,
        depth: int = 0,
    ) -> bool:
        """Validate XML structure."""
        # Check depth
        if depth > self.config.max_element_depth:
            return False
        
        # Check attributes
        if len(element.attrib) > self.config.max_attributes_per_element:
            return False
        
        # Check attribute lengths
        for value in element.attrib.values():
            if len(str(value)) > self.config.max_attribute_length:
                return False
        
        # Recurse to children
        for child in element:
            if not self._validate_structure(child, depth + 1):
                return False
        
        return True
    
    def parse_file(self, filepath: str) -> XMLParseResultData:
        """Parse XML file safely."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return self.parse(content)
        except IOError as e:
            return XMLParseResultData(
                status=XMLParseResult.ERROR,
                error_message=f"File error: {e}",
            )


class XMLSecurityService:
    """Comprehensive XML security service."""
    
    _instance: Optional["XMLSecurityService"] = None
    
    def __init__(self, config: Optional[XMLSecurityConfig] = None):
        self.config = config or XMLSecurityConfig()
        self.parser = SafeXMLParser(self.config)
        self.detector = XMLThreatDetector(self.config)
        self.sanitizer = XMLSanitizer(self.config)
    
    @classmethod
    def get_instance(cls) -> "XMLSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: XMLSecurityConfig) -> "XMLSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def is_safe(self, xml_content: str) -> bool:
        """Check if XML is safe."""
        result = self.detector.detect_threats(xml_content)
        return result.is_safe
    
    def validate(self, xml_content: str) -> XMLValidationResult:
        """Validate XML for threats."""
        return self.detector.detect_threats(xml_content)
    
    def parse(
        self,
        xml_content: str,
        sanitize: bool = True,
    ) -> XMLParseResultData:
        """Parse XML safely."""
        return self.parser.parse(xml_content, sanitize)
    
    def sanitize(self, xml_content: str) -> str:
        """Sanitize XML content."""
        return self.sanitizer.sanitize(xml_content)
    
    def parse_or_none(
        self,
        xml_content: str,
    ) -> Optional[ET.Element]:
        """Parse XML and return root or None if unsafe."""
        result = self.parse(xml_content)
        return result.root if result.status == XMLParseResult.SUCCESS else None


# Convenience functions
def get_xml_service() -> XMLSecurityService:
    """Get XML service instance."""
    return XMLSecurityService.get_instance()


def is_xml_safe(xml_content: str) -> bool:
    """Check if XML is safe."""
    return get_xml_service().is_safe(xml_content)


def parse_xml_safe(xml_content: str) -> XMLParseResultData:
    """Parse XML safely."""
    return get_xml_service().parse(xml_content)


def sanitize_xml(xml_content: str) -> str:
    """Sanitize XML content."""
    return get_xml_service().sanitize(xml_content)
