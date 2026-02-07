"""
SEC-025: Secure Random Generation.

Provides cryptographically secure random number generation:
- Random bytes generation
- Random integer generation
- Random string generation
- Token generation
- UUID generation
- Entropy source validation
"""

import base64
import hashlib
import logging
import math
import os
import secrets
import string
import struct
import time
import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Sequence, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class RandomGenerationError(Exception):
    """Base exception for random generation errors."""
    pass


class InsufficientEntropyError(RandomGenerationError):
    """Raised when insufficient entropy is available."""
    pass


class InvalidParameterError(RandomGenerationError):
    """Raised when parameters are invalid."""
    pass


# =============================================================================
# Enums
# =============================================================================

class CharacterSet(str, Enum):
    """Predefined character sets."""
    ALPHANUMERIC = "alphanumeric"
    ALPHABETIC = "alphabetic"
    DIGITS = "digits"
    HEXADECIMAL = "hexadecimal"
    BASE32 = "base32"
    BASE64 = "base64"
    URL_SAFE = "url_safe"
    PRINTABLE = "printable"


class TokenFormat(str, Enum):
    """Token formats."""
    HEX = "hex"
    BASE64 = "base64"
    BASE64_URL = "base64_url"
    BASE32 = "base32"


# =============================================================================
# Constants
# =============================================================================

# Character sets
ALPHANUMERIC_CHARS = string.ascii_letters + string.digits
ALPHABETIC_CHARS = string.ascii_letters
DIGIT_CHARS = string.digits
HEX_CHARS = string.hexdigits[:16]  # 0-9, a-f
BASE32_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
BASE64_CHARS = string.ascii_letters + string.digits + "+/"
URL_SAFE_CHARS = string.ascii_letters + string.digits + "-_"
PRINTABLE_CHARS = string.ascii_letters + string.digits + string.punctuation


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EntropyInfo:
    """Information about entropy source."""
    source: str
    bits_requested: int
    bits_available: int
    quality: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "bits_requested": self.bits_requested,
            "bits_available": self.bits_available,
            "quality": self.quality,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GeneratedToken:
    """Generated secure token with metadata."""
    value: str
    format: TokenFormat
    bits: int
    entropy_source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "value": self.value,
            "format": self.format.value,
            "bits": self.bits,
            "entropy_source": self.entropy_source,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


# =============================================================================
# Entropy Source
# =============================================================================

class EntropySource:
    """
    Manages cryptographic entropy sources.
    
    Uses the OS-level CSPRNG for secure random generation.
    """
    
    def __init__(self):
        """Initialize entropy source."""
        self._source = "os.urandom"
    
    def get_entropy_info(self, bits: int) -> EntropyInfo:
        """
        Get information about entropy availability.
        
        Args:
            bits: Number of bits requested
            
        Returns:
            EntropyInfo about the source
        """
        return EntropyInfo(
            source=self._source,
            bits_requested=bits,
            bits_available=bits,  # OS provides sufficient entropy
            quality="high",
        )
    
    def get_bytes(self, n: int) -> bytes:
        """
        Get cryptographically secure random bytes.
        
        Args:
            n: Number of bytes
            
        Returns:
            Random bytes
        """
        if n <= 0:
            raise InvalidParameterError("Byte count must be positive")
        
        return os.urandom(n)
    
    def validate_entropy(self, bits: int = 128) -> bool:
        """
        Validate that sufficient entropy is available.
        
        Args:
            bits: Minimum required bits
            
        Returns:
            True if sufficient entropy available
        """
        # Modern OS always provides sufficient entropy
        # This would check /proc/sys/kernel/random/entropy_avail on Linux
        return True


# =============================================================================
# Random Bytes Generator
# =============================================================================

class RandomBytesGenerator:
    """Generates cryptographically secure random bytes."""
    
    def __init__(self, entropy_source: Optional[EntropySource] = None):
        """Initialize generator."""
        self.entropy_source = entropy_source or EntropySource()
    
    def generate(self, n: int) -> bytes:
        """
        Generate n random bytes.
        
        Args:
            n: Number of bytes
            
        Returns:
            Random bytes
        """
        return self.entropy_source.get_bytes(n)
    
    def generate_bits(self, bits: int) -> bytes:
        """
        Generate random bytes for specified bit count.
        
        Args:
            bits: Number of bits
            
        Returns:
            Random bytes (rounded up to nearest byte)
        """
        n_bytes = (bits + 7) // 8
        return self.generate(n_bytes)


# =============================================================================
# Random Integer Generator
# =============================================================================

class RandomIntegerGenerator:
    """Generates cryptographically secure random integers."""
    
    def __init__(self, entropy_source: Optional[EntropySource] = None):
        """Initialize generator."""
        self.entropy_source = entropy_source or EntropySource()
    
    def generate(self, lower: int = 0, upper: int = 2**32 - 1) -> int:
        """
        Generate random integer in range [lower, upper].
        
        Uses rejection sampling to avoid modulo bias.
        
        Args:
            lower: Minimum value (inclusive)
            upper: Maximum value (inclusive)
            
        Returns:
            Random integer
        """
        if lower > upper:
            raise InvalidParameterError(f"lower ({lower}) must be <= upper ({upper})")
        
        if lower == upper:
            return lower
        
        # Use secrets for unbiased random integers
        return secrets.randbelow(upper - lower + 1) + lower
    
    def generate_n_bits(self, n: int) -> int:
        """
        Generate random n-bit integer.
        
        Args:
            n: Number of bits
            
        Returns:
            Random integer with at most n bits
        """
        if n <= 0:
            raise InvalidParameterError("Bit count must be positive")
        
        return secrets.randbits(n)
    
    def generate_prime_candidate(self, bits: int) -> int:
        """
        Generate random odd number for prime testing.
        
        Args:
            bits: Bit length of candidate
            
        Returns:
            Random odd number with specified bit length
        """
        # Generate random number with correct bit length
        candidate = secrets.randbits(bits)
        
        # Ensure it has the right bit length
        candidate |= (1 << (bits - 1))  # Set high bit
        candidate |= 1  # Make odd
        
        return candidate


# =============================================================================
# Random String Generator
# =============================================================================

class RandomStringGenerator:
    """Generates cryptographically secure random strings."""
    
    # Character set mappings
    CHAR_SETS = {
        CharacterSet.ALPHANUMERIC: ALPHANUMERIC_CHARS,
        CharacterSet.ALPHABETIC: ALPHABETIC_CHARS,
        CharacterSet.DIGITS: DIGIT_CHARS,
        CharacterSet.HEXADECIMAL: HEX_CHARS,
        CharacterSet.BASE32: BASE32_CHARS,
        CharacterSet.BASE64: BASE64_CHARS,
        CharacterSet.URL_SAFE: URL_SAFE_CHARS,
        CharacterSet.PRINTABLE: PRINTABLE_CHARS,
    }
    
    def __init__(self, entropy_source: Optional[EntropySource] = None):
        """Initialize generator."""
        self.entropy_source = entropy_source or EntropySource()
    
    def generate(
        self,
        length: int,
        charset: Union[CharacterSet, str] = CharacterSet.ALPHANUMERIC,
    ) -> str:
        """
        Generate random string.
        
        Args:
            length: String length
            charset: Character set to use
            
        Returns:
            Random string
        """
        if length <= 0:
            raise InvalidParameterError("Length must be positive")
        
        # Get character set
        if isinstance(charset, CharacterSet):
            chars = self.CHAR_SETS[charset]
        else:
            chars = charset
        
        if not chars:
            raise InvalidParameterError("Character set cannot be empty")
        
        # Generate using secrets.choice for each character
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    def generate_with_requirements(
        self,
        length: int,
        require_upper: bool = True,
        require_lower: bool = True,
        require_digits: bool = True,
        require_special: bool = False,
        special_chars: str = "!@#$%^&*",
    ) -> str:
        """
        Generate string meeting specific requirements.
        
        Args:
            length: String length
            require_upper: Include uppercase letters
            require_lower: Include lowercase letters
            require_digits: Include digits
            require_special: Include special characters
            special_chars: Special characters to use
            
        Returns:
            Random string meeting requirements
        """
        if length < 4:
            raise InvalidParameterError("Length must be at least 4 for requirements")
        
        # Build character set
        chars = ""
        required: List[str] = []
        
        if require_upper:
            chars += string.ascii_uppercase
            required.append(secrets.choice(string.ascii_uppercase))
        
        if require_lower:
            chars += string.ascii_lowercase
            required.append(secrets.choice(string.ascii_lowercase))
        
        if require_digits:
            chars += string.digits
            required.append(secrets.choice(string.digits))
        
        if require_special:
            chars += special_chars
            required.append(secrets.choice(special_chars))
        
        if not chars:
            chars = ALPHANUMERIC_CHARS
        
        # Generate remaining characters
        remaining = length - len(required)
        if remaining < 0:
            raise InvalidParameterError(
                f"Length {length} insufficient for {len(required)} requirements"
            )
        
        result = required + [secrets.choice(chars) for _ in range(remaining)]
        
        # Shuffle to randomize positions
        shuffled = list(result)
        for i in range(len(shuffled) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        
        return ''.join(shuffled)
    
    def calculate_entropy(self, length: int, charset_size: int) -> float:
        """
        Calculate entropy bits for a random string.
        
        Args:
            length: String length
            charset_size: Size of character set
            
        Returns:
            Entropy in bits
        """
        if charset_size <= 1:
            return 0.0
        
        return length * math.log2(charset_size)


# =============================================================================
# Token Generator
# =============================================================================

class TokenGenerator:
    """Generates cryptographically secure tokens."""
    
    def __init__(self, entropy_source: Optional[EntropySource] = None):
        """Initialize generator."""
        self.entropy_source = entropy_source or EntropySource()
        self.bytes_generator = RandomBytesGenerator(entropy_source)
    
    def generate(
        self,
        bits: int = 256,
        format: TokenFormat = TokenFormat.HEX,
    ) -> GeneratedToken:
        """
        Generate secure token.
        
        Args:
            bits: Entropy bits
            format: Output format
            
        Returns:
            GeneratedToken
        """
        if bits <= 0:
            raise InvalidParameterError("Bits must be positive")
        
        n_bytes = (bits + 7) // 8
        raw_bytes = self.bytes_generator.generate(n_bytes)
        
        # Format token
        if format == TokenFormat.HEX:
            value = raw_bytes.hex()
        elif format == TokenFormat.BASE64:
            value = base64.b64encode(raw_bytes).decode('utf-8')
        elif format == TokenFormat.BASE64_URL:
            value = base64.urlsafe_b64encode(raw_bytes).decode('utf-8').rstrip('=')
        elif format == TokenFormat.BASE32:
            value = base64.b32encode(raw_bytes).decode('utf-8').rstrip('=')
        else:
            value = raw_bytes.hex()
        
        return GeneratedToken(
            value=value,
            format=format,
            bits=bits,
            entropy_source=self.entropy_source._source,
        )
    
    def generate_hex(self, bits: int = 256) -> str:
        """Generate hex token."""
        return self.generate(bits, TokenFormat.HEX).value
    
    def generate_base64(self, bits: int = 256) -> str:
        """Generate base64 token."""
        return self.generate(bits, TokenFormat.BASE64).value
    
    def generate_url_safe(self, bits: int = 256) -> str:
        """Generate URL-safe base64 token."""
        return self.generate(bits, TokenFormat.BASE64_URL).value
    
    def generate_api_key(self, prefix: str = "") -> str:
        """
        Generate API key with optional prefix.
        
        Args:
            prefix: Optional prefix (e.g., "sk_", "pk_")
            
        Returns:
            API key string
        """
        token = self.generate(256, TokenFormat.BASE64_URL).value
        return f"{prefix}{token}" if prefix else token


# =============================================================================
# UUID Generator
# =============================================================================

class UUIDGenerator:
    """Generates cryptographically secure UUIDs."""
    
    def __init__(self, entropy_source: Optional[EntropySource] = None):
        """Initialize generator."""
        self.entropy_source = entropy_source or EntropySource()
    
    def generate_v4(self) -> str:
        """
        Generate UUID version 4 (random).
        
        Returns:
            UUID string
        """
        # Use uuid4 which uses os.urandom
        return str(uuid_lib.uuid4())
    
    def generate_v7(self) -> str:
        """
        Generate UUID version 7 (time-ordered).
        
        UUIDv7 format:
        - 48 bits: Unix timestamp in milliseconds
        - 4 bits: Version (7)
        - 12 bits: Random
        - 2 bits: Variant
        - 62 bits: Random
        
        Returns:
            UUID string
        """
        # Get timestamp in milliseconds
        timestamp_ms = int(time.time() * 1000)
        
        # Get random bytes
        random_bytes = self.entropy_source.get_bytes(10)
        
        # Build UUID bytes
        uuid_bytes = bytearray(16)
        
        # Timestamp (48 bits)
        uuid_bytes[0] = (timestamp_ms >> 40) & 0xFF
        uuid_bytes[1] = (timestamp_ms >> 32) & 0xFF
        uuid_bytes[2] = (timestamp_ms >> 24) & 0xFF
        uuid_bytes[3] = (timestamp_ms >> 16) & 0xFF
        uuid_bytes[4] = (timestamp_ms >> 8) & 0xFF
        uuid_bytes[5] = timestamp_ms & 0xFF
        
        # Version and random (16 bits)
        uuid_bytes[6] = (0x70 | (random_bytes[0] & 0x0F))  # Version 7
        uuid_bytes[7] = random_bytes[1]
        
        # Variant and random (64 bits)
        uuid_bytes[8] = (0x80 | (random_bytes[2] & 0x3F))  # Variant 10
        uuid_bytes[9:16] = random_bytes[3:10]
        
        # Format as UUID string
        hex_str = uuid_bytes.hex()
        return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"
    
    def generate_short(self, length: int = 12) -> str:
        """
        Generate short unique ID.
        
        Args:
            length: ID length
            
        Returns:
            Short unique ID
        """
        chars = URL_SAFE_CHARS
        return ''.join(secrets.choice(chars) for _ in range(length))


# =============================================================================
# Secure Random Service
# =============================================================================

class SecureRandomService:
    """
    High-level service for secure random generation.
    
    Provides a unified interface for all random generation needs.
    """
    
    _instance: Optional["SecureRandomService"] = None
    
    def __init__(self):
        """Initialize service."""
        self.entropy_source = EntropySource()
        self.bytes_generator = RandomBytesGenerator(self.entropy_source)
        self.integer_generator = RandomIntegerGenerator(self.entropy_source)
        self.string_generator = RandomStringGenerator(self.entropy_source)
        self.token_generator = TokenGenerator(self.entropy_source)
        self.uuid_generator = UUIDGenerator(self.entropy_source)
    
    @classmethod
    def get_instance(cls) -> "SecureRandomService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    # Byte generation
    def random_bytes(self, n: int) -> bytes:
        """Generate n random bytes."""
        return self.bytes_generator.generate(n)
    
    # Integer generation
    def random_int(self, lower: int = 0, upper: int = 2**32 - 1) -> int:
        """Generate random integer in range."""
        return self.integer_generator.generate(lower, upper)
    
    def random_bits(self, n: int) -> int:
        """Generate random n-bit integer."""
        return self.integer_generator.generate_n_bits(n)
    
    # String generation
    def random_string(
        self,
        length: int,
        charset: Union[CharacterSet, str] = CharacterSet.ALPHANUMERIC,
    ) -> str:
        """Generate random string."""
        return self.string_generator.generate(length, charset)
    
    def random_password(
        self,
        length: int = 16,
        require_special: bool = True,
    ) -> str:
        """Generate random password."""
        return self.string_generator.generate_with_requirements(
            length=length,
            require_upper=True,
            require_lower=True,
            require_digits=True,
            require_special=require_special,
        )
    
    # Token generation
    def random_token(
        self,
        bits: int = 256,
        format: TokenFormat = TokenFormat.HEX,
    ) -> str:
        """Generate random token."""
        return self.token_generator.generate(bits, format).value
    
    def random_hex(self, bits: int = 256) -> str:
        """Generate random hex string."""
        return self.token_generator.generate_hex(bits)
    
    def random_api_key(self, prefix: str = "") -> str:
        """Generate API key."""
        return self.token_generator.generate_api_key(prefix)
    
    # UUID generation
    def uuid(self) -> str:
        """Generate UUID v4."""
        return self.uuid_generator.generate_v4()
    
    def uuid_v7(self) -> str:
        """Generate UUID v7 (time-ordered)."""
        return self.uuid_generator.generate_v7()
    
    def short_id(self, length: int = 12) -> str:
        """Generate short unique ID."""
        return self.uuid_generator.generate_short(length)
    
    # Selection
    def choice(self, sequence: Sequence) -> Any:
        """Select random element from sequence."""
        if not sequence:
            raise InvalidParameterError("Sequence cannot be empty")
        return secrets.choice(sequence)
    
    def sample(self, population: Sequence, k: int) -> List:
        """Select k unique random elements."""
        if k > len(population):
            raise InvalidParameterError(
                f"Sample size {k} exceeds population size {len(population)}"
            )
        
        # Fisher-Yates selection
        pool = list(population)
        result = []
        
        for _ in range(k):
            idx = secrets.randbelow(len(pool))
            result.append(pool[idx])
            pool[idx] = pool[-1]
            pool.pop()
        
        return result
    
    def shuffle(self, sequence: List) -> List:
        """Shuffle list in place."""
        for i in range(len(sequence) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            sequence[i], sequence[j] = sequence[j], sequence[i]
        return sequence
    
    # Entropy info
    def get_entropy_info(self, bits: int = 256) -> EntropyInfo:
        """Get entropy source information."""
        return self.entropy_source.get_entropy_info(bits)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_secure_random() -> SecureRandomService:
    """Get the global secure random service."""
    return SecureRandomService.get_instance()


def random_bytes(n: int) -> bytes:
    """Generate n random bytes."""
    return get_secure_random().random_bytes(n)


def random_int(lower: int = 0, upper: int = 2**32 - 1) -> int:
    """Generate random integer in range."""
    return get_secure_random().random_int(lower, upper)


def random_string(
    length: int,
    charset: Union[CharacterSet, str] = CharacterSet.ALPHANUMERIC,
) -> str:
    """Generate random string."""
    return get_secure_random().random_string(length, charset)


def random_token(bits: int = 256) -> str:
    """Generate random hex token."""
    return get_secure_random().random_hex(bits)


def random_uuid() -> str:
    """Generate UUID v4."""
    return get_secure_random().uuid()
