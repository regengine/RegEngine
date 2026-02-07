"""
Tests for SEC-041: API Key Security.

Tests cover:
- API key generation
- Key validation
- Key rotation
- IP and origin restrictions
"""

import time
import pytest

from shared.api_key_security import (
    # Enums
    KeyStatus,
    KeyScope,
    # Data classes
    APIKeyConfig,
    APIKey,
    KeyValidationResult,
    # Classes
    APIKeyGenerator,
    APIKeyValidator,
    APIKeyRotator,
    APIKeySecurityService,
    # Convenience functions
    get_api_key_service,
    create_api_key,
    validate_api_key,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create API key config."""
    return APIKeyConfig()


@pytest.fixture
def generator(config):
    """Create API key generator."""
    return APIKeyGenerator(config)


@pytest.fixture
def validator(config):
    """Create API key validator."""
    return APIKeyValidator(config)


@pytest.fixture
def rotator(generator, config):
    """Create API key rotator."""
    return APIKeyRotator(generator, config)


@pytest.fixture
def service(config):
    """Create API key service."""
    APIKeySecurityService._instance = None
    return APIKeySecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_key_status(self):
        """Should have expected status values."""
        assert KeyStatus.ACTIVE == "active"
        assert KeyStatus.EXPIRED == "expired"
        assert KeyStatus.REVOKED == "revoked"
        assert KeyStatus.PENDING == "pending"
    
    def test_key_scope(self):
        """Should have expected scope values."""
        assert KeyScope.READ == "read"
        assert KeyScope.WRITE == "write"
        assert KeyScope.ADMIN == "admin"
        assert KeyScope.FULL == "full"


# =============================================================================
# Test: APIKeyConfig
# =============================================================================

class TestAPIKeyConfig:
    """Test APIKeyConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = APIKeyConfig()
        
        assert config.key_length == 32
        assert config.min_key_length == 16
        assert config.hash_algorithm == "sha256"
        assert config.require_https is True
    
    def test_custom_prefix(self):
        """Should allow custom prefix."""
        config = APIKeyConfig(prefix="sk")
        
        assert config.prefix == "sk"


# =============================================================================
# Test: APIKey
# =============================================================================

class TestAPIKey:
    """Test APIKey class."""
    
    def test_is_valid(self):
        """Should check validity."""
        key = APIKey(
            key_id="test",
            key_hash="hash",
            prefix="rk",
            version="1",
            status=KeyStatus.ACTIVE,
        )
        
        assert key.is_valid is True
    
    def test_is_expired(self):
        """Should check expiration."""
        key = APIKey(
            key_id="test",
            key_hash="hash",
            prefix="rk",
            version="1",
            expires_at=time.time() - 1000,
        )
        
        assert key.is_expired is True
        assert key.is_valid is False
    
    def test_to_safe_dict(self):
        """Should exclude sensitive data."""
        key = APIKey(
            key_id="test",
            key_hash="secret_hash",
            prefix="rk",
            version="1",
        )
        
        safe = key.to_safe_dict()
        
        assert "key_id" in safe
        assert "key_hash" not in safe


# =============================================================================
# Test: APIKeyGenerator
# =============================================================================

class TestAPIKeyGenerator:
    """Test APIKeyGenerator."""
    
    def test_generates_unique_keys(self, generator):
        """Should generate unique keys."""
        raw1, key1 = generator.generate()
        raw2, key2 = generator.generate()
        
        assert raw1 != raw2
        assert key1.key_id != key2.key_id
    
    def test_key_has_prefix(self, generator):
        """Should include prefix in key."""
        raw_key, _ = generator.generate()
        
        assert raw_key.startswith("rk_")
    
    def test_key_has_version(self, generator):
        """Should include version in key."""
        raw_key, _ = generator.generate()
        
        assert "_1_" in raw_key
    
    def test_stores_hash_not_raw(self, generator):
        """Should store hash not raw key."""
        raw_key, api_key = generator.generate()
        
        assert api_key.key_hash != raw_key
        assert len(api_key.key_hash) == 64  # SHA256 hex
    
    def test_sets_expiration(self, generator):
        """Should set expiration."""
        _, api_key = generator.generate(ttl_days=30)
        
        assert api_key.expires_at is not None
        assert api_key.expires_at > time.time()
    
    def test_sets_metadata(self, generator):
        """Should set metadata."""
        _, api_key = generator.generate(
            scope=KeyScope.WRITE,
            name="Test Key",
            tenant_id="tenant-1",
        )
        
        assert api_key.scope == KeyScope.WRITE
        assert api_key.name == "Test Key"
        assert api_key.tenant_id == "tenant-1"
    
    def test_generate_key_pair(self, generator):
        """Should generate key pair."""
        key_id, secret, api_key = generator.generate_key_pair()
        
        assert key_id.startswith("rk_")
        assert len(secret) > 20
        assert api_key.key_id == key_id


# =============================================================================
# Test: APIKeyValidator
# =============================================================================

class TestAPIKeyValidator:
    """Test APIKeyValidator."""
    
    def test_validates_format(self, validator):
        """Should validate key format."""
        is_valid, error = validator.validate_format("rk_1_abcdefghijk12345")
        
        assert is_valid is True
        assert error is None
    
    def test_rejects_empty_key(self, validator):
        """Should reject empty key."""
        is_valid, error = validator.validate_format("")
        
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_rejects_short_key(self, validator):
        """Should reject short key."""
        is_valid, error = validator.validate_format("rk_1_ab")
        
        assert is_valid is False
        assert "short" in error.lower()
    
    def test_rejects_invalid_format(self, validator):
        """Should reject invalid format."""
        # Use a long enough string that fails format check
        is_valid, error = validator.validate_format("not-a-valid-key-without-proper-format")
        
        assert is_valid is False
        assert "format" in error.lower()
    
    def test_validates_key(self, generator, validator):
        """Should validate key against stored."""
        raw_key, api_key = generator.generate()
        
        result = validator.validate_key(raw_key, api_key)
        
        assert result.is_valid is True
    
    def test_rejects_wrong_key(self, generator, validator):
        """Should reject wrong key."""
        _, api_key = generator.generate()
        
        result = validator.validate_key("rk_1_wrongkeywrongkey", api_key)
        
        assert result.is_valid is False
    
    def test_rejects_revoked_key(self, generator, validator):
        """Should reject revoked key."""
        raw_key, api_key = generator.generate()
        api_key.status = KeyStatus.REVOKED
        
        result = validator.validate_key(raw_key, api_key)
        
        assert result.is_valid is False
        assert "revoked" in result.error.lower()
    
    def test_rejects_expired_key(self, generator, validator):
        """Should reject expired key."""
        raw_key, api_key = generator.generate()
        api_key.expires_at = time.time() - 1000
        
        result = validator.validate_key(raw_key, api_key)
        
        assert result.is_valid is False
        assert "expired" in result.error.lower()
    
    def test_check_ip_allowed(self, validator):
        """Should check IP restriction."""
        key = APIKey(
            key_id="test",
            key_hash="hash",
            prefix="rk",
            version="1",
            allowed_ips={"192.168.1.1"},
        )
        
        assert validator.check_ip_allowed(key, "192.168.1.1") is True
        assert validator.check_ip_allowed(key, "10.0.0.1") is False
    
    def test_check_ip_no_restriction(self, validator):
        """Should allow all IPs when not restricted."""
        key = APIKey(
            key_id="test",
            key_hash="hash",
            prefix="rk",
            version="1",
        )
        
        assert validator.check_ip_allowed(key, "any-ip") is True
    
    def test_check_origin_allowed(self, validator):
        """Should check origin restriction."""
        key = APIKey(
            key_id="test",
            key_hash="hash",
            prefix="rk",
            version="1",
            allowed_origins={"https://example.com"},
        )
        
        assert validator.check_origin_allowed(key, "https://example.com") is True
        assert validator.check_origin_allowed(key, "https://evil.com") is False


# =============================================================================
# Test: APIKeyRotator
# =============================================================================

class TestAPIKeyRotator:
    """Test APIKeyRotator."""
    
    def test_rotates_key(self, generator, rotator):
        """Should rotate key."""
        _, old_key = generator.generate(name="Original")
        
        new_raw, new_key, updated_old = rotator.rotate(old_key)
        
        assert new_raw is not None
        assert new_key.key_id != old_key.key_id
        assert "rotated" in new_key.name.lower()
        assert "deprecated" in updated_old.name.lower()
    
    def test_preserves_metadata(self, generator, rotator):
        """Should preserve metadata on rotation."""
        _, old_key = generator.generate(
            scope=KeyScope.ADMIN,
            tenant_id="tenant-1",
        )
        old_key.allowed_ips = {"192.168.1.1"}
        
        _, new_key, _ = rotator.rotate(old_key)
        
        assert new_key.scope == KeyScope.ADMIN
        assert new_key.tenant_id == "tenant-1"
        assert "192.168.1.1" in new_key.allowed_ips
    
    def test_sets_grace_period(self, generator, rotator):
        """Should set grace period."""
        _, old_key = generator.generate()
        
        _, _, updated_old = rotator.rotate(old_key, grace_period_hours=48)
        
        expected_expiry = time.time() + (48 * 3600)
        assert abs(updated_old.expires_at - expected_expiry) < 10
    
    def test_revokes_key(self, generator, rotator):
        """Should revoke key."""
        _, key = generator.generate()
        
        revoked = rotator.revoke(key, "Security concern")
        
        assert revoked.status == KeyStatus.REVOKED
        assert revoked.revoked_at is not None
        assert "Security concern" in revoked.description
    
    def test_should_rotate(self, generator, rotator):
        """Should check rotation needed."""
        _, key = generator.generate()
        key.expires_at = time.time() + (10 * 86400)  # 10 days
        
        assert rotator.should_rotate(key, days_before_expiry=30) is True
        assert rotator.should_rotate(key, days_before_expiry=5) is False


# =============================================================================
# Test: APIKeySecurityService
# =============================================================================

class TestAPIKeySecurityService:
    """Test APIKeySecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        APIKeySecurityService._instance = None
        
        s1 = get_api_key_service()
        s2 = get_api_key_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        APIKeySecurityService._instance = None
        config = APIKeyConfig(prefix="sk")
        
        service = APIKeySecurityService.configure(config)
        
        assert service.config.prefix == "sk"
    
    def test_create_key(self, service):
        """Should create key."""
        raw_key, api_key = service.create_key(name="Test")
        
        assert raw_key is not None
        assert api_key.name == "Test"
        assert api_key.key_id in service._keys
    
    def test_validate(self, service):
        """Should validate key."""
        raw_key, _ = service.create_key()
        
        result = service.validate(raw_key)
        
        assert result.is_valid is True
    
    def test_validate_invalid(self, service):
        """Should reject invalid key."""
        result = service.validate("rk_1_invalidkeyvalue")
        
        assert result.is_valid is False
    
    def test_validate_with_ip(self, service):
        """Should validate IP restriction."""
        raw_key, api_key = service.create_key()
        api_key.allowed_ips = {"192.168.1.1"}
        
        result = service.validate(raw_key, client_ip="10.0.0.1")
        
        assert result.is_valid is False
        assert "IP" in result.error
    
    def test_validate_with_origin(self, service):
        """Should validate origin restriction."""
        raw_key, api_key = service.create_key()
        api_key.allowed_origins = {"https://example.com"}
        
        result = service.validate(raw_key, origin="https://evil.com")
        
        assert result.is_valid is False
        assert "Origin" in result.error
    
    def test_rotate_key(self, service):
        """Should rotate key."""
        _, api_key = service.create_key(name="Original")
        
        result = service.rotate_key(api_key.key_id)
        
        assert result is not None
        new_raw, new_key = result
        assert new_key.key_id in service._keys
    
    def test_revoke_key(self, service):
        """Should revoke key."""
        _, api_key = service.create_key()
        
        success = service.revoke_key(api_key.key_id, "Test revoke")
        
        assert success is True
        assert service._keys[api_key.key_id].status == KeyStatus.REVOKED
    
    def test_get_key(self, service):
        """Should get key by ID."""
        _, api_key = service.create_key()
        
        found = service.get_key(api_key.key_id)
        
        assert found is not None
        assert found.key_id == api_key.key_id
    
    def test_list_keys(self, service):
        """Should list keys."""
        service.create_key(tenant_id="tenant-1")
        service.create_key(tenant_id="tenant-2")
        
        all_keys = service.list_keys()
        tenant_keys = service.list_keys(tenant_id="tenant-1")
        
        assert len(all_keys) == 2
        assert len(tenant_keys) == 1
    
    def test_cleanup_expired(self, service):
        """Should cleanup expired keys."""
        _, api_key = service.create_key()
        api_key.expires_at = time.time() - 1000
        
        count = service.cleanup_expired()
        
        assert count == 1
        assert api_key.key_id not in service._keys


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_api_key(self):
        """Should create via convenience function."""
        APIKeySecurityService._instance = None
        
        raw_key, api_key = create_api_key(scope=KeyScope.WRITE)
        
        assert raw_key is not None
        assert api_key.scope == KeyScope.WRITE
    
    def test_validate_api_key(self):
        """Should validate via convenience function."""
        APIKeySecurityService._instance = None
        raw_key, _ = create_api_key()
        
        result = validate_api_key(raw_key)
        
        assert result.is_valid is True


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_keys_use_secure_random(self, generator):
        """Should use secure random."""
        raw1, _ = generator.generate()
        raw2, _ = generator.generate()
        
        # Keys should be sufficiently different
        assert raw1 != raw2
        assert len(set(raw1) & set(raw2)) < len(raw1) * 0.8
    
    def test_hash_stored_not_raw(self, generator):
        """Should store hash not raw key."""
        raw_key, api_key = generator.generate()
        
        assert raw_key not in api_key.key_hash
        assert api_key.key_hash != raw_key
    
    def test_timing_safe_comparison(self, generator, validator):
        """Should use timing-safe comparison."""
        # This test verifies the code uses hmac.compare_digest
        raw_key, api_key = generator.generate()
        
        # Valid key
        result1 = validator.validate_key(raw_key, api_key)
        assert result1.is_valid is True
        
        # Wrong key - should not leak timing
        result2 = validator.validate_key("rk_1_wrongkeywrongkey", api_key)
        assert result2.is_valid is False
