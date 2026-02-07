"""
Tests for SEC-025: Secure Random Generation.

Tests cover:
- Random bytes generation
- Random integer generation
- Random string generation
- Token generation
- UUID generation
- Entropy validation
"""

import pytest
import re
import string
from collections import Counter

from shared.secure_random import (
    # Enums
    CharacterSet,
    TokenFormat,
    # Exceptions
    RandomGenerationError,
    InvalidParameterError,
    # Data classes
    EntropyInfo,
    GeneratedToken,
    # Classes
    EntropySource,
    RandomBytesGenerator,
    RandomIntegerGenerator,
    RandomStringGenerator,
    TokenGenerator,
    UUIDGenerator,
    SecureRandomService,
    # Convenience functions
    get_secure_random,
    random_bytes,
    random_int,
    random_string,
    random_token,
    random_uuid,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def entropy_source():
    """Create entropy source."""
    return EntropySource()


@pytest.fixture
def service():
    """Create secure random service."""
    return SecureRandomService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_character_sets(self):
        """Should have expected character sets."""
        assert CharacterSet.ALPHANUMERIC == "alphanumeric"
        assert CharacterSet.HEXADECIMAL == "hexadecimal"
        assert CharacterSet.URL_SAFE == "url_safe"
    
    def test_token_formats(self):
        """Should have expected token formats."""
        assert TokenFormat.HEX == "hex"
        assert TokenFormat.BASE64 == "base64"
        assert TokenFormat.BASE64_URL == "base64_url"


# =============================================================================
# Test: Entropy Source
# =============================================================================

class TestEntropySource:
    """Test EntropySource."""
    
    def test_get_bytes(self, entropy_source):
        """Should generate random bytes."""
        data = entropy_source.get_bytes(32)
        
        assert len(data) == 32
        assert isinstance(data, bytes)
    
    def test_get_bytes_different_sizes(self, entropy_source):
        """Should generate various sizes."""
        for size in [1, 16, 32, 64, 128, 256]:
            data = entropy_source.get_bytes(size)
            assert len(data) == size
    
    def test_get_bytes_invalid_size(self, entropy_source):
        """Should reject invalid size."""
        with pytest.raises(InvalidParameterError):
            entropy_source.get_bytes(0)
        
        with pytest.raises(InvalidParameterError):
            entropy_source.get_bytes(-1)
    
    def test_validate_entropy(self, entropy_source):
        """Should validate entropy availability."""
        assert entropy_source.validate_entropy(128) is True
        assert entropy_source.validate_entropy(256) is True
    
    def test_entropy_info(self, entropy_source):
        """Should provide entropy info."""
        info = entropy_source.get_entropy_info(256)
        
        assert info.bits_requested == 256
        assert info.quality == "high"


# =============================================================================
# Test: Random Bytes Generator
# =============================================================================

class TestRandomBytesGenerator:
    """Test RandomBytesGenerator."""
    
    def test_generate(self):
        """Should generate random bytes."""
        gen = RandomBytesGenerator()
        data = gen.generate(32)
        
        assert len(data) == 32
    
    def test_generate_unique(self):
        """Should generate unique values."""
        gen = RandomBytesGenerator()
        
        values = [gen.generate(32) for _ in range(100)]
        unique = set(values)
        
        # All values should be unique
        assert len(unique) == 100
    
    def test_generate_bits(self):
        """Should generate by bit count."""
        gen = RandomBytesGenerator()
        
        data = gen.generate_bits(256)
        assert len(data) == 32  # 256 / 8
        
        data = gen.generate_bits(128)
        assert len(data) == 16


# =============================================================================
# Test: Random Integer Generator
# =============================================================================

class TestRandomIntegerGenerator:
    """Test RandomIntegerGenerator."""
    
    def test_generate_in_range(self):
        """Should generate in range."""
        gen = RandomIntegerGenerator()
        
        for _ in range(100):
            value = gen.generate(0, 100)
            assert 0 <= value <= 100
    
    def test_generate_lower_bound(self):
        """Should respect lower bound."""
        gen = RandomIntegerGenerator()
        
        for _ in range(100):
            value = gen.generate(50, 100)
            assert value >= 50
    
    def test_generate_upper_bound(self):
        """Should respect upper bound."""
        gen = RandomIntegerGenerator()
        
        for _ in range(100):
            value = gen.generate(0, 10)
            assert value <= 10
    
    def test_generate_equal_bounds(self):
        """Should handle equal bounds."""
        gen = RandomIntegerGenerator()
        
        value = gen.generate(42, 42)
        assert value == 42
    
    def test_generate_invalid_bounds(self):
        """Should reject invalid bounds."""
        gen = RandomIntegerGenerator()
        
        with pytest.raises(InvalidParameterError):
            gen.generate(100, 50)
    
    def test_generate_n_bits(self):
        """Should generate n-bit integer."""
        gen = RandomIntegerGenerator()
        
        value = gen.generate_n_bits(8)
        assert 0 <= value < 256
        
        value = gen.generate_n_bits(16)
        assert 0 <= value < 65536
    
    def test_distribution(self):
        """Should have uniform distribution."""
        gen = RandomIntegerGenerator()
        
        # Generate many values and check distribution
        counts = Counter(gen.generate(0, 9) for _ in range(10000))
        
        # Each digit should appear roughly 1000 times (10%)
        for count in counts.values():
            assert 700 < count < 1300  # Allow some variance


# =============================================================================
# Test: Random String Generator
# =============================================================================

class TestRandomStringGenerator:
    """Test RandomStringGenerator."""
    
    def test_generate_alphanumeric(self):
        """Should generate alphanumeric string."""
        gen = RandomStringGenerator()
        
        s = gen.generate(32, CharacterSet.ALPHANUMERIC)
        
        assert len(s) == 32
        assert all(c in string.ascii_letters + string.digits for c in s)
    
    def test_generate_hexadecimal(self):
        """Should generate hex string."""
        gen = RandomStringGenerator()
        
        s = gen.generate(32, CharacterSet.HEXADECIMAL)
        
        assert len(s) == 32
        assert all(c in "0123456789abcdef" for c in s)
    
    def test_generate_digits(self):
        """Should generate digit string."""
        gen = RandomStringGenerator()
        
        s = gen.generate(16, CharacterSet.DIGITS)
        
        assert len(s) == 16
        assert s.isdigit()
    
    def test_generate_custom_charset(self):
        """Should support custom charset."""
        gen = RandomStringGenerator()
        
        s = gen.generate(10, "ABC")
        
        assert len(s) == 10
        assert all(c in "ABC" for c in s)
    
    def test_generate_invalid_length(self):
        """Should reject invalid length."""
        gen = RandomStringGenerator()
        
        with pytest.raises(InvalidParameterError):
            gen.generate(0)
    
    def test_generate_with_requirements(self):
        """Should meet character requirements."""
        gen = RandomStringGenerator()
        
        for _ in range(20):
            s = gen.generate_with_requirements(
                length=16,
                require_upper=True,
                require_lower=True,
                require_digits=True,
                require_special=True,
            )
            
            assert len(s) == 16
            assert any(c.isupper() for c in s)
            assert any(c.islower() for c in s)
            assert any(c.isdigit() for c in s)
            assert any(c in "!@#$%^&*" for c in s)
    
    def test_calculate_entropy(self):
        """Should calculate entropy correctly."""
        gen = RandomStringGenerator()
        
        # 26 lowercase letters
        entropy = gen.calculate_entropy(8, 26)
        assert entropy > 37  # log2(26^8) ≈ 37.6
        
        # 62 alphanumeric
        entropy = gen.calculate_entropy(16, 62)
        assert entropy > 95  # log2(62^16) ≈ 95.3


# =============================================================================
# Test: Token Generator
# =============================================================================

class TestTokenGenerator:
    """Test TokenGenerator."""
    
    def test_generate_hex(self):
        """Should generate hex token."""
        gen = TokenGenerator()
        
        token = gen.generate(256, TokenFormat.HEX)
        
        assert len(token.value) == 64  # 256 bits = 32 bytes = 64 hex chars
        assert all(c in "0123456789abcdef" for c in token.value)
    
    def test_generate_base64(self):
        """Should generate base64 token."""
        gen = TokenGenerator()
        
        token = gen.generate(256, TokenFormat.BASE64)
        
        # Base64 is roughly 4/3 of byte length
        assert token.format == TokenFormat.BASE64
    
    def test_generate_url_safe(self):
        """Should generate URL-safe token."""
        gen = TokenGenerator()
        
        token = gen.generate(256, TokenFormat.BASE64_URL)
        
        # Should not contain + or /
        assert "+" not in token.value
        assert "/" not in token.value
    
    def test_generate_api_key(self):
        """Should generate API key."""
        gen = TokenGenerator()
        
        key = gen.generate_api_key("sk_test_")
        
        assert key.startswith("sk_test_")
    
    def test_token_metadata(self):
        """Should include metadata."""
        gen = TokenGenerator()
        
        token = gen.generate(256)
        
        assert token.bits == 256
        assert token.entropy_source is not None


# =============================================================================
# Test: UUID Generator
# =============================================================================

class TestUUIDGenerator:
    """Test UUIDGenerator."""
    
    def test_generate_v4(self):
        """Should generate UUID v4."""
        gen = UUIDGenerator()
        
        uuid = gen.generate_v4()
        
        # UUID format: 8-4-4-4-12
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        assert re.match(pattern, uuid)
    
    def test_generate_v7(self):
        """Should generate UUID v7."""
        gen = UUIDGenerator()
        
        uuid = gen.generate_v7()
        
        # UUID format: 8-4-4-4-12
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        assert re.match(pattern, uuid)
    
    def test_v7_ordering(self):
        """UUID v7 should be time-ordered (across different milliseconds)."""
        import time
        gen = UUIDGenerator()
        
        # Generate UUIDs with small delays to ensure different timestamps
        uuids = []
        for _ in range(5):
            uuids.append(gen.generate_v7())
            time.sleep(0.002)  # 2ms delay
        
        # Should be in increasing order when generated across different milliseconds
        assert uuids == sorted(uuids)
    
    def test_generate_short(self):
        """Should generate short ID."""
        gen = UUIDGenerator()
        
        short_id = gen.generate_short(12)
        
        assert len(short_id) == 12
    
    def test_uniqueness(self):
        """Should generate unique UUIDs."""
        gen = UUIDGenerator()
        
        uuids = [gen.generate_v4() for _ in range(1000)]
        
        assert len(set(uuids)) == 1000


# =============================================================================
# Test: Secure Random Service
# =============================================================================

class TestSecureRandomService:
    """Test SecureRandomService."""
    
    def test_random_bytes(self, service):
        """Should generate random bytes."""
        data = service.random_bytes(32)
        
        assert len(data) == 32
    
    def test_random_int(self, service):
        """Should generate random int."""
        value = service.random_int(1, 100)
        
        assert 1 <= value <= 100
    
    def test_random_string(self, service):
        """Should generate random string."""
        s = service.random_string(20)
        
        assert len(s) == 20
    
    def test_random_password(self, service):
        """Should generate strong password."""
        pwd = service.random_password(16)
        
        assert len(pwd) == 16
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)
    
    def test_random_token(self, service):
        """Should generate random token."""
        token = service.random_token(256)
        
        assert len(token) == 64  # Hex
    
    def test_uuid(self, service):
        """Should generate UUID."""
        uuid = service.uuid()
        
        assert len(uuid) == 36
    
    def test_choice(self, service):
        """Should select random element."""
        items = ["a", "b", "c", "d"]
        
        for _ in range(20):
            choice = service.choice(items)
            assert choice in items
    
    def test_sample(self, service):
        """Should sample unique elements."""
        items = list(range(100))
        
        sample = service.sample(items, 10)
        
        assert len(sample) == 10
        assert len(set(sample)) == 10  # All unique
    
    def test_shuffle(self, service):
        """Should shuffle list."""
        original = list(range(100))
        shuffled = list(original)
        
        service.shuffle(shuffled)
        
        # Should contain same elements
        assert sorted(shuffled) == original
        # Should be different order (with high probability)
        assert shuffled != original


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_secure_random(self):
        """Should return singleton."""
        s1 = get_secure_random()
        s2 = get_secure_random()
        
        assert s1 is s2
    
    def test_random_bytes_function(self):
        """Should generate bytes."""
        data = random_bytes(32)
        
        assert len(data) == 32
    
    def test_random_int_function(self):
        """Should generate int."""
        value = random_int(0, 100)
        
        assert 0 <= value <= 100
    
    def test_random_string_function(self):
        """Should generate string."""
        s = random_string(20)
        
        assert len(s) == 20
    
    def test_random_token_function(self):
        """Should generate token."""
        token = random_token(128)
        
        assert len(token) == 32  # 128 bits = 16 bytes = 32 hex
    
    def test_random_uuid_function(self):
        """Should generate UUID."""
        uuid = random_uuid()
        
        assert len(uuid) == 36
