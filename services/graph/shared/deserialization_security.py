"""
SEC-050: Deserialization Security.

Secure deserialization with format validation,
type restrictions, and depth limits.
"""

import base64
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Type


class DeserializationThreatType(str, Enum):
    """Types of deserialization threats."""
    PICKLE_EXPLOIT = "pickle_exploit"
    YAML_EXPLOIT = "yaml_exploit"
    TYPE_CONFUSION = "type_confusion"
    DEPTH_LIMIT = "depth_limit"
    SIZE_LIMIT = "size_limit"
    MALFORMED_DATA = "malformed_data"
    UNSAFE_TYPE = "unsafe_type"


class DeserializationResult(str, Enum):
    """Deserialization result types."""
    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass
class DeserializationConfig:
    """Configuration for deserialization security."""
    
    # Format controls
    allow_pickle: bool = False
    allow_yaml: bool = False
    allow_json: bool = True
    
    # Limits
    max_depth: int = 20
    max_size: int = 10485760  # 10MB
    max_string_length: int = 1000000
    max_array_length: int = 10000
    max_object_keys: int = 1000
    
    # Type restrictions
    allowed_types: list = field(default_factory=lambda: [
        "str", "int", "float", "bool", "NoneType",
        "list", "dict", "tuple",
    ])
    
    # Blocked patterns
    blocked_patterns: list = field(default_factory=lambda: [
        r"__reduce__",
        r"__reduce_ex__",
        r"__getstate__",
        r"__setstate__",
        r"os\.system",
        r"subprocess",
        r"eval\s*\(",
        r"exec\s*\(",
    ])


@dataclass
class DeserializationReport:
    """Result of deserialization validation."""
    
    status: DeserializationResult
    is_safe: bool
    data: Any = None
    threats_detected: list = field(default_factory=list)
    error_message: Optional[str] = None


class PickleDetector:
    """Detects pickle-based attacks."""
    
    # Pickle opcodes that indicate code execution
    DANGEROUS_OPCODES = [
        b"\x80",  # PROTO
        b"c",     # GLOBAL
        b"i",     # INST
        b"o",     # OBJ
        b"R",     # REDUCE
        b"b",     # BUILD
    ]
    
    # Dangerous module references
    DANGEROUS_MODULES = [
        "os",
        "subprocess",
        "commands",
        "sys",
        "builtins",
        "__builtin__",
        "posix",
        "nt",
        "socket",
        "pickle",
        "marshal",
    ]
    
    def is_pickle_data(self, data: bytes) -> bool:
        """Check if data looks like pickle."""
        if not isinstance(data, bytes):
            return False
        
        # Check for pickle protocol markers (\x80 followed by version)
        if len(data) >= 2 and data[0:1] == b"\x80" and data[1] < 6:
            return True
        
        # Check for multiple dangerous opcodes together
        opcode_count = 0
        for opcode in self.DANGEROUS_OPCODES:
            if opcode in data:
                opcode_count += 1
        
        # Only flag as pickle if multiple opcodes found
        return opcode_count >= 2
    
    def detect_threats(self, data: bytes) -> list[DeserializationThreatType]:
        """Detect pickle-based threats."""
        threats = []
        
        if not isinstance(data, bytes):
            return threats
        
        # Check for pickle data
        if self.is_pickle_data(data):
            threats.append(DeserializationThreatType.PICKLE_EXPLOIT)
        
        # Check for dangerous module references
        data_str = data.decode("utf-8", errors="ignore")
        for module in self.DANGEROUS_MODULES:
            if module in data_str:
                if DeserializationThreatType.PICKLE_EXPLOIT not in threats:
                    threats.append(DeserializationThreatType.PICKLE_EXPLOIT)
                break
        
        return threats


class YAMLDetector:
    """Detects YAML-based attacks."""
    
    # Dangerous YAML tags
    DANGEROUS_TAGS = [
        "!!python/object",
        "!!python/object/apply",
        "!!python/object/new",
        "!!python/name",
        "!!python/module",
        "!!python/bool",
        "tag:yaml.org,2002:python",
    ]
    
    # Dangerous YAML constructs
    DANGEROUS_PATTERNS = [
        r"!\s*python/",
        r"!!python",
        r"__import__",
        r"subprocess",
        r"os\.system",
        r"eval\s*\(",
        r"exec\s*\(",
    ]
    
    def __init__(self):
        self._patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS
        ]
    
    def is_yaml_data(self, data: str) -> bool:
        """Check if data looks like YAML."""
        if not isinstance(data, str):
            return False
        
        # Simple YAML detection
        yaml_indicators = [
            data.startswith("---"),
            ": " in data,
            data.startswith("- "),
            "!!str" in data,
            "!!int" in data,
        ]
        return any(yaml_indicators)
    
    def detect_threats(self, data: str) -> list[DeserializationThreatType]:
        """Detect YAML-based threats."""
        threats = []
        
        if not isinstance(data, str):
            return threats
        
        # Check for dangerous tags
        for tag in self.DANGEROUS_TAGS:
            if tag in data:
                threats.append(DeserializationThreatType.YAML_EXPLOIT)
                break
        
        # Check for dangerous patterns
        for pattern in self._patterns:
            if pattern.search(data):
                if DeserializationThreatType.YAML_EXPLOIT not in threats:
                    threats.append(DeserializationThreatType.YAML_EXPLOIT)
                break
        
        return threats


class JSONValidator:
    """Validates JSON data for security issues."""
    
    def __init__(self, config: Optional[DeserializationConfig] = None):
        self.config = config or DeserializationConfig()
    
    def validate(self, data: str) -> DeserializationReport:
        """Validate JSON data."""
        # Check size
        if len(data) > self.config.max_size:
            return DeserializationReport(
                status=DeserializationResult.BLOCKED,
                is_safe=False,
                threats_detected=[DeserializationThreatType.SIZE_LIMIT],
                error_message="Data exceeds maximum size",
            )
        
        # Try to parse
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            return DeserializationReport(
                status=DeserializationResult.ERROR,
                is_safe=False,
                threats_detected=[DeserializationThreatType.MALFORMED_DATA],
                error_message=f"Invalid JSON: {e}",
            )
        
        # Validate structure
        threats = self._validate_structure(parsed)
        
        if threats:
            return DeserializationReport(
                status=DeserializationResult.BLOCKED,
                is_safe=False,
                threats_detected=threats,
                error_message="Structure validation failed",
            )
        
        return DeserializationReport(
            status=DeserializationResult.SUCCESS,
            is_safe=True,
            data=parsed,
        )
    
    def _validate_structure(
        self,
        data: Any,
        depth: int = 0,
    ) -> list[DeserializationThreatType]:
        """Validate data structure."""
        threats = []
        
        # Check depth
        if depth > self.config.max_depth:
            threats.append(DeserializationThreatType.DEPTH_LIMIT)
            return threats
        
        if isinstance(data, str):
            if len(data) > self.config.max_string_length:
                threats.append(DeserializationThreatType.SIZE_LIMIT)
        
        elif isinstance(data, list):
            if len(data) > self.config.max_array_length:
                threats.append(DeserializationThreatType.SIZE_LIMIT)
            else:
                for item in data:
                    threats.extend(self._validate_structure(item, depth + 1))
        
        elif isinstance(data, dict):
            if len(data) > self.config.max_object_keys:
                threats.append(DeserializationThreatType.SIZE_LIMIT)
            else:
                for value in data.values():
                    threats.extend(self._validate_structure(value, depth + 1))
        
        return threats


class TypeValidator:
    """Validates deserialized types."""
    
    def __init__(self, config: Optional[DeserializationConfig] = None):
        self.config = config or DeserializationConfig()
    
    def validate_type(self, data: Any) -> tuple[bool, Optional[str]]:
        """Validate that data contains only allowed types."""
        type_name = type(data).__name__
        
        if type_name not in self.config.allowed_types:
            return False, f"Disallowed type: {type_name}"
        
        # Recurse for containers
        if isinstance(data, dict):
            for key, value in data.items():
                # Keys should be strings
                if not isinstance(key, str):
                    return False, f"Non-string key: {type(key).__name__}"
                valid, error = self.validate_type(value)
                if not valid:
                    return valid, error
        
        elif isinstance(data, (list, tuple)):
            for item in data:
                valid, error = self.validate_type(item)
                if not valid:
                    return valid, error
        
        return True, None


class SafeDeserializer:
    """Safe deserializer with security checks."""
    
    def __init__(self, config: Optional[DeserializationConfig] = None):
        self.config = config or DeserializationConfig()
        self.pickle_detector = PickleDetector()
        self.yaml_detector = YAMLDetector()
        self.json_validator = JSONValidator(self.config)
        self.type_validator = TypeValidator(self.config)
    
    def deserialize_json(self, data: str) -> DeserializationReport:
        """Safely deserialize JSON."""
        if not self.config.allow_json:
            return DeserializationReport(
                status=DeserializationResult.BLOCKED,
                is_safe=False,
                error_message="JSON deserialization disabled",
            )
        
        return self.json_validator.validate(data)
    
    def deserialize_bytes(self, data: bytes) -> DeserializationReport:
        """Safely deserialize bytes, detecting format."""
        # Check for pickle
        if self.pickle_detector.is_pickle_data(data):
            if not self.config.allow_pickle:
                return DeserializationReport(
                    status=DeserializationResult.BLOCKED,
                    is_safe=False,
                    threats_detected=[DeserializationThreatType.PICKLE_EXPLOIT],
                    error_message="Pickle deserialization blocked",
                )
        
        # Try to decode as string and check for YAML
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return DeserializationReport(
                status=DeserializationResult.ERROR,
                is_safe=False,
                threats_detected=[DeserializationThreatType.MALFORMED_DATA],
                error_message="Could not decode as UTF-8",
            )
        
        # Check for YAML threats
        yaml_threats = self.yaml_detector.detect_threats(text)
        if yaml_threats and not self.config.allow_yaml:
            return DeserializationReport(
                status=DeserializationResult.BLOCKED,
                is_safe=False,
                threats_detected=yaml_threats,
                error_message="YAML deserialization blocked",
            )
        
        # Try JSON
        return self.deserialize_json(text)
    
    def validate_deserialized(self, data: Any) -> DeserializationReport:
        """Validate already-deserialized data."""
        valid, error = self.type_validator.validate_type(data)
        
        if not valid:
            return DeserializationReport(
                status=DeserializationResult.BLOCKED,
                is_safe=False,
                threats_detected=[DeserializationThreatType.UNSAFE_TYPE],
                error_message=error,
            )
        
        return DeserializationReport(
            status=DeserializationResult.SUCCESS,
            is_safe=True,
            data=data,
        )


class DeserializationSecurityService:
    """Comprehensive deserialization security service."""
    
    _instance: Optional["DeserializationSecurityService"] = None
    
    def __init__(self, config: Optional[DeserializationConfig] = None):
        self.config = config or DeserializationConfig()
        self.deserializer = SafeDeserializer(self.config)
        self.pickle_detector = PickleDetector()
        self.yaml_detector = YAMLDetector()
    
    @classmethod
    def get_instance(cls) -> "DeserializationSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: DeserializationConfig) -> "DeserializationSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def is_safe_json(self, data: str) -> bool:
        """Check if JSON is safe to deserialize."""
        result = self.deserializer.deserialize_json(data)
        return result.is_safe
    
    def deserialize_json(self, data: str) -> DeserializationReport:
        """Safely deserialize JSON."""
        return self.deserializer.deserialize_json(data)
    
    def deserialize_bytes(self, data: bytes) -> DeserializationReport:
        """Safely deserialize bytes."""
        return self.deserializer.deserialize_bytes(data)
    
    def is_pickle(self, data: bytes) -> bool:
        """Check if data is pickle format."""
        return self.pickle_detector.is_pickle_data(data)
    
    def has_yaml_threats(self, data: str) -> bool:
        """Check if data has YAML threats."""
        threats = self.yaml_detector.detect_threats(data)
        return len(threats) > 0
    
    def validate(self, data: Any) -> DeserializationReport:
        """Validate deserialized data."""
        return self.deserializer.validate_deserialized(data)


# Convenience functions
def get_deserialization_service() -> DeserializationSecurityService:
    """Get deserialization service instance."""
    return DeserializationSecurityService.get_instance()


def is_safe_json(data: str) -> bool:
    """Check if JSON is safe."""
    return get_deserialization_service().is_safe_json(data)


def deserialize_json_safe(data: str) -> DeserializationReport:
    """Safely deserialize JSON."""
    return get_deserialization_service().deserialize_json(data)


def is_pickle_data(data: bytes) -> bool:
    """Check if data is pickle."""
    return get_deserialization_service().is_pickle(data)
