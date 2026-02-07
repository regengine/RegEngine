"""
SEC-044: Password Security.

Secure password handling with hashing, validation,
strength checking, and breach detection.
"""

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PasswordStrength(str, Enum):
    """Password strength levels."""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    FAIR = "fair"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class HashAlgorithm(str, Enum):
    """Password hashing algorithms."""
    PBKDF2_SHA256 = "pbkdf2_sha256"
    PBKDF2_SHA512 = "pbkdf2_sha512"
    ARGON2 = "argon2"  # Requires argon2-cffi
    BCRYPT = "bcrypt"  # Requires bcrypt


@dataclass
class PasswordPolicy:
    """Password policy configuration."""
    
    # Length
    min_length: int = 12
    max_length: int = 128
    
    # Character requirements
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # Restrictions
    max_consecutive_chars: int = 3
    disallow_common_passwords: bool = True
    disallow_username_in_password: bool = True
    
    # History
    password_history_count: int = 5


@dataclass
class HashConfig:
    """Password hashing configuration."""
    
    algorithm: HashAlgorithm = HashAlgorithm.PBKDF2_SHA256
    iterations: int = 600000  # OWASP recommended
    salt_length: int = 32
    hash_length: int = 64


@dataclass
class PasswordValidationResult:
    """Result of password validation."""
    
    is_valid: bool
    strength: PasswordStrength = PasswordStrength.VERY_WEAK
    score: int = 0
    errors: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


@dataclass
class HashedPassword:
    """Represents a hashed password."""
    
    hash: str
    salt: str
    algorithm: str
    iterations: int
    
    def to_string(self) -> str:
        """Convert to storable string."""
        return f"{self.algorithm}${self.iterations}${self.salt}${self.hash}"
    
    @classmethod
    def from_string(cls, stored: str) -> "HashedPassword":
        """Create from stored string."""
        parts = stored.split("$")
        if len(parts) != 4:
            raise ValueError("Invalid hash format")
        
        return cls(
            algorithm=parts[0],
            iterations=int(parts[1]),
            salt=parts[2],
            hash=parts[3],
        )


# Common passwords list (abbreviated - in production, use a larger list)
COMMON_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "monkey", "1234567", "letmein", "trustno1", "dragon",
    "baseball", "iloveyou", "master", "sunshine", "ashley",
    "bailey", "shadow", "passw0rd", "password1", "password123",
}


class PasswordValidator:
    """Validates password against policy."""
    
    def __init__(self, policy: Optional[PasswordPolicy] = None):
        self.policy = policy or PasswordPolicy()
    
    def validate(
        self,
        password: str,
        username: Optional[str] = None,
    ) -> PasswordValidationResult:
        """Validate password against policy."""
        errors = []
        suggestions = []
        score = 0
        
        # Check length
        if len(password) < self.policy.min_length:
            errors.append(
                f"Password must be at least {self.policy.min_length} characters"
            )
        elif len(password) >= self.policy.min_length:
            score += 1
        
        if len(password) > self.policy.max_length:
            errors.append(
                f"Password must not exceed {self.policy.max_length} characters"
            )
        
        # Check uppercase
        if self.policy.require_uppercase:
            if not any(c.isupper() for c in password):
                errors.append("Password must contain uppercase letters")
                suggestions.append("Add uppercase letters (A-Z)")
            else:
                score += 1
        
        # Check lowercase
        if self.policy.require_lowercase:
            if not any(c.islower() for c in password):
                errors.append("Password must contain lowercase letters")
                suggestions.append("Add lowercase letters (a-z)")
            else:
                score += 1
        
        # Check digits
        if self.policy.require_digits:
            if not any(c.isdigit() for c in password):
                errors.append("Password must contain digits")
                suggestions.append("Add numbers (0-9)")
            else:
                score += 1
        
        # Check special characters
        if self.policy.require_special:
            if not any(c in self.policy.special_chars for c in password):
                errors.append("Password must contain special characters")
                suggestions.append(
                    f"Add special characters ({self.policy.special_chars[:10]}...)"
                )
            else:
                score += 1
        
        # Check consecutive characters
        if self._has_consecutive_chars(password):
            errors.append(
                f"Password has more than {self.policy.max_consecutive_chars} "
                "consecutive identical characters"
            )
        
        # Check common passwords
        if self.policy.disallow_common_passwords:
            if password.lower() in COMMON_PASSWORDS:
                errors.append("Password is too common")
                suggestions.append("Use a more unique password")
        
        # Check username in password
        if self.policy.disallow_username_in_password and username:
            if username.lower() in password.lower():
                errors.append("Password must not contain username")
        
        # Bonus points for extra length
        if len(password) >= 16:
            score += 1
        if len(password) >= 20:
            score += 1
        
        # Calculate strength
        strength = self._calculate_strength(score, len(password))
        
        return PasswordValidationResult(
            is_valid=len(errors) == 0,
            strength=strength,
            score=score,
            errors=errors,
            suggestions=suggestions,
        )
    
    def _has_consecutive_chars(self, password: str) -> bool:
        """Check for consecutive identical characters."""
        count = 1
        prev = None
        
        for char in password:
            if char == prev:
                count += 1
                if count > self.policy.max_consecutive_chars:
                    return True
            else:
                count = 1
            prev = char
        
        return False
    
    def _calculate_strength(self, score: int, length: int) -> PasswordStrength:
        """Calculate password strength."""
        if score <= 1:
            return PasswordStrength.VERY_WEAK
        elif score == 2:
            return PasswordStrength.WEAK
        elif score == 3 or (score == 4 and length < 14):
            return PasswordStrength.FAIR
        elif score <= 5:
            return PasswordStrength.STRONG
        else:
            return PasswordStrength.VERY_STRONG


class PasswordHasher:
    """Hashes and verifies passwords."""
    
    def __init__(self, config: Optional[HashConfig] = None):
        self.config = config or HashConfig()
    
    def hash(self, password: str) -> HashedPassword:
        """Hash a password."""
        # Generate salt
        salt = secrets.token_hex(self.config.salt_length)
        
        # Hash password
        hash_bytes = self._hash_password(
            password, salt, self.config.algorithm, self.config.iterations
        )
        
        return HashedPassword(
            hash=hash_bytes.hex(),
            salt=salt,
            algorithm=self.config.algorithm.value,
            iterations=self.config.iterations,
        )
    
    def verify(
        self,
        password: str,
        hashed: HashedPassword,
    ) -> bool:
        """Verify password against hash."""
        try:
            algorithm = HashAlgorithm(hashed.algorithm)
        except ValueError:
            return False
        
        # Hash password with same params
        hash_bytes = self._hash_password(
            password, hashed.salt, algorithm, hashed.iterations
        )
        
        # Timing-safe comparison
        return hmac.compare_digest(
            hash_bytes.hex(),
            hashed.hash,
        )
    
    def _hash_password(
        self,
        password: str,
        salt: str,
        algorithm: HashAlgorithm,
        iterations: int,
    ) -> bytes:
        """Hash password with algorithm."""
        if algorithm == HashAlgorithm.PBKDF2_SHA256:
            return hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt.encode(),
                iterations,
                dklen=self.config.hash_length,
            )
        elif algorithm == HashAlgorithm.PBKDF2_SHA512:
            return hashlib.pbkdf2_hmac(
                "sha512",
                password.encode(),
                salt.encode(),
                iterations,
                dklen=self.config.hash_length,
            )
        else:
            # Fallback to PBKDF2_SHA256
            return hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt.encode(),
                iterations,
                dklen=self.config.hash_length,
            )
    
    def needs_rehash(self, hashed: HashedPassword) -> bool:
        """Check if password needs rehashing."""
        return (
            hashed.algorithm != self.config.algorithm.value or
            hashed.iterations < self.config.iterations
        )


class PasswordGenerator:
    """Generates secure passwords."""
    
    def __init__(self, policy: Optional[PasswordPolicy] = None):
        self.policy = policy or PasswordPolicy()
    
    def generate(self, length: Optional[int] = None) -> str:
        """Generate a secure password."""
        length = length or self.policy.min_length
        length = max(length, self.policy.min_length)
        
        # Character sets
        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        lowercase = "abcdefghijklmnopqrstuvwxyz"
        digits = "0123456789"
        special = self.policy.special_chars
        
        # Ensure requirements
        password = []
        
        if self.policy.require_uppercase:
            password.append(secrets.choice(uppercase))
        if self.policy.require_lowercase:
            password.append(secrets.choice(lowercase))
        if self.policy.require_digits:
            password.append(secrets.choice(digits))
        if self.policy.require_special:
            password.append(secrets.choice(special))
        
        # Fill remaining
        all_chars = ""
        if self.policy.require_uppercase:
            all_chars += uppercase
        if self.policy.require_lowercase:
            all_chars += lowercase
        if self.policy.require_digits:
            all_chars += digits
        if self.policy.require_special:
            all_chars += special
        
        if not all_chars:
            all_chars = uppercase + lowercase + digits
        
        while len(password) < length:
            password.append(secrets.choice(all_chars))
        
        # Shuffle
        password_list = list(password)
        for i in range(len(password_list) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            password_list[i], password_list[j] = password_list[j], password_list[i]
        
        return "".join(password_list)
    
    def generate_passphrase(
        self,
        word_count: int = 4,
        separator: str = "-",
    ) -> str:
        """Generate a passphrase."""
        # Simple word list (in production, use a larger list)
        words = [
            "correct", "horse", "battery", "staple", "orange",
            "purple", "dragon", "castle", "forest", "river",
            "mountain", "ocean", "thunder", "lightning", "crystal",
            "silver", "golden", "ancient", "mystic", "shadow",
        ]
        
        selected = [secrets.choice(words) for _ in range(word_count)]
        return separator.join(selected)


class PasswordSecurityService:
    """Comprehensive password security service."""
    
    _instance: Optional["PasswordSecurityService"] = None
    
    def __init__(
        self,
        policy: Optional[PasswordPolicy] = None,
        hash_config: Optional[HashConfig] = None,
    ):
        self.policy = policy or PasswordPolicy()
        self.hash_config = hash_config or HashConfig()
        
        self.validator = PasswordValidator(self.policy)
        self.hasher = PasswordHasher(self.hash_config)
        self.generator = PasswordGenerator(self.policy)
        
        # Password history storage
        self._password_history: dict[str, list[str]] = {}
    
    @classmethod
    def get_instance(cls) -> "PasswordSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        policy: Optional[PasswordPolicy] = None,
        hash_config: Optional[HashConfig] = None,
    ) -> "PasswordSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(policy, hash_config)
        return cls._instance
    
    def validate(
        self,
        password: str,
        username: Optional[str] = None,
    ) -> PasswordValidationResult:
        """Validate password."""
        return self.validator.validate(password, username)
    
    def hash(self, password: str) -> str:
        """Hash password and return storable string."""
        hashed = self.hasher.hash(password)
        return hashed.to_string()
    
    def verify(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash."""
        try:
            hashed = HashedPassword.from_string(stored_hash)
            return self.hasher.verify(password, hashed)
        except ValueError:
            return False
    
    def needs_rehash(self, stored_hash: str) -> bool:
        """Check if password needs rehashing."""
        try:
            hashed = HashedPassword.from_string(stored_hash)
            return self.hasher.needs_rehash(hashed)
        except ValueError:
            return True
    
    def generate(self, length: Optional[int] = None) -> str:
        """Generate a secure password."""
        return self.generator.generate(length)
    
    def generate_passphrase(
        self,
        word_count: int = 4,
    ) -> str:
        """Generate a passphrase."""
        return self.generator.generate_passphrase(word_count)
    
    def check_history(
        self,
        user_id: str,
        password: str,
    ) -> bool:
        """Check if password was used before. Returns True if allowed."""
        history = self._password_history.get(user_id, [])
        
        for old_hash in history:
            if self.verify(password, old_hash):
                return False
        
        return True
    
    def add_to_history(
        self,
        user_id: str,
        stored_hash: str,
    ) -> None:
        """Add password hash to history."""
        if user_id not in self._password_history:
            self._password_history[user_id] = []
        
        history = self._password_history[user_id]
        history.insert(0, stored_hash)
        
        # Trim to max history
        while len(history) > self.policy.password_history_count:
            history.pop()
    
    def check_breach(self, password: str) -> bool:
        """
        Check if password appears in breaches.
        Returns True if password is safe (not breached).
        
        Note: In production, use Have I Been Pwned API.
        """
        # Simple check against common passwords
        return password.lower() not in COMMON_PASSWORDS


# Convenience functions
def get_password_service() -> PasswordSecurityService:
    """Get password service instance."""
    return PasswordSecurityService.get_instance()


def hash_password(password: str) -> str:
    """Hash a password."""
    return get_password_service().hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password."""
    return get_password_service().verify(password, stored_hash)


def validate_password(
    password: str,
    username: Optional[str] = None,
) -> PasswordValidationResult:
    """Validate a password."""
    return get_password_service().validate(password, username)
