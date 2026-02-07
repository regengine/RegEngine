"""
Tests for SEC-022: Secure Data Encryption.

Tests cover:
- Basic encryption/decryption
- Authenticated encryption (AAD)
- Envelope encryption
- Field-level encryption
- Searchable encryption
- Error handling
"""

import asyncio
import base64
import pytest
import secrets

from shared.data_encryption import (
    # Enums
    EncryptionAlgorithm,
    DataClassification,
    # Exceptions
    EncryptionError,
    DecryptionError,
    IntegrityError,
    KeyNotFoundError,
    # Data classes
    EncryptedData,
    EncryptionContext,
    # Core
    EncryptionEngine,
    EnvelopeEncryption,
    FieldEncryptor,
    SearchableEncryption,
    # Service
    DataEncryptionService,
    # Functions
    get_encryption_service,
    encrypt_data,
    decrypt_data,
    encrypt_string,
    decrypt_string,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def aes_key():
    """Generate AES-256 key."""
    return secrets.token_bytes(32)


@pytest.fixture
def engine():
    """Create encryption engine."""
    return EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)


@pytest.fixture
def service(aes_key):
    """Create encryption service."""
    return DataEncryptionService(default_key=aes_key)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_encryption_algorithm(self):
        """Should have expected algorithms."""
        assert EncryptionAlgorithm.AES_256_GCM == "aes-256-gcm"
        assert EncryptionAlgorithm.CHACHA20_POLY1305 == "chacha20-poly1305"
    
    def test_data_classification(self):
        """Should have expected classifications."""
        assert DataClassification.PUBLIC == "public"
        assert DataClassification.RESTRICTED == "restricted"


# =============================================================================
# Test: Encrypted Data
# =============================================================================

class TestEncryptedData:
    """Test EncryptedData container."""
    
    def test_creation(self):
        """Should create encrypted data container."""
        data = EncryptedData(
            version=1,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_id="key-123",
            key_version=1,
            nonce=b"123456789012",
            ciphertext=b"encrypted_data",
        )
        
        assert data.version == 1
        assert data.key_id == "key-123"
    
    def test_to_bytes_and_back(self):
        """Should serialize and deserialize."""
        original = EncryptedData(
            version=1,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_id="test-key",
            key_version=2,
            nonce=secrets.token_bytes(12),
            ciphertext=secrets.token_bytes(50),
        )
        
        serialized = original.to_bytes()
        restored = EncryptedData.from_bytes(serialized)
        
        assert restored.version == original.version
        assert restored.algorithm == original.algorithm
        assert restored.key_id == original.key_id
        assert restored.key_version == original.key_version
        assert restored.nonce == original.nonce
        assert restored.ciphertext == original.ciphertext
    
    def test_to_base64_and_back(self):
        """Should encode and decode base64."""
        original = EncryptedData(
            version=1,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_id="key-123",
            key_version=1,
            nonce=secrets.token_bytes(12),
            ciphertext=b"encrypted_content",
        )
        
        encoded = original.to_base64()
        restored = EncryptedData.from_base64(encoded)
        
        assert restored.key_id == original.key_id
        assert restored.ciphertext == original.ciphertext


# =============================================================================
# Test: Encryption Context
# =============================================================================

class TestEncryptionContext:
    """Test EncryptionContext."""
    
    def test_to_aad_with_fields(self):
        """Should create AAD from context fields."""
        context = EncryptionContext(
            tenant_id="tenant-1",
            user_id="user-123",
            resource_type="document",
            resource_id="doc-456",
        )
        
        aad = context.to_aad()
        
        assert b"tenant:tenant-1" in aad
        assert b"user:user-123" in aad
        assert b"type:document" in aad
    
    def test_to_aad_with_extra(self):
        """Should include extra fields in AAD."""
        context = EncryptionContext(
            purpose="backup",
            extra={"region": "us-east-1"},
        )
        
        aad = context.to_aad()
        
        assert b"purpose:backup" in aad
        assert b"region:us-east-1" in aad


# =============================================================================
# Test: Encryption Engine
# =============================================================================

class TestEncryptionEngine:
    """Test EncryptionEngine."""
    
    def test_encrypt_decrypt_aes_gcm(self, aes_key):
        """Should encrypt and decrypt with AES-GCM."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Hello, World!"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key)
        decrypted = engine.decrypt(ciphertext, aes_key, nonce)
        
        assert decrypted == plaintext
    
    def test_encrypt_decrypt_with_aad(self, aes_key):
        """Should authenticate additional data."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Secret message"
        aad = b"context:user-123"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key, aad)
        decrypted = engine.decrypt(ciphertext, aes_key, nonce, aad)
        
        assert decrypted == plaintext
    
    def test_wrong_aad_fails(self, aes_key):
        """Should fail with wrong AAD."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Secret message"
        aad = b"context:user-123"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key, aad)
        
        # Try with wrong AAD
        with pytest.raises(DecryptionError):
            engine.decrypt(ciphertext, aes_key, nonce, b"wrong:aad")
    
    def test_wrong_key_fails(self, aes_key):
        """Should fail with wrong key."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Secret message"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key)
        
        wrong_key = secrets.token_bytes(32)
        with pytest.raises(DecryptionError):
            engine.decrypt(ciphertext, wrong_key, nonce)
    
    def test_tampered_ciphertext_fails(self, aes_key):
        """Should detect tampered ciphertext."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Secret message"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key)
        
        # Tamper with ciphertext
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF
        
        with pytest.raises(DecryptionError):
            engine.decrypt(bytes(tampered), aes_key, nonce)
    
    def test_unique_nonces(self, aes_key):
        """Should generate unique nonces."""
        engine = EncryptionEngine(EncryptionAlgorithm.AES_256_GCM)
        plaintext = b"Same message"
        
        nonce1, _ = engine.encrypt(plaintext, aes_key)
        nonce2, _ = engine.encrypt(plaintext, aes_key)
        
        assert nonce1 != nonce2
    
    def test_chacha20_poly1305(self, aes_key):
        """Should encrypt with ChaCha20-Poly1305."""
        engine = EncryptionEngine(EncryptionAlgorithm.CHACHA20_POLY1305)
        plaintext = b"ChaCha20 test message"
        
        nonce, ciphertext = engine.encrypt(plaintext, aes_key)
        decrypted = engine.decrypt(ciphertext, aes_key, nonce)
        
        assert decrypted == plaintext


# =============================================================================
# Test: Envelope Encryption
# =============================================================================

class TestEnvelopeEncryption:
    """Test EnvelopeEncryption."""
    
    def test_encrypt_decrypt(self, aes_key):
        """Should encrypt and decrypt with envelope encryption."""
        envelope = EnvelopeEncryption()
        plaintext = b"Large document content" * 100
        
        enc_dek, dek_nonce, ciphertext, data_nonce = envelope.encrypt(
            plaintext, aes_key
        )
        
        decrypted = envelope.decrypt(
            enc_dek, dek_nonce, ciphertext, data_nonce, aes_key
        )
        
        assert decrypted == plaintext
    
    def test_envelope_with_aad(self, aes_key):
        """Should support AAD."""
        envelope = EnvelopeEncryption()
        plaintext = b"Sensitive data"
        aad = b"user:123|doc:456"
        
        enc_dek, dek_nonce, ciphertext, data_nonce = envelope.encrypt(
            plaintext, aes_key, aad
        )
        
        decrypted = envelope.decrypt(
            enc_dek, dek_nonce, ciphertext, data_nonce, aes_key, aad
        )
        
        assert decrypted == plaintext
    
    def test_different_dek_each_time(self, aes_key):
        """Should use different DEK for each encryption."""
        envelope = EnvelopeEncryption()
        plaintext = b"Same message"
        
        enc_dek1, _, _, _ = envelope.encrypt(plaintext, aes_key)
        enc_dek2, _, _, _ = envelope.encrypt(plaintext, aes_key)
        
        # DEKs should be different
        assert enc_dek1 != enc_dek2


# =============================================================================
# Test: Field Encryption
# =============================================================================

class TestFieldEncryptor:
    """Test FieldEncryptor."""
    
    def test_encrypt_decrypt_string_field(self, aes_key):
        """Should encrypt and decrypt string field."""
        encryptor = FieldEncryptor(aes_key)
        
        encrypted = encryptor.encrypt_field("John Doe", "name")
        decrypted = encryptor.decrypt_field(encrypted, "name", str)
        
        assert decrypted == "John Doe"
    
    def test_encrypt_decrypt_json_field(self, aes_key):
        """Should encrypt and decrypt JSON-serializable field."""
        encryptor = FieldEncryptor(aes_key)
        data = {"ssn": "123-45-6789", "dob": "1990-01-15"}
        
        encrypted = encryptor.encrypt_field(data, "personal_info")
        decrypted = encryptor.decrypt_field(encrypted, "personal_info", dict)
        
        assert decrypted == data
    
    def test_field_binding(self, aes_key):
        """Should bind encryption to field name."""
        encryptor = FieldEncryptor(aes_key)
        
        encrypted = encryptor.encrypt_field("secret", "field_a")
        
        # Decrypt with wrong field name should fail
        with pytest.raises(DecryptionError):
            encryptor.decrypt_field(encrypted, "field_b", str)
    
    def test_encrypt_decrypt_multiple_fields(self, aes_key):
        """Should encrypt multiple fields in dictionary."""
        encryptor = FieldEncryptor(aes_key)
        
        data = {
            "id": "user-123",
            "email": "john@example.com",
            "ssn": "123-45-6789",
            "name": "John Doe",
        }
        
        # Encrypt sensitive fields
        encrypted = encryptor.encrypt_fields(
            data,
            {"email", "ssn"},
        )
        
        assert encrypted["id"] == "user-123"  # Unchanged
        assert encrypted["name"] == "John Doe"  # Unchanged
        assert encrypted["email"] != "john@example.com"  # Encrypted
        assert encrypted["ssn"] != "123-45-6789"  # Encrypted
        
        # Decrypt
        decrypted = encryptor.decrypt_fields(
            encrypted,
            {"email": str, "ssn": str},
        )
        
        assert decrypted["email"] == "john@example.com"
        assert decrypted["ssn"] == "123-45-6789"
    
    def test_context_binding(self, aes_key):
        """Should bind encryption to context."""
        encryptor = FieldEncryptor(aes_key)
        context = EncryptionContext(tenant_id="tenant-1", user_id="user-123")
        
        encrypted = encryptor.encrypt_field("secret", "data", context)
        
        # Decrypt with same context
        decrypted = encryptor.decrypt_field(encrypted, "data", str, context)
        assert decrypted == "secret"
        
        # Different context should fail
        wrong_context = EncryptionContext(tenant_id="tenant-2", user_id="user-123")
        with pytest.raises(DecryptionError):
            encryptor.decrypt_field(encrypted, "data", str, wrong_context)


# =============================================================================
# Test: Searchable Encryption
# =============================================================================

class TestSearchableEncryption:
    """Test SearchableEncryption."""
    
    def test_deterministic_encryption(self, aes_key):
        """Should produce same ciphertext for same plaintext."""
        searchable = SearchableEncryption(aes_key)
        
        enc1 = searchable.encrypt("john@example.com")
        enc2 = searchable.encrypt("john@example.com")
        
        assert enc1 == enc2
    
    def test_encrypt_decrypt(self, aes_key):
        """Should encrypt and decrypt correctly."""
        searchable = SearchableEncryption(aes_key)
        
        plaintext = "sensitive_value"
        encrypted = searchable.encrypt(plaintext)
        decrypted = searchable.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_different_values_different_ciphertexts(self, aes_key):
        """Should produce different ciphertexts for different values."""
        searchable = SearchableEncryption(aes_key)
        
        enc1 = searchable.encrypt("value1")
        enc2 = searchable.encrypt("value2")
        
        assert enc1 != enc2
    
    def test_search_token(self, aes_key):
        """Should create matching search token."""
        searchable = SearchableEncryption(aes_key)
        
        # Encrypt value
        encrypted = searchable.encrypt("searchable@email.com")
        
        # Create search token
        token = searchable.create_search_token("searchable@email.com")
        
        # Should match
        assert token == encrypted


# =============================================================================
# Test: Data Encryption Service
# =============================================================================

class TestDataEncryptionService:
    """Test DataEncryptionService."""
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt(self, service):
        """Should encrypt and decrypt data."""
        plaintext = "Hello, encryption!"
        
        encrypted = await service.encrypt(plaintext)
        decrypted = await service.decrypt(encrypted)
        
        assert decrypted.decode() == plaintext
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_bytes(self, service):
        """Should handle bytes input."""
        plaintext = b"Binary data \x00\x01\x02"
        
        encrypted = await service.encrypt(plaintext)
        decrypted = await service.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    @pytest.mark.asyncio
    async def test_encrypt_with_context(self, service):
        """Should bind to encryption context."""
        plaintext = "Context-bound data"
        context = EncryptionContext(tenant_id="t1", user_id="u1")
        
        encrypted = await service.encrypt(plaintext, context=context)
        decrypted = await service.decrypt(encrypted, context=context)
        
        assert decrypted.decode() == plaintext
    
    @pytest.mark.asyncio
    async def test_registered_key(self, service):
        """Should use registered key."""
        custom_key = secrets.token_bytes(32)
        service.register_key("custom-key", custom_key, version=1)
        
        plaintext = "Using custom key"
        encrypted = await service.encrypt(plaintext, key_id="custom-key")
        
        assert encrypted.key_id == "custom-key"
        
        decrypted = await service.decrypt(encrypted)
        assert decrypted.decode() == plaintext
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_string(self, service):
        """Should encrypt/decrypt string with base64."""
        plaintext = "String to encrypt"
        
        encrypted_b64 = await service.encrypt_string(plaintext)
        decrypted = await service.decrypt_string(encrypted_b64)
        
        assert decrypted == plaintext
    
    def test_create_field_encryptor(self, service):
        """Should create field encryptor."""
        encryptor = service.create_field_encryptor()
        
        encrypted = encryptor.encrypt_field("value", "field")
        decrypted = encryptor.decrypt_field(encrypted, "field", str)
        
        assert decrypted == "value"


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_encryption_service(self):
        """Should return singleton."""
        service1 = get_encryption_service()
        service2 = get_encryption_service()
        assert service1 is service2
    
    @pytest.mark.asyncio
    async def test_encrypt_data_function(self):
        """Should encrypt via convenience function."""
        DataEncryptionService.configure()
        
        encrypted = await encrypt_data("test message")
        
        assert encrypted.ciphertext is not None
    
    @pytest.mark.asyncio
    async def test_decrypt_data_function(self):
        """Should decrypt via convenience function."""
        DataEncryptionService.configure()
        
        encrypted = await encrypt_data("test message")
        decrypted = await decrypt_data(encrypted)
        
        assert decrypted.decode() == "test message"
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_string_functions(self):
        """Should encrypt/decrypt string via functions."""
        DataEncryptionService.configure()
        
        encrypted = await encrypt_string("hello world")
        decrypted = await decrypt_string(encrypted)
        
        assert decrypted == "hello world"
