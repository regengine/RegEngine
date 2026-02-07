"""
Tests for SEC-050: Deserialization Security.

Tests cover:
- Pickle detection
- YAML threat detection
- JSON validation
- Type validation
- Safe deserialization
"""

import json
import pytest

from shared.deserialization_security import (
    # Enums
    DeserializationThreatType,
    DeserializationResult,
    # Data classes
    DeserializationConfig,
    DeserializationReport,
    # Classes
    PickleDetector,
    YAMLDetector,
    JSONValidator,
    TypeValidator,
    SafeDeserializer,
    DeserializationSecurityService,
    # Convenience functions
    get_deserialization_service,
    is_safe_json,
    deserialize_json_safe,
    is_pickle_data,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create deserialization config."""
    return DeserializationConfig()


@pytest.fixture
def pickle_detector():
    """Create pickle detector."""
    return PickleDetector()


@pytest.fixture
def yaml_detector():
    """Create YAML detector."""
    return YAMLDetector()


@pytest.fixture
def json_validator(config):
    """Create JSON validator."""
    return JSONValidator(config)


@pytest.fixture
def type_validator(config):
    """Create type validator."""
    return TypeValidator(config)


@pytest.fixture
def deserializer(config):
    """Create deserializer."""
    return SafeDeserializer(config)


@pytest.fixture
def service(config):
    """Create service."""
    DeserializationSecurityService._instance = None
    return DeserializationSecurityService(config)


@pytest.fixture
def safe_json():
    """Safe JSON data."""
    return '{"name": "John", "age": 30, "active": true}'


@pytest.fixture
def pickle_bytes():
    """Pickle-like bytes."""
    return b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00}"


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_threat_types(self):
        """Should have expected threat types."""
        assert DeserializationThreatType.PICKLE_EXPLOIT == "pickle_exploit"
        assert DeserializationThreatType.YAML_EXPLOIT == "yaml_exploit"
        assert DeserializationThreatType.TYPE_CONFUSION == "type_confusion"
    
    def test_result_types(self):
        """Should have expected result types."""
        assert DeserializationResult.SUCCESS == "success"
        assert DeserializationResult.BLOCKED == "blocked"
        assert DeserializationResult.ERROR == "error"


# =============================================================================
# Test: DeserializationConfig
# =============================================================================

class TestDeserializationConfig:
    """Test DeserializationConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = DeserializationConfig()
        
        assert config.allow_pickle is False
        assert config.allow_yaml is False
        assert config.allow_json is True
        assert config.max_depth == 20


# =============================================================================
# Test: PickleDetector
# =============================================================================

class TestPickleDetector:
    """Test PickleDetector."""
    
    def test_detects_pickle_protocol(self, pickle_detector):
        """Should detect pickle protocol marker."""
        data = b"\x80\x04\x95"
        
        assert pickle_detector.is_pickle_data(data) is True
    
    def test_detects_global_opcode(self, pickle_detector):
        """Should detect GLOBAL opcode."""
        data = b"cos\nsystem\n"
        
        assert pickle_detector.is_pickle_data(data) is True
    
    def test_detects_reduce_opcode(self, pickle_detector):
        """Should detect REDUCE opcode with other markers."""
        # Single R is not enough, need multiple opcodes
        data = b"cmodule\nfunc\nR."
        
        assert pickle_detector.is_pickle_data(data) is True
    
    def test_ignores_safe_data(self, pickle_detector):
        """Should ignore safe data."""
        data = b"hello world"
        
        assert pickle_detector.is_pickle_data(data) is False
    
    def test_detects_dangerous_modules(self, pickle_detector):
        """Should detect dangerous module references."""
        data = b"cos\nsystem\n(S'id'\ntR."
        
        threats = pickle_detector.detect_threats(data)
        
        assert DeserializationThreatType.PICKLE_EXPLOIT in threats
    
    def test_handles_non_bytes(self, pickle_detector):
        """Should handle non-bytes input."""
        assert pickle_detector.is_pickle_data("string") is False
        assert pickle_detector.detect_threats("string") == []


# =============================================================================
# Test: YAMLDetector
# =============================================================================

class TestYAMLDetector:
    """Test YAMLDetector."""
    
    def test_detects_python_object(self, yaml_detector):
        """Should detect !!python/object tag."""
        data = "!!python/object:__main__.MyClass {}"
        
        threats = yaml_detector.detect_threats(data)
        
        assert DeserializationThreatType.YAML_EXPLOIT in threats
    
    def test_detects_python_apply(self, yaml_detector):
        """Should detect !!python/object/apply tag."""
        data = "!!python/object/apply:os.system ['id']"
        
        threats = yaml_detector.detect_threats(data)
        
        assert DeserializationThreatType.YAML_EXPLOIT in threats
    
    def test_detects_python_module(self, yaml_detector):
        """Should detect !!python/module tag."""
        data = "!!python/module:os"
        
        threats = yaml_detector.detect_threats(data)
        
        assert DeserializationThreatType.YAML_EXPLOIT in threats
    
    def test_detects_exec_in_yaml(self, yaml_detector):
        """Should detect exec in YAML."""
        data = "key: exec('import os')"
        
        threats = yaml_detector.detect_threats(data)
        
        assert DeserializationThreatType.YAML_EXPLOIT in threats
    
    def test_ignores_safe_yaml(self, yaml_detector):
        """Should ignore safe YAML."""
        data = "name: John\nage: 30"
        
        threats = yaml_detector.detect_threats(data)
        
        assert len(threats) == 0
    
    def test_detects_yaml_format(self, yaml_detector):
        """Should detect YAML format."""
        assert yaml_detector.is_yaml_data("---\nkey: value") is True
        assert yaml_detector.is_yaml_data("key: value") is True
        assert yaml_detector.is_yaml_data("- item1\n- item2") is True


# =============================================================================
# Test: JSONValidator
# =============================================================================

class TestJSONValidator:
    """Test JSONValidator."""
    
    def test_validates_safe_json(self, json_validator, safe_json):
        """Should validate safe JSON."""
        result = json_validator.validate(safe_json)
        
        assert result.is_safe is True
        assert result.status == DeserializationResult.SUCCESS
        assert result.data["name"] == "John"
    
    def test_rejects_invalid_json(self, json_validator):
        """Should reject invalid JSON."""
        result = json_validator.validate("{invalid json}")
        
        assert result.is_safe is False
        assert result.status == DeserializationResult.ERROR
    
    def test_rejects_oversized_json(self, json_validator):
        """Should reject oversized JSON."""
        data = '{"x": "' + "a" * 20000000 + '"}'
        
        result = json_validator.validate(data)
        
        assert result.is_safe is False
        assert DeserializationThreatType.SIZE_LIMIT in result.threats_detected
    
    def test_rejects_deep_nesting(self):
        """Should reject deeply nested JSON."""
        config = DeserializationConfig(max_depth=5)
        validator = JSONValidator(config)
        
        # Create deeply nested JSON
        nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
        data = json.dumps(nested)
        
        result = validator.validate(data)
        
        assert result.is_safe is False
        assert DeserializationThreatType.DEPTH_LIMIT in result.threats_detected
    
    def test_rejects_large_array(self):
        """Should reject large arrays."""
        config = DeserializationConfig(max_array_length=10)
        validator = JSONValidator(config)
        
        data = json.dumps(list(range(100)))
        
        result = validator.validate(data)
        
        assert result.is_safe is False
    
    def test_rejects_many_keys(self):
        """Should reject objects with many keys."""
        config = DeserializationConfig(max_object_keys=5)
        validator = JSONValidator(config)
        
        data = json.dumps({f"key{i}": i for i in range(100)})
        
        result = validator.validate(data)
        
        assert result.is_safe is False


# =============================================================================
# Test: TypeValidator
# =============================================================================

class TestTypeValidator:
    """Test TypeValidator."""
    
    def test_allows_safe_types(self, type_validator):
        """Should allow safe types."""
        data = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
        }
        
        valid, error = type_validator.validate_type(data)
        
        assert valid is True
        assert error is None
    
    def test_rejects_unsafe_types(self):
        """Should reject unsafe types."""
        config = DeserializationConfig(allowed_types=["str", "int", "dict"])
        validator = TypeValidator(config)
        
        data = {"key": [1, 2, 3]}  # list not allowed
        
        valid, error = validator.validate_type(data)
        
        assert valid is False
    
    def test_validates_nested_types(self, type_validator):
        """Should validate nested types."""
        data = {
            "level1": {
                "level2": {
                    "value": "string",
                },
            },
        }
        
        valid, error = type_validator.validate_type(data)
        
        assert valid is True


# =============================================================================
# Test: SafeDeserializer
# =============================================================================

class TestSafeDeserializer:
    """Test SafeDeserializer."""
    
    def test_deserializes_json(self, deserializer, safe_json):
        """Should deserialize safe JSON."""
        result = deserializer.deserialize_json(safe_json)
        
        assert result.is_safe is True
        assert result.data["name"] == "John"
    
    def test_blocks_pickle(self, deserializer, pickle_bytes):
        """Should block pickle."""
        result = deserializer.deserialize_bytes(pickle_bytes)
        
        assert result.is_safe is False
        assert DeserializationThreatType.PICKLE_EXPLOIT in result.threats_detected
    
    def test_blocks_yaml_threats(self, deserializer):
        """Should block YAML threats."""
        data = b"!!python/object:__main__.Evil {}"
        
        result = deserializer.deserialize_bytes(data)
        
        assert result.is_safe is False
    
    def test_deserializes_json_bytes(self, deserializer):
        """Should deserialize JSON from bytes."""
        data = b'{"name": "test"}'
        
        result = deserializer.deserialize_bytes(data)
        
        assert result.is_safe is True
        assert result.data["name"] == "test"
    
    def test_validates_deserialized(self, deserializer):
        """Should validate already deserialized data."""
        data = {"name": "John", "items": [1, 2, 3]}
        
        result = deserializer.validate_deserialized(data)
        
        assert result.is_safe is True
    
    def test_blocks_when_json_disabled(self):
        """Should block when JSON disabled."""
        config = DeserializationConfig(allow_json=False)
        deserializer = SafeDeserializer(config)
        
        result = deserializer.deserialize_json('{"key": "value"}')
        
        assert result.is_safe is False


# =============================================================================
# Test: DeserializationSecurityService
# =============================================================================

class TestDeserializationSecurityService:
    """Test DeserializationSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        DeserializationSecurityService._instance = None
        
        s1 = get_deserialization_service()
        s2 = get_deserialization_service()
        
        assert s1 is s2
    
    def test_is_safe_json(self, service, safe_json):
        """Should check JSON safety."""
        assert service.is_safe_json(safe_json) is True
        assert service.is_safe_json("{invalid}") is False
    
    def test_deserialize_json(self, service, safe_json):
        """Should deserialize JSON."""
        result = service.deserialize_json(safe_json)
        
        assert result.is_safe is True
        assert result.data["name"] == "John"
    
    def test_deserialize_bytes(self, service):
        """Should deserialize bytes."""
        data = b'{"key": "value"}'
        
        result = service.deserialize_bytes(data)
        
        assert result.is_safe is True
    
    def test_is_pickle(self, service, pickle_bytes):
        """Should detect pickle."""
        assert service.is_pickle(pickle_bytes) is True
        assert service.is_pickle(b"plain text data") is False
    
    def test_has_yaml_threats(self, service):
        """Should detect YAML threats."""
        safe = "name: value"
        unsafe = "!!python/object:os.system {}"
        
        assert service.has_yaml_threats(safe) is False
        assert service.has_yaml_threats(unsafe) is True
    
    def test_validate(self, service):
        """Should validate data."""
        data = {"name": "test"}
        
        result = service.validate(data)
        
        assert result.is_safe is True


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_is_safe_json(self, safe_json):
        """Should check JSON safety."""
        DeserializationSecurityService._instance = None
        
        assert is_safe_json(safe_json) is True
        assert is_safe_json("{bad}") is False
    
    def test_deserialize_json_safe(self, safe_json):
        """Should deserialize JSON safely."""
        DeserializationSecurityService._instance = None
        
        result = deserialize_json_safe(safe_json)
        
        assert result.is_safe is True
    
    def test_is_pickle_data(self, pickle_bytes):
        """Should detect pickle data."""
        DeserializationSecurityService._instance = None
        
        assert is_pickle_data(pickle_bytes) is True
        assert is_pickle_data(b"safe data") is False


# =============================================================================
# Test: Attack Vectors
# =============================================================================

class TestAttackVectors:
    """Test various deserialization attack vectors."""
    
    def test_pickle_code_execution(self, pickle_detector):
        """Should detect pickle code execution."""
        # Simulated pickle exploit payload
        data = b"cos\nsystem\n(S'id'\ntR."
        
        threats = pickle_detector.detect_threats(data)
        
        assert DeserializationThreatType.PICKLE_EXPLOIT in threats
    
    def test_yaml_code_execution(self, yaml_detector):
        """Should detect YAML code execution."""
        data = "!!python/object/apply:subprocess.check_output [['id']]"
        
        threats = yaml_detector.detect_threats(data)
        
        assert DeserializationThreatType.YAML_EXPLOIT in threats
    
    def test_json_depth_bomb(self, json_validator):
        """Should detect JSON depth bomb."""
        # Create deeply nested JSON
        depth = 100
        data = '{"a":' * depth + '1' + '}' * depth
        
        result = json_validator.validate(data)
        
        # Should be blocked due to depth
        assert result.is_safe is False
    
    def test_json_width_bomb(self):
        """Should detect JSON width bomb."""
        config = DeserializationConfig(max_object_keys=100)
        validator = JSONValidator(config)
        
        # Create wide JSON
        data = json.dumps({f"k{i}": i for i in range(500)})
        
        result = validator.validate(data)
        
        assert result.is_safe is False
