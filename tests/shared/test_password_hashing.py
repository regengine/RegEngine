"""
Tests for SEC-023: Secure Password Hashing.

Tests cover:
- Password strength analysis
- Argon2 hashing
- bcrypt hashing
- PBKDF2 hashing
- Hash verification
- Password generation
"""

import pytest
from typing import Tuple

from shared.password_hashing import (
    # Enums
    HashAlgorithm,
    PasswordStrength,
    # Exceptions
    PasswordHashError,
    WeakPasswordError,
    # Data classes
    PasswordPolicy,
    PasswordStrengthResult,
    HashedPassword,
    # Analyzer
    PasswordStrengthAnalyzer,
    # Hashers
    Argon2Hasher,
    BcryptHasher,
    PBKDF2Hasher,
    # Service
    PasswordService,
    # Functions
    get_password_service,
    hash_password,
    verify_password,
    analyze_password_strength,
    generate_secure_password,
    ARGON2_AVAILABLE,
    BCRYPT_AVAILABLE,
    CRYPTOGRAPHY_AVAILABLE,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def policy():
    """Create test password policy."""
    return PasswordPolicy(
        min_length=8,
        max_length=128,
        require_uppercase=True,
        require_lowercase=True,
        require_digits=True,
        require_special=True,
    )


@pytest.fixture
def analyzer(policy):
    """Create test analyzer."""
    return PasswordStrengthAnalyzer(policy)


@pytest.fixture
def service():
    """Create test password service."""
    return PasswordService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_hash_algorithm(self):
        """Should have expected algorithms."""
        assert HashAlgorithm.ARGON2ID == "argon2id"
        assert HashAlgorithm.BCRYPT == "bcrypt"
        assert HashAlgorithm.PBKDF2_SHA256 == "pbkdf2-sha256"
    
    def test_password_strength(self):
        """Should have expected strength levels."""
        assert PasswordStrength.VERY_WEAK == "very_weak"
        assert PasswordStrength.STRONG == "strong"
        assert PasswordStrength.VERY_STRONG == "very_strong"


# =============================================================================
# Test: Password Policy
# =============================================================================

class TestPasswordPolicy:
    """Test PasswordPolicy."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        policy = PasswordPolicy()
        
        assert policy.min_length >= 12
        assert policy.require_uppercase is True
        assert policy.require_special is True


# =============================================================================
# Test: Password Strength Analyzer
# =============================================================================

class TestPasswordStrengthAnalyzer:
    """Test PasswordStrengthAnalyzer."""
    
    def test_weak_password(self, analyzer):
        """Should detect weak password."""
        result = analyzer.analyze("password")
        
        assert result.strength in {PasswordStrength.VERY_WEAK, PasswordStrength.WEAK}
        assert result.meets_policy is False
        assert len(result.issues) > 0
    
    def test_common_password(self, analyzer):
        """Should detect common password."""
        result = analyzer.analyze("password123")
        
        assert "too common" in str(result.issues).lower()
    
    def test_short_password(self, analyzer):
        """Should require minimum length."""
        result = analyzer.analyze("Ab1!")
        
        assert result.meets_policy is False
        assert any("characters" in issue for issue in result.issues)
    
    def test_missing_uppercase(self, analyzer):
        """Should require uppercase."""
        result = analyzer.analyze("abcd1234!@#$")
        
        assert result.meets_policy is False
        assert any("uppercase" in issue.lower() for issue in result.issues)
    
    def test_missing_lowercase(self, analyzer):
        """Should require lowercase."""
        result = analyzer.analyze("ABCD1234!@#$")
        
        assert result.meets_policy is False
        assert any("lowercase" in issue.lower() for issue in result.issues)
    
    def test_missing_digits(self, analyzer):
        """Should require digits."""
        result = analyzer.analyze("AbcdEfgh!@#$")
        
        assert result.meets_policy is False
        assert any("digit" in issue.lower() for issue in result.issues)
    
    def test_missing_special(self, analyzer):
        """Should require special characters."""
        result = analyzer.analyze("AbcdEfgh1234")
        
        assert result.meets_policy is False
        assert any("special" in issue.lower() for issue in result.issues)
    
    def test_strong_password(self, analyzer):
        """Should accept strong password."""
        result = analyzer.analyze("MyStr0ng!Pass#2024")
        
        assert result.meets_policy is True
        assert result.strength in {PasswordStrength.STRONG, PasswordStrength.VERY_STRONG}
    
    def test_keyboard_pattern_detection(self, analyzer):
        """Should detect keyboard patterns."""
        result = analyzer.analyze("Qwerty12345!")
        
        assert any("pattern" in issue.lower() for issue in result.issues)
    
    def test_repeated_characters(self, analyzer):
        """Should detect repeated characters."""
        result = analyzer.analyze("Aaaaa12345!@")
        
        assert any("repeated" in issue.lower() or "pattern" in issue.lower() 
                   for issue in result.issues)
    
    def test_score_calculation(self, analyzer):
        """Should calculate meaningful score."""
        weak = analyzer.analyze("abc")
        strong = analyzer.analyze("MyV3ryStr0ng!P@ssw0rd")
        
        assert weak.score < strong.score
    
    def test_to_dict(self, analyzer):
        """Should convert result to dictionary."""
        result = analyzer.analyze("TestPassword1!")
        data = result.to_dict()
        
        assert "strength" in data
        assert "score" in data
        assert "issues" in data


# =============================================================================
# Test: Argon2 Hasher
# =============================================================================

@pytest.mark.skipif(not ARGON2_AVAILABLE, reason="argon2-cffi not installed")
class TestArgon2Hasher:
    """Test Argon2Hasher."""
    
    def test_hash_password(self):
        """Should hash password with Argon2."""
        hasher = Argon2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        
        assert hashed.startswith("$argon2id$")
        assert hashed != password
    
    def test_verify_correct_password(self):
        """Should verify correct password."""
        hasher = Argon2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify(password, hashed)
        
        assert result is True
    
    def test_verify_wrong_password(self):
        """Should reject wrong password."""
        hasher = Argon2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify("WrongPassword!", hashed)
        
        assert result is False
    
    def test_unique_hashes(self):
        """Should produce different hashes for same password."""
        hasher = Argon2Hasher()
        password = "TestPassword123!"
        
        hash1 = hasher.hash(password)
        hash2 = hasher.hash(password)
        
        assert hash1 != hash2  # Different salts
    
    def test_needs_rehash(self):
        """Should detect when rehash needed."""
        # Create hasher with low parameters
        weak_hasher = Argon2Hasher(time_cost=1, memory_cost=1024)
        strong_hasher = Argon2Hasher(time_cost=3, memory_cost=65536)
        
        weak_hash = weak_hasher.hash("password")
        
        # Strong hasher should want to rehash weak hash
        assert strong_hasher.needs_rehash(weak_hash) is True


# =============================================================================
# Test: bcrypt Hasher
# =============================================================================

@pytest.mark.skipif(not BCRYPT_AVAILABLE, reason="bcrypt not installed")
class TestBcryptHasher:
    """Test BcryptHasher."""
    
    def test_hash_password(self):
        """Should hash password with bcrypt."""
        hasher = BcryptHasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    
    def test_verify_correct_password(self):
        """Should verify correct password."""
        hasher = BcryptHasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify(password, hashed)
        
        assert result is True
    
    def test_verify_wrong_password(self):
        """Should reject wrong password."""
        hasher = BcryptHasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify("WrongPassword!", hashed)
        
        assert result is False
    
    def test_needs_rehash(self):
        """Should detect when rounds need upgrade."""
        weak_hasher = BcryptHasher(rounds=4)
        strong_hasher = BcryptHasher(rounds=12)
        
        weak_hash = weak_hasher.hash("password")
        
        assert strong_hasher.needs_rehash(weak_hash) is True


# =============================================================================
# Test: PBKDF2 Hasher
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not installed")
class TestPBKDF2Hasher:
    """Test PBKDF2Hasher."""
    
    def test_hash_password(self):
        """Should hash password with PBKDF2."""
        hasher = PBKDF2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_verify_correct_password(self):
        """Should verify correct password."""
        hasher = PBKDF2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify(password, hashed)
        
        assert result is True
    
    def test_verify_wrong_password(self):
        """Should reject wrong password."""
        hasher = PBKDF2Hasher()
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        result = hasher.verify("WrongPassword!", hashed)
        
        assert result is False
    
    def test_sha512_variant(self):
        """Should support SHA-512."""
        hasher = PBKDF2Hasher(algorithm="sha512")
        password = "TestPassword123!"
        
        hashed = hasher.hash(password)
        
        assert hashed.startswith("$pbkdf2-sha512$")
        assert hasher.verify(password, hashed) is True


# =============================================================================
# Test: Password Service
# =============================================================================

class TestPasswordService:
    """Test PasswordService."""
    
    def test_analyze_strength(self, service):
        """Should analyze password strength."""
        result = service.analyze_strength("WeakPwd1!")
        
        assert isinstance(result, PasswordStrengthResult)
    
    def test_validate_password_weak(self, service):
        """Should reject weak password."""
        with pytest.raises(WeakPasswordError) as exc_info:
            service.validate_password("weak")
        
        assert len(exc_info.value.issues) > 0
    
    def test_validate_password_strong(self, service):
        """Should accept strong password."""
        result = service.validate_password("MyStr0ng!Pass#2024")
        
        assert result.meets_policy is True
    
    @pytest.mark.skipif(not ARGON2_AVAILABLE, reason="argon2 not available")
    def test_hash_password_argon2(self, service):
        """Should hash with Argon2."""
        hashed = service.hash_password(
            "MyStr0ng!Pass#2024",
            algorithm=HashAlgorithm.ARGON2ID,
        )
        
        assert hashed.algorithm == HashAlgorithm.ARGON2ID
        assert hashed.hash.startswith("$argon2id$")
    
    @pytest.mark.skipif(not BCRYPT_AVAILABLE, reason="bcrypt not available")
    def test_hash_password_bcrypt(self, service):
        """Should hash with bcrypt."""
        hashed = service.hash_password(
            "MyStr0ng!Pass#2024",
            algorithm=HashAlgorithm.BCRYPT,
        )
        
        assert hashed.algorithm == HashAlgorithm.BCRYPT
    
    def test_verify_password(self, service):
        """Should verify password."""
        password = "MyStr0ng!Pass#2024"
        # Use PBKDF2 which is always available
        hashed = service.hash_password(password, algorithm=HashAlgorithm.PBKDF2_SHA256)
        
        is_valid, needs_rehash = service.verify_password(password, hashed)
        
        assert is_valid is True
    
    def test_verify_wrong_password(self, service):
        """Should reject wrong password."""
        # Use PBKDF2 which is always available
        hashed = service.hash_password("MyStr0ng!Pass#2024", algorithm=HashAlgorithm.PBKDF2_SHA256)
        
        is_valid, _ = service.verify_password("WrongPassword1!", hashed)
        
        assert is_valid is False
    
    def test_verify_and_rehash(self, service):
        """Should rehash when needed."""
        password = "MyStr0ng!Pass#2024"
        
        # Create hash with non-default algorithm
        if BCRYPT_AVAILABLE:
            hashed = service.hash_password(password, algorithm=HashAlgorithm.BCRYPT)
            
            # Service should suggest rehash to default algorithm
            is_valid, new_hash = service.verify_and_rehash(password, hashed)
            
            assert is_valid is True
            # Will return new hash if default algo is different
            if service._default_algorithm != HashAlgorithm.BCRYPT:
                assert new_hash is not None
    
    def test_generate_password(self, service):
        """Should generate secure password."""
        password = service.generate_password(length=20)
        
        assert len(password) == 20
        
        # Should be strong
        result = service.analyze_strength(password)
        assert result.meets_policy is True
    
    def test_generate_password_customization(self, service):
        """Should respect generation options."""
        password = service.generate_password(
            length=16,
            include_upper=True,
            include_lower=True,
            include_digits=True,
            include_special=False,
        )
        
        assert len(password) == 16
        # Should have no special chars
        assert not any(c in "!@#$%^&*" for c in password)


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_password_service(self):
        """Should return singleton."""
        service1 = get_password_service()
        service2 = get_password_service()
        assert service1 is service2
    
    def test_hash_password_function(self):
        """Should hash via convenience function."""
        PasswordService.configure()
        
        # Use PBKDF2 which is always available
        hashed = hash_password("MyStr0ng!Pass#2024", algorithm=HashAlgorithm.PBKDF2_SHA256)
        
        assert hashed.hash is not None
    
    def test_verify_password_function(self):
        """Should verify via convenience function."""
        PasswordService.configure()
        
        # Use PBKDF2 which is always available
        hashed = hash_password("MyStr0ng!Pass#2024", algorithm=HashAlgorithm.PBKDF2_SHA256)
        is_valid, _ = verify_password("MyStr0ng!Pass#2024", hashed)
        
        assert is_valid is True
    
    def test_analyze_password_strength_function(self):
        """Should analyze via convenience function."""
        PasswordService.configure()
        
        result = analyze_password_strength("TestPassword1!")
        
        assert isinstance(result, PasswordStrengthResult)
    
    def test_generate_secure_password_function(self):
        """Should generate via convenience function."""
        PasswordService.configure()
        
        password = generate_secure_password(20)
        
        assert len(password) == 20
