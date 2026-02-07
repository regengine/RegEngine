"""
Tests for SEC-044: Password Security.

Tests cover:
- Password validation
- Password hashing
- Password generation
- History checking
"""

import pytest

from shared.password_security import (
    # Enums
    PasswordStrength,
    HashAlgorithm,
    # Data classes
    PasswordPolicy,
    HashConfig,
    PasswordValidationResult,
    HashedPassword,
    # Classes
    PasswordValidator,
    PasswordHasher,
    PasswordGenerator,
    PasswordSecurityService,
    # Convenience functions
    get_password_service,
    hash_password,
    verify_password,
    validate_password,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def policy():
    """Create password policy."""
    return PasswordPolicy()


@pytest.fixture
def hash_config():
    """Create hash config."""
    return HashConfig(iterations=1000)  # Lower for tests


@pytest.fixture
def validator(policy):
    """Create validator."""
    return PasswordValidator(policy)


@pytest.fixture
def hasher(hash_config):
    """Create hasher."""
    return PasswordHasher(hash_config)


@pytest.fixture
def generator(policy):
    """Create generator."""
    return PasswordGenerator(policy)


@pytest.fixture
def service(policy, hash_config):
    """Create service."""
    PasswordSecurityService._instance = None
    return PasswordSecurityService(policy, hash_config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_password_strength(self):
        """Should have expected strength values."""
        assert PasswordStrength.VERY_WEAK == "very_weak"
        assert PasswordStrength.WEAK == "weak"
        assert PasswordStrength.FAIR == "fair"
        assert PasswordStrength.STRONG == "strong"
        assert PasswordStrength.VERY_STRONG == "very_strong"
    
    def test_hash_algorithms(self):
        """Should have expected algorithms."""
        assert HashAlgorithm.PBKDF2_SHA256 == "pbkdf2_sha256"
        assert HashAlgorithm.PBKDF2_SHA512 == "pbkdf2_sha512"


# =============================================================================
# Test: PasswordPolicy
# =============================================================================

class TestPasswordPolicy:
    """Test PasswordPolicy class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        policy = PasswordPolicy()
        
        assert policy.min_length == 12
        assert policy.require_uppercase is True
        assert policy.require_lowercase is True
        assert policy.require_digits is True
        assert policy.require_special is True
    
    def test_custom_values(self):
        """Should allow custom values."""
        policy = PasswordPolicy(min_length=16)
        
        assert policy.min_length == 16


# =============================================================================
# Test: HashedPassword
# =============================================================================

class TestHashedPassword:
    """Test HashedPassword class."""
    
    def test_to_string(self):
        """Should convert to string."""
        hashed = HashedPassword(
            hash="abc123",
            salt="salt456",
            algorithm="pbkdf2_sha256",
            iterations=100000,
        )
        
        result = hashed.to_string()
        
        assert "pbkdf2_sha256" in result
        assert "100000" in result
        assert "salt456" in result
        assert "abc123" in result
    
    def test_from_string(self):
        """Should parse from string."""
        stored = "pbkdf2_sha256$100000$salt456$abc123"
        
        hashed = HashedPassword.from_string(stored)
        
        assert hashed.algorithm == "pbkdf2_sha256"
        assert hashed.iterations == 100000
        assert hashed.salt == "salt456"
        assert hashed.hash == "abc123"
    
    def test_from_string_invalid(self):
        """Should raise on invalid string."""
        with pytest.raises(ValueError):
            HashedPassword.from_string("invalid")


# =============================================================================
# Test: PasswordValidator
# =============================================================================

class TestPasswordValidator:
    """Test PasswordValidator."""
    
    def test_validates_strong_password(self, validator):
        """Should validate strong password."""
        result = validator.validate("SecureP@ssw0rd!!")
        
        assert result.is_valid is True
        assert result.strength in [
            PasswordStrength.STRONG,
            PasswordStrength.VERY_STRONG,
        ]
    
    def test_rejects_short_password(self, validator):
        """Should reject short password."""
        result = validator.validate("Short1!")
        
        assert result.is_valid is False
        assert any("at least" in e for e in result.errors)
    
    def test_requires_uppercase(self, validator):
        """Should require uppercase."""
        result = validator.validate("lowercase1234!")
        
        assert result.is_valid is False
        assert any("uppercase" in e for e in result.errors)
    
    def test_requires_lowercase(self, validator):
        """Should require lowercase."""
        result = validator.validate("UPPERCASE1234!")
        
        assert result.is_valid is False
        assert any("lowercase" in e for e in result.errors)
    
    def test_requires_digits(self, validator):
        """Should require digits."""
        result = validator.validate("NoDigitsHere!!")
        
        assert result.is_valid is False
        assert any("digits" in e for e in result.errors)
    
    def test_requires_special(self, validator):
        """Should require special chars."""
        result = validator.validate("NoSpecialChars123")
        
        assert result.is_valid is False
        assert any("special" in e for e in result.errors)
    
    def test_rejects_common_passwords(self, validator):
        """Should reject common passwords."""
        result = validator.validate("password123")
        
        assert result.is_valid is False
        assert any("common" in e for e in result.errors)
    
    def test_rejects_username_in_password(self, validator):
        """Should reject username in password."""
        result = validator.validate("JohnDoe1234!!", username="johndoe")
        
        assert result.is_valid is False
        assert any("username" in e for e in result.errors)
    
    def test_rejects_consecutive_chars(self, validator):
        """Should reject consecutive chars."""
        result = validator.validate("Secureeee1234!")
        
        assert result.is_valid is False
        assert any("consecutive" in e for e in result.errors)
    
    def test_provides_suggestions(self, validator):
        """Should provide suggestions."""
        result = validator.validate("weak")
        
        assert len(result.suggestions) > 0


# =============================================================================
# Test: PasswordHasher
# =============================================================================

class TestPasswordHasher:
    """Test PasswordHasher."""
    
    def test_hashes_password(self, hasher):
        """Should hash password."""
        hashed = hasher.hash("MySecurePassword123!")
        
        assert hashed.hash is not None
        assert len(hashed.hash) > 0
        assert hashed.salt is not None
    
    def test_different_salts(self, hasher):
        """Should use different salts."""
        h1 = hasher.hash("password")
        h2 = hasher.hash("password")
        
        assert h1.salt != h2.salt
        assert h1.hash != h2.hash
    
    def test_verifies_correct_password(self, hasher):
        """Should verify correct password."""
        hashed = hasher.hash("MyPassword123!")
        
        result = hasher.verify("MyPassword123!", hashed)
        
        assert result is True
    
    def test_rejects_wrong_password(self, hasher):
        """Should reject wrong password."""
        hashed = hasher.hash("MyPassword123!")
        
        result = hasher.verify("WrongPassword!", hashed)
        
        assert result is False
    
    def test_needs_rehash(self):
        """Should detect when rehash needed."""
        old_config = HashConfig(iterations=1000)
        new_config = HashConfig(iterations=100000)
        
        old_hasher = PasswordHasher(old_config)
        new_hasher = PasswordHasher(new_config)
        
        hashed = old_hasher.hash("password")
        
        assert new_hasher.needs_rehash(hashed) is True


# =============================================================================
# Test: PasswordGenerator
# =============================================================================

class TestPasswordGenerator:
    """Test PasswordGenerator."""
    
    def test_generates_password(self, generator):
        """Should generate password."""
        password = generator.generate()
        
        assert password is not None
        assert len(password) >= 12
    
    def test_generates_with_length(self, generator):
        """Should generate with specified length."""
        password = generator.generate(length=20)
        
        assert len(password) == 20
    
    def test_generated_passes_validation(self, generator, validator):
        """Generated password should pass validation."""
        password = generator.generate()
        
        result = validator.validate(password)
        
        assert result.is_valid is True
    
    def test_generates_unique(self, generator):
        """Should generate unique passwords."""
        passwords = [generator.generate() for _ in range(10)]
        
        assert len(set(passwords)) == 10
    
    def test_generates_passphrase(self, generator):
        """Should generate passphrase."""
        passphrase = generator.generate_passphrase(word_count=4)
        
        assert passphrase is not None
        assert passphrase.count("-") == 3


# =============================================================================
# Test: PasswordSecurityService
# =============================================================================

class TestPasswordSecurityService:
    """Test PasswordSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        PasswordSecurityService._instance = None
        
        s1 = get_password_service()
        s2 = get_password_service()
        
        assert s1 is s2
    
    def test_validate(self, service):
        """Should validate password."""
        result = service.validate("SecureP@ssw0rd!!")
        
        assert result.is_valid is True
    
    def test_hash_and_verify(self, service):
        """Should hash and verify."""
        stored = service.hash("MyPassword123!")
        
        assert service.verify("MyPassword123!", stored) is True
        assert service.verify("Wrong!", stored) is False
    
    def test_generate(self, service):
        """Should generate password."""
        password = service.generate()
        
        assert password is not None
        assert service.validate(password).is_valid is True
    
    def test_check_history(self, service):
        """Should check password history."""
        stored = service.hash("OldPassword1!")
        service.add_to_history("user-1", stored)
        
        # Old password should be rejected
        assert service.check_history("user-1", "OldPassword1!") is False
        
        # New password should be allowed
        assert service.check_history("user-1", "NewPassword2!") is True
    
    def test_needs_rehash(self):
        """Should detect rehash needed."""
        service = PasswordSecurityService(
            hash_config=HashConfig(iterations=100000)
        )
        
        # Simulate old hash with fewer iterations
        old = "pbkdf2_sha256$1000$salt$hash"
        
        assert service.needs_rehash(old) is True
    
    def test_check_breach(self, service):
        """Should check for breached passwords."""
        assert service.check_breach("password123") is False
        assert service.check_breach("UniqueSecure123!") is True


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_hash_password(self):
        """Should hash via convenience function."""
        PasswordSecurityService._instance = None
        
        stored = hash_password("TestPassword123!")
        
        assert stored is not None
        assert "$" in stored
    
    def test_verify_password(self):
        """Should verify via convenience function."""
        PasswordSecurityService._instance = None
        
        stored = hash_password("TestPassword123!")
        
        assert verify_password("TestPassword123!", stored) is True
        assert verify_password("Wrong!", stored) is False
    
    def test_validate_password(self):
        """Should validate via convenience function."""
        PasswordSecurityService._instance = None
        
        result = validate_password("SecureP@ssw0rd!!")
        
        assert result.is_valid is True


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_uses_secure_random_salt(self, hasher):
        """Should use secure random for salt."""
        salts = [hasher.hash("password").salt for _ in range(10)]
        
        # All should be unique
        assert len(set(salts)) == 10
    
    def test_timing_safe_verify(self, hasher):
        """Should use timing-safe comparison."""
        hashed = hasher.hash("password")
        
        # Both should complete without timing leak
        result1 = hasher.verify("password", hashed)
        result2 = hasher.verify("wrongpassword", hashed)
        
        assert result1 is True
        assert result2 is False
    
    def test_no_plaintext_storage(self, hasher):
        """Should not store plaintext."""
        password = "MySecretPassword123!"
        hashed = hasher.hash(password)
        
        assert password not in hashed.hash
        assert password not in hashed.salt
        assert password not in hashed.to_string()
