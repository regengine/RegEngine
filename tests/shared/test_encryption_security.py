"""
Tests for SEC-045: Encryption Security.

Tests cover:
- AES-GCM encryption/decryption
- Key management
- Password-based encryption
- Key rotation
"""

import pytest

from shared.encryption_security import (
    # Enums
    EncryptionAlgorithm,
    KeyType,
    # Data classes
    EncryptionConfig,
    EncryptedData,
    EncryptionKey,
    # Classes
    AESGCMCipher,
    KeyManager,
    EncryptionService,
    # Convenience functions
    get_encryption_service,
    encrypt,
    decrypt,
    encrypt_string,
    decrypt_string,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create encryption config."""
    return EncryptionConfig()


@pytest.fixture
def key_manager(config):
    """Create key manager."""
    return KeyManager(config)


@pytest.fixture
def service(config):
    """Create encryption service."""
    EncryptionService._instance = None
    return EncryptionService(config)


@pytest.fixture
def cipher():
    """Create cipher with random key."""
    import secrets
    key = secrets.token_bytes(32)
    return AESGCMCipher(key)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_encryption_algorithms(self):
        """Should have expected algorithms."""
        assert EncryptionAlgorithm.AES_256_GCM == "aes-256-gcm"
        assert EncryptionAlgorithm.AES_128_GCM == "aes-128-gcm"
    
    def test_key_types(self):
        """Should have expected key types."""
        assert KeyType.DATA_KEY == "data_key"
        assert KeyType.KEY_ENCRYPTION_KEY == "key_encryption_key"
        assert KeyType.MASTER_KEY == "master_key"


# =============================================================================
# Test: EncryptionConfig
# =============================================================================

class TestEncryptionConfig:
    """Test EncryptionConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = EncryptionConfig()
        
        assert config.algorithm == EncryptionAlgorithm.AES_256_GCM
        assert config.key_size == 32
        assert config.nonce_size == 12
        assert config.tag_size == 16


# =============================================================================
# Test: EncryptedData
# =============================================================================

class TestEncryptedData:
    """Test EncryptedData class."""
    
    def test_to_bytes(self):
        """Should serialize to bytes."""
        encrypted = EncryptedData(
            ciphertext=b"ciphertext",
            nonce=b"nonce123456",
            tag=b"tag1234567890123",
            algorithm="aes-256-gcm",
            key_id="key-1",
        )
        
        result = encrypted.to_bytes()
        
        assert isinstance(result, bytes)
        assert len(result) > 0
    
    def test_from_bytes(self):
        """Should deserialize from bytes."""
        original = EncryptedData(
            ciphertext=b"ciphertext",
            nonce=b"nonce123456",
            tag=b"tag1234567890123",
            algorithm="aes-256-gcm",
            key_id="key-1",
        )
        
        serialized = original.to_bytes()
        restored = EncryptedData.from_bytes(serialized)
        
        assert restored.ciphertext == original.ciphertext
        assert restored.nonce == original.nonce
        assert restored.tag == original.tag
        assert restored.algorithm == original.algorithm
        assert restored.key_id == original.key_id
    
    def test_to_base64(self):
        """Should encode to base64."""
        encrypted = EncryptedData(
            ciphertext=b"test",
            nonce=b"nonce123456",
            tag=b"tag1234567890123",
            algorithm="aes-256-gcm",
            key_id="key-1",
        )
        
        result = encrypted.to_base64()
        
        assert isinstance(result, str)
    
    def test_from_base64(self):
        """Should decode from base64."""
        original = EncryptedData(
            ciphertext=b"test",
            nonce=b"nonce123456",
            tag=b"tag1234567890123",
            algorithm="aes-256-gcm",
            key_id="key-1",
        )
        
        encoded = original.to_base64()
        restored = EncryptedData.from_base64(encoded)
        
        assert restored.ciphertext == original.ciphertext


# =============================================================================
# Test: EncryptionKey
# =============================================================================

class TestEncryptionKey:
    """Test EncryptionKey class."""
    
    def test_is_expired(self):
        """Should check expiration."""
        import time
        
        expired = EncryptionKey(
            key_id="key-1",
            key_material=b"x" * 32,
            key_type=KeyType.DATA_KEY,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            expires_at=time.time() - 1000,
        )
        
        not_expired = EncryptionKey(
            key_id="key-2",
            key_material=b"x" * 32,
            key_type=KeyType.DATA_KEY,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            expires_at=time.time() + 1000,
        )
        
        assert expired.is_expired is True
        assert not_expired.is_expired is False


# =============================================================================
# Test: AESGCMCipher
# =============================================================================

class TestAESGCMCipher:
    """Test AESGCMCipher."""
    
    def test_encrypts_data(self, cipher):
        """Should encrypt data."""
        plaintext = b"Hello, World!"
        
        ciphertext, nonce, tag = cipher.encrypt(plaintext)
        
        assert ciphertext != plaintext
        assert len(nonce) == 12
        assert len(tag) == 16
    
    def test_decrypts_data(self, cipher):
        """Should decrypt data."""
        plaintext = b"Hello, World!"
        
        ciphertext, nonce, tag = cipher.encrypt(plaintext)
        decrypted = cipher.decrypt(ciphertext, nonce, tag)
        
        assert decrypted == plaintext
    
    def test_different_nonces(self, cipher):
        """Should use different nonces."""
        plaintext = b"Same message"
        
        _, nonce1, _ = cipher.encrypt(plaintext)
        _, nonce2, _ = cipher.encrypt(plaintext)
        
        assert nonce1 != nonce2
    
    def test_rejects_tampered_ciphertext(self, cipher):
        """Should reject tampered ciphertext."""
        plaintext = b"Hello!"
        ciphertext, nonce, tag = cipher.encrypt(plaintext)
        
        # Tamper with ciphertext
        tampered = bytes([c ^ 1 for c in ciphertext])
        
        with pytest.raises(ValueError):
            cipher.decrypt(tampered, nonce, tag)
    
    def test_rejects_wrong_tag(self, cipher):
        """Should reject wrong tag."""
        plaintext = b"Hello!"
        ciphertext, nonce, _ = cipher.encrypt(plaintext)
        
        wrong_tag = b"0" * 16
        
        with pytest.raises(ValueError):
            cipher.decrypt(ciphertext, nonce, wrong_tag)
    
    def test_with_aad(self, cipher):
        """Should authenticate AAD."""
        plaintext = b"Hello!"
        aad = b"additional authenticated data"
        
        ciphertext, nonce, tag = cipher.encrypt(plaintext, aad)
        decrypted = cipher.decrypt(ciphertext, nonce, tag, aad)
        
        assert decrypted == plaintext
    
    def test_rejects_wrong_aad(self, cipher):
        """Should reject wrong AAD."""
        plaintext = b"Hello!"
        aad = b"correct aad"
        
        ciphertext, nonce, tag = cipher.encrypt(plaintext, aad)
        
        with pytest.raises(ValueError):
            cipher.decrypt(ciphertext, nonce, tag, b"wrong aad")
    
    def test_rejects_invalid_key_size(self):
        """Should reject invalid key size."""
        with pytest.raises(ValueError):
            AESGCMCipher(b"short")


# =============================================================================
# Test: KeyManager
# =============================================================================

class TestKeyManager:
    """Test KeyManager."""
    
    def test_generates_key(self, key_manager):
        """Should generate key."""
        key = key_manager.generate_key()
        
        assert key is not None
        assert len(key.key_material) == 32
        assert key.is_active is True
    
    def test_gets_key(self, key_manager):
        """Should get key by ID."""
        key = key_manager.generate_key()
        
        found = key_manager.get_key(key.key_id)
        
        assert found is not None
        assert found.key_id == key.key_id
    
    def test_gets_active_key(self, key_manager):
        """Should get active key."""
        key = key_manager.generate_key()
        
        active = key_manager.get_active_key()
        
        assert active is not None
        assert active.key_id == key.key_id
    
    def test_sets_active_key(self, key_manager):
        """Should set active key."""
        key1 = key_manager.generate_key()
        key2 = key_manager.generate_key()
        
        result = key_manager.set_active_key(key2.key_id)
        
        assert result is True
        assert key_manager.get_active_key().key_id == key2.key_id
    
    def test_rotates_key(self, key_manager):
        """Should rotate key."""
        old_key = key_manager.generate_key()
        
        new_key = key_manager.rotate_key()
        
        assert new_key.key_id != old_key.key_id
        assert key_manager.get_active_key().key_id == new_key.key_id
        assert old_key.is_active is False
    
    def test_derives_key_from_password(self, key_manager):
        """Should derive key from password."""
        key, salt = key_manager.derive_key("password123")
        
        assert len(key) == 32
        assert len(salt) == 32
    
    def test_derives_same_key_with_salt(self, key_manager):
        """Should derive same key with same salt."""
        key1, salt = key_manager.derive_key("password123")
        key2, _ = key_manager.derive_key("password123", salt)
        
        assert key1 == key2


# =============================================================================
# Test: EncryptionService
# =============================================================================

class TestEncryptionService:
    """Test EncryptionService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        EncryptionService._instance = None
        
        s1 = get_encryption_service()
        s2 = get_encryption_service()
        
        assert s1 is s2
    
    def test_encrypts_data(self, service):
        """Should encrypt data."""
        plaintext = b"Secret message"
        
        encrypted = service.encrypt(plaintext)
        
        assert encrypted.ciphertext != plaintext
        assert encrypted.key_id is not None
    
    def test_decrypts_data(self, service):
        """Should decrypt data."""
        plaintext = b"Secret message"
        
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypts_string(self, service):
        """Should encrypt string."""
        plaintext = "Hello, World!"
        
        encrypted = service.encrypt_string(plaintext)
        
        assert encrypted != plaintext
        assert isinstance(encrypted, str)
    
    def test_decrypts_string(self, service):
        """Should decrypt string."""
        plaintext = "Hello, World!"
        
        encrypted = service.encrypt_string(plaintext)
        decrypted = service.decrypt_string(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypts_with_aad(self, service):
        """Should encrypt with AAD."""
        plaintext = b"Secret"
        aad = b"context"
        
        encrypted = service.encrypt(plaintext, aad)
        decrypted = service.decrypt(encrypted, aad)
        
        assert decrypted == plaintext
    
    def test_encrypts_with_password(self, service):
        """Should encrypt with password."""
        plaintext = b"Secret message"
        password = "mypassword123"
        
        encrypted, salt = service.encrypt_with_password(plaintext, password)
        decrypted = service.decrypt_with_password(encrypted, password, salt)
        
        assert decrypted == plaintext
    
    def test_rotates_keys(self, service):
        """Should rotate keys."""
        old_key = service.key_manager.get_active_key()
        
        new_key_id = service.rotate_keys()
        
        assert new_key_id != (old_key.key_id if old_key else None)
    
    def test_decrypts_with_old_key(self, service):
        """Should decrypt with old key after rotation."""
        plaintext = b"Before rotation"
        
        encrypted = service.encrypt(plaintext)
        service.rotate_keys()
        decrypted = service.decrypt(encrypted)
        
        assert decrypted == plaintext


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_encrypt_decrypt(self):
        """Should encrypt/decrypt via convenience functions."""
        EncryptionService._instance = None
        plaintext = b"Test data"
        
        encrypted = encrypt(plaintext)
        decrypted = decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypt_decrypt_string(self):
        """Should encrypt/decrypt string."""
        EncryptionService._instance = None
        plaintext = "Test string"
        
        encrypted = encrypt_string(plaintext)
        decrypted = decrypt_string(encrypted)
        
        assert decrypted == plaintext


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_unique_nonces(self, service):
        """Should use unique nonces."""
        plaintext = b"Same data"
        
        enc1 = service.encrypt(plaintext)
        enc2 = service.encrypt(plaintext)
        
        assert enc1.nonce != enc2.nonce
        assert enc1.ciphertext != enc2.ciphertext
    
    def test_authenticated_encryption(self, service):
        """Should use authenticated encryption."""
        plaintext = b"Secret"
        
        encrypted = service.encrypt(plaintext)
        
        # Tamper with ciphertext
        tampered = EncryptedData(
            ciphertext=bytes([c ^ 1 for c in encrypted.ciphertext]),
            nonce=encrypted.nonce,
            tag=encrypted.tag,
            algorithm=encrypted.algorithm,
            key_id=encrypted.key_id,
        )
        
        with pytest.raises(ValueError):
            service.decrypt(tampered)
    
    def test_key_material_secure_length(self, key_manager):
        """Should use secure key length."""
        key = key_manager.generate_key()
        
        assert len(key.key_material) >= 32  # 256 bits
