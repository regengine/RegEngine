"""
SEC-023: Secure Password Hashing.

Industry-standard password hashing including:
- Argon2id (recommended)
- bcrypt (legacy support)
- PBKDF2 (FIPS compliance)
- Password strength validation
- Hash upgrade/migration support
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import argon2
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHash
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class HashAlgorithm(str, Enum):
    """Supported password hashing algorithms."""
    ARGON2ID = "argon2id"  # Recommended
    ARGON2I = "argon2i"  # Alternative Argon2
    BCRYPT = "bcrypt"  # Legacy but still secure
    PBKDF2_SHA256 = "pbkdf2-sha256"  # FIPS compliant
    PBKDF2_SHA512 = "pbkdf2-sha512"


class PasswordStrength(str, Enum):
    """Password strength levels."""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    FAIR = "fair"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


# =============================================================================
# Exceptions
# =============================================================================

class PasswordHashError(Exception):
    """Base exception for password hashing errors."""
    pass


class WeakPasswordError(Exception):
    """Password does not meet strength requirements."""
    def __init__(self, message: str, issues: List[str]):
        super().__init__(message)
        self.issues = issues


class HashVerificationError(Exception):
    """Password verification failed."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PasswordPolicy:
    """Password policy configuration."""
    min_length: int = 12
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    min_unique_chars: int = 8
    
    # Common password checks
    check_common_passwords: bool = True
    check_breached_passwords: bool = False  # Requires external API
    
    # Character sets
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # History
    prevent_password_reuse: int = 5  # Number of previous passwords to check


@dataclass
class PasswordStrengthResult:
    """Result of password strength analysis."""
    strength: PasswordStrength
    score: int  # 0-100
    issues: List[str]
    suggestions: List[str]
    meets_policy: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strength": self.strength.value,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "meets_policy": self.meets_policy,
        }


@dataclass
class HashedPassword:
    """Container for hashed password with metadata."""
    hash: str
    algorithm: HashAlgorithm
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    needs_rehash: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hash": self.hash,
            "algorithm": self.algorithm.value,
            "created_at": self.created_at.isoformat(),
            "needs_rehash": self.needs_rehash,
        }


# =============================================================================
# Common Password List (subset for demonstration)
# =============================================================================

COMMON_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "monkey", "1234567", "letmein", "trustno1", "dragon",
    "baseball", "iloveyou", "master", "sunshine", "ashley",
    "michael", "password1", "shadow", "123123", "654321",
    "superman", "qazwsx", "football", "passw0rd", "admin",
    "welcome", "hello", "charlie", "donald", "password123",
}


# =============================================================================
# Password Strength Analyzer
# =============================================================================

class PasswordStrengthAnalyzer:
    """
    Analyze password strength and compliance.
    
    Uses multiple factors to calculate strength:
    - Length
    - Character diversity
    - Pattern detection
    - Common password check
    """
    
    def __init__(self, policy: Optional[PasswordPolicy] = None):
        self._policy = policy or PasswordPolicy()
    
    def analyze(self, password: str) -> PasswordStrengthResult:
        """
        Analyze password strength.
        
        Returns comprehensive strength analysis.
        """
        issues = []
        suggestions = []
        score = 0
        
        # Normalize password
        password = unicodedata.normalize("NFKC", password)
        
        # Length check
        if len(password) < self._policy.min_length:
            issues.append(f"Password must be at least {self._policy.min_length} characters")
        elif len(password) < 16:
            suggestions.append("Consider using 16+ characters for better security")
        
        if len(password) > self._policy.max_length:
            issues.append(f"Password must be at most {self._policy.max_length} characters")
        
        # Length scoring (up to 25 points)
        length_score = min(25, len(password) * 2)
        score += length_score
        
        # Character class checks
        has_upper = bool(re.search(r"[A-Z]", password))
        has_lower = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_special = bool(re.search(f"[{re.escape(self._policy.special_chars)}]", password))
        
        if self._policy.require_uppercase and not has_upper:
            issues.append("Password must contain uppercase letters")
        if self._policy.require_lowercase and not has_lower:
            issues.append("Password must contain lowercase letters")
        if self._policy.require_digits and not has_digit:
            issues.append("Password must contain digits")
        if self._policy.require_special and not has_special:
            issues.append("Password must contain special characters")
        
        # Character diversity scoring (up to 20 points)
        diversity_score = sum([has_upper, has_lower, has_digit, has_special]) * 5
        score += diversity_score
        
        # Unique character check
        unique_chars = len(set(password))
        if unique_chars < self._policy.min_unique_chars:
            issues.append(f"Password must have at least {self._policy.min_unique_chars} unique characters")
        
        # Unique char scoring (up to 15 points)
        unique_score = min(15, unique_chars)
        score += unique_score
        
        # Pattern detection
        patterns = self._detect_patterns(password)
        if patterns:
            score -= len(patterns) * 5
            for pattern in patterns:
                issues.append(f"Password contains predictable pattern: {pattern}")
        
        # Common password check
        if self._policy.check_common_passwords:
            if password.lower() in COMMON_PASSWORDS:
                issues.append("Password is too common")
                score -= 30
        
        # Entropy estimation (up to 40 points)
        entropy = self._estimate_entropy(password)
        entropy_score = min(40, int(entropy / 2))
        score += entropy_score
        
        # Clamp score
        score = max(0, min(100, score))
        
        # Determine strength level
        if score < 20:
            strength = PasswordStrength.VERY_WEAK
        elif score < 40:
            strength = PasswordStrength.WEAK
        elif score < 60:
            strength = PasswordStrength.FAIR
        elif score < 80:
            strength = PasswordStrength.STRONG
        else:
            strength = PasswordStrength.VERY_STRONG
        
        # Generate suggestions
        if not has_upper:
            suggestions.append("Add uppercase letters")
        if not has_lower:
            suggestions.append("Add lowercase letters")
        if not has_digit:
            suggestions.append("Add numbers")
        if not has_special:
            suggestions.append("Add special characters")
        if len(password) < 16:
            suggestions.append("Make password longer")
        
        return PasswordStrengthResult(
            strength=strength,
            score=score,
            issues=issues,
            suggestions=suggestions,
            meets_policy=len(issues) == 0,
        )
    
    def _detect_patterns(self, password: str) -> List[str]:
        """Detect common patterns in password."""
        patterns = []
        lower = password.lower()
        
        # Keyboard patterns
        keyboard_patterns = [
            "qwerty", "asdf", "zxcv", "qazwsx", "1234", "4321",
            "0987", "7890", "abcd", "dcba",
        ]
        for pattern in keyboard_patterns:
            if pattern in lower:
                patterns.append("keyboard sequence")
                break
        
        # Repeated characters
        if re.search(r"(.)\1{2,}", password):
            patterns.append("repeated characters")
        
        # Sequential numbers
        if re.search(r"012|123|234|345|456|567|678|789|890", password):
            patterns.append("sequential numbers")
        
        # Sequential letters
        if re.search(r"abc|bcd|cde|def|efg|xyz", lower):
            patterns.append("sequential letters")
        
        return patterns
    
    def _estimate_entropy(self, password: str) -> float:
        """Estimate password entropy in bits."""
        import math
        
        charset_size = 0
        if re.search(r"[a-z]", password):
            charset_size += 26
        if re.search(r"[A-Z]", password):
            charset_size += 26
        if re.search(r"\d", password):
            charset_size += 10
        if re.search(r"[^a-zA-Z\d]", password):
            charset_size += 32
        
        if charset_size == 0:
            return 0
        
        return len(password) * math.log2(charset_size)


# =============================================================================
# Password Hashers
# =============================================================================

class PasswordHasherBackend(ABC):
    """Abstract base class for password hashers."""
    
    @property
    @abstractmethod
    def algorithm(self) -> HashAlgorithm:
        """Get the algorithm name."""
        pass
    
    @abstractmethod
    def hash(self, password: str) -> str:
        """Hash a password."""
        pass
    
    @abstractmethod
    def verify(self, password: str, hash: str) -> bool:
        """Verify a password against a hash."""
        pass
    
    @abstractmethod
    def needs_rehash(self, hash: str) -> bool:
        """Check if hash needs to be upgraded."""
        pass


class Argon2Hasher(PasswordHasherBackend):
    """
    Argon2id password hasher (recommended).
    
    Winner of the Password Hashing Competition.
    Provides memory-hard hashing resistant to GPU attacks.
    """
    
    def __init__(
        self,
        time_cost: int = 3,
        memory_cost: int = 65536,  # 64 MB
        parallelism: int = 4,
        hash_len: int = 32,
        salt_len: int = 16,
        variant: str = "id",  # "id", "i", or "d"
    ):
        if not ARGON2_AVAILABLE:
            raise RuntimeError("argon2-cffi library not available")
        
        self._time_cost = time_cost
        self._memory_cost = memory_cost
        self._parallelism = parallelism
        self._hash_len = hash_len
        self._salt_len = salt_len
        self._variant = variant
        
        # Determine type
        if variant == "id":
            type_val = argon2.Type.ID
        elif variant == "i":
            type_val = argon2.Type.I
        else:
            type_val = argon2.Type.D
        
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=type_val,
        )
    
    @property
    def algorithm(self) -> HashAlgorithm:
        if self._variant == "i":
            return HashAlgorithm.ARGON2I
        return HashAlgorithm.ARGON2ID
    
    def hash(self, password: str) -> str:
        """Hash password with Argon2."""
        return self._hasher.hash(password)
    
    def verify(self, password: str, hash: str) -> bool:
        """Verify password against Argon2 hash."""
        try:
            self._hasher.verify(hash, password)
            return True
        except VerifyMismatchError:
            return False
        except InvalidHash:
            return False
    
    def needs_rehash(self, hash: str) -> bool:
        """Check if hash parameters are outdated."""
        try:
            return self._hasher.check_needs_rehash(hash)
        except Exception:
            return True


class BcryptHasher(PasswordHasherBackend):
    """
    bcrypt password hasher.
    
    Well-established, but consider Argon2 for new systems.
    """
    
    def __init__(self, rounds: int = 12):
        if not BCRYPT_AVAILABLE:
            raise RuntimeError("bcrypt library not available")
        
        self._rounds = rounds
    
    @property
    def algorithm(self) -> HashAlgorithm:
        return HashAlgorithm.BCRYPT
    
    def hash(self, password: str) -> str:
        """Hash password with bcrypt."""
        salt = bcrypt.gensalt(rounds=self._rounds)
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    
    def verify(self, password: str, hash: str) -> bool:
        """Verify password against bcrypt hash."""
        try:
            return bcrypt.checkpw(password.encode(), hash.encode())
        except Exception:
            return False
    
    def needs_rehash(self, hash: str) -> bool:
        """Check if hash needs upgrade (based on rounds)."""
        try:
            # Extract rounds from hash
            parts = hash.split("$")
            if len(parts) >= 3:
                current_rounds = int(parts[2])
                return current_rounds < self._rounds
        except Exception:
            pass
        return True


class PBKDF2Hasher(PasswordHasherBackend):
    """
    PBKDF2 password hasher.
    
    FIPS 140-2 compliant. Use when compliance is required.
    """
    
    def __init__(
        self,
        iterations: int = 600000,
        algorithm: str = "sha256",
        salt_length: int = 32,
        key_length: int = 32,
    ):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        self._iterations = iterations
        self._algorithm_name = algorithm
        self._salt_length = salt_length
        self._key_length = key_length
        
        if algorithm == "sha512":
            self._hash_algorithm = hashes.SHA512()
        else:
            self._hash_algorithm = hashes.SHA256()
    
    @property
    def algorithm(self) -> HashAlgorithm:
        if self._algorithm_name == "sha512":
            return HashAlgorithm.PBKDF2_SHA512
        return HashAlgorithm.PBKDF2_SHA256
    
    def hash(self, password: str) -> str:
        """Hash password with PBKDF2."""
        salt = secrets.token_bytes(self._salt_length)
        
        kdf = PBKDF2HMAC(
            algorithm=self._hash_algorithm,
            length=self._key_length,
            salt=salt,
            iterations=self._iterations,
            backend=default_backend(),
        )
        
        key = kdf.derive(password.encode())
        
        # Format: $pbkdf2-sha256$iterations$salt$hash
        salt_b64 = base64.b64encode(salt).decode()
        key_b64 = base64.b64encode(key).decode()
        
        return f"$pbkdf2-{self._algorithm_name}${self._iterations}${salt_b64}${key_b64}"
    
    def verify(self, password: str, hash: str) -> bool:
        """Verify password against PBKDF2 hash."""
        try:
            parts = hash.split("$")
            if len(parts) != 5:
                return False
            
            _, algo, iterations, salt_b64, key_b64 = parts
            iterations = int(iterations)
            salt = base64.b64decode(salt_b64)
            expected_key = base64.b64decode(key_b64)
            
            # Determine algorithm
            if "sha512" in algo:
                hash_algo = hashes.SHA512()
            else:
                hash_algo = hashes.SHA256()
            
            kdf = PBKDF2HMAC(
                algorithm=hash_algo,
                length=len(expected_key),
                salt=salt,
                iterations=iterations,
                backend=default_backend(),
            )
            
            try:
                kdf.verify(password.encode(), expected_key)
                return True
            except Exception:
                return False
            
        except Exception:
            return False
    
    def needs_rehash(self, hash: str) -> bool:
        """Check if hash needs upgrade."""
        try:
            parts = hash.split("$")
            if len(parts) >= 3:
                current_iterations = int(parts[2])
                return current_iterations < self._iterations
        except Exception:
            pass
        return True


# =============================================================================
# Password Service
# =============================================================================

class PasswordService:
    """
    High-level service for password operations.
    
    Handles hashing, verification, strength analysis,
    and hash migration.
    """
    
    _instance: Optional["PasswordService"] = None
    
    def __init__(
        self,
        default_algorithm: HashAlgorithm = HashAlgorithm.ARGON2ID,
        policy: Optional[PasswordPolicy] = None,
    ):
        self._default_algorithm = default_algorithm
        self._policy = policy or PasswordPolicy()
        self._analyzer = PasswordStrengthAnalyzer(self._policy)
        self._hashers: Dict[HashAlgorithm, PasswordHasherBackend] = {}
        
        # Initialize available hashers
        self._init_hashers()
    
    def _init_hashers(self) -> None:
        """Initialize available hashers."""
        if ARGON2_AVAILABLE:
            self._hashers[HashAlgorithm.ARGON2ID] = Argon2Hasher(variant="id")
            self._hashers[HashAlgorithm.ARGON2I] = Argon2Hasher(variant="i")
        
        if BCRYPT_AVAILABLE:
            self._hashers[HashAlgorithm.BCRYPT] = BcryptHasher()
        
        if CRYPTOGRAPHY_AVAILABLE:
            self._hashers[HashAlgorithm.PBKDF2_SHA256] = PBKDF2Hasher(algorithm="sha256")
            self._hashers[HashAlgorithm.PBKDF2_SHA512] = PBKDF2Hasher(algorithm="sha512")
    
    @classmethod
    def configure(
        cls,
        default_algorithm: HashAlgorithm = HashAlgorithm.ARGON2ID,
        policy: Optional[PasswordPolicy] = None,
    ) -> "PasswordService":
        """Configure singleton instance."""
        cls._instance = cls(default_algorithm=default_algorithm, policy=policy)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "PasswordService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def analyze_strength(self, password: str) -> PasswordStrengthResult:
        """Analyze password strength."""
        return self._analyzer.analyze(password)
    
    def validate_password(
        self,
        password: str,
        raise_on_weak: bool = True,
    ) -> PasswordStrengthResult:
        """
        Validate password against policy.
        
        Args:
            password: Password to validate
            raise_on_weak: Raise exception if password is weak
        
        Returns:
            PasswordStrengthResult
        
        Raises:
            WeakPasswordError: If password doesn't meet policy
        """
        result = self.analyze_strength(password)
        
        if raise_on_weak and not result.meets_policy:
            raise WeakPasswordError(
                "Password does not meet security requirements",
                result.issues,
            )
        
        return result
    
    def hash_password(
        self,
        password: str,
        algorithm: Optional[HashAlgorithm] = None,
        validate: bool = True,
    ) -> HashedPassword:
        """
        Hash a password.
        
        Args:
            password: Password to hash
            algorithm: Hashing algorithm (uses default if not specified)
            validate: Validate password strength first
        
        Returns:
            HashedPassword container
        """
        if validate:
            self.validate_password(password)
        
        algo = algorithm or self._default_algorithm
        hasher = self._hashers.get(algo)
        
        if not hasher:
            raise PasswordHashError(f"Unsupported algorithm: {algo}")
        
        hash_value = hasher.hash(password)
        
        return HashedPassword(
            hash=hash_value,
            algorithm=algo,
        )
    
    def verify_password(
        self,
        password: str,
        hashed: HashedPassword,
    ) -> Tuple[bool, bool]:
        """
        Verify a password against a hash.
        
        Returns:
            (is_valid, needs_rehash) tuple
        """
        hasher = self._hashers.get(hashed.algorithm)
        
        if not hasher:
            # Try to detect algorithm from hash
            hasher = self._detect_hasher(hashed.hash)
            if not hasher:
                raise PasswordHashError(f"Unknown hash format")
        
        is_valid = hasher.verify(password, hashed.hash)
        needs_rehash = hasher.needs_rehash(hashed.hash) if is_valid else False
        
        # Also check if algorithm should be upgraded
        if is_valid and hashed.algorithm != self._default_algorithm:
            needs_rehash = True
        
        return is_valid, needs_rehash
    
    def verify_and_rehash(
        self,
        password: str,
        hashed: HashedPassword,
    ) -> Tuple[bool, Optional[HashedPassword]]:
        """
        Verify password and rehash if needed.
        
        Returns:
            (is_valid, new_hash) tuple
            new_hash is None if no rehash needed or verification failed
        """
        is_valid, needs_rehash = self.verify_password(password, hashed)
        
        if is_valid and needs_rehash:
            new_hash = self.hash_password(password, validate=False)
            return True, new_hash
        
        return is_valid, None
    
    def _detect_hasher(self, hash: str) -> Optional[PasswordHasherBackend]:
        """Detect hasher from hash format."""
        if hash.startswith("$argon2id$"):
            return self._hashers.get(HashAlgorithm.ARGON2ID)
        elif hash.startswith("$argon2i$"):
            return self._hashers.get(HashAlgorithm.ARGON2I)
        elif hash.startswith("$2b$") or hash.startswith("$2a$"):
            return self._hashers.get(HashAlgorithm.BCRYPT)
        elif hash.startswith("$pbkdf2-sha256$"):
            return self._hashers.get(HashAlgorithm.PBKDF2_SHA256)
        elif hash.startswith("$pbkdf2-sha512$"):
            return self._hashers.get(HashAlgorithm.PBKDF2_SHA512)
        
        return None
    
    def generate_password(
        self,
        length: int = 16,
        include_upper: bool = True,
        include_lower: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
    ) -> str:
        """
        Generate a secure random password.
        
        Returns:
            Generated password
        """
        chars = ""
        required = []
        
        if include_upper:
            chars += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            required.append(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        if include_lower:
            chars += "abcdefghijklmnopqrstuvwxyz"
            required.append(secrets.choice("abcdefghijklmnopqrstuvwxyz"))
        if include_digits:
            chars += "0123456789"
            required.append(secrets.choice("0123456789"))
        if include_special:
            special = "!@#$%^&*"
            chars += special
            required.append(secrets.choice(special))
        
        if not chars:
            chars = "abcdefghijklmnopqrstuvwxyz"
        
        # Generate remaining characters
        remaining = length - len(required)
        password_chars = required + [secrets.choice(chars) for _ in range(remaining)]
        
        # Shuffle
        secrets.SystemRandom().shuffle(password_chars)
        
        return "".join(password_chars)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_password_service() -> PasswordService:
    """Get the singleton password service."""
    return PasswordService.get_instance()


def hash_password(
    password: str,
    algorithm: Optional[HashAlgorithm] = None,
) -> HashedPassword:
    """Hash a password."""
    service = get_password_service()
    return service.hash_password(password, algorithm)


def verify_password(
    password: str,
    hashed: HashedPassword,
) -> Tuple[bool, bool]:
    """Verify a password."""
    service = get_password_service()
    return service.verify_password(password, hashed)


def analyze_password_strength(password: str) -> PasswordStrengthResult:
    """Analyze password strength."""
    service = get_password_service()
    return service.analyze_strength(password)


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    service = get_password_service()
    return service.generate_password(length)
