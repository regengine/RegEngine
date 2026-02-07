"""Tests for PII encryption utilities."""

import os
import pytest

# Check if cryptography is available
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

from shared.pii_encryption import (
    PIIEncryptionError,
    PIIKeyNotConfiguredError,
    generate_encryption_key,
    hash_for_lookup,
    mask_credit_card,
    mask_ein,
    mask_email,
    mask_phone,
    mask_ssn,
)

# Only import PIIEncryptor if cryptography is available
if CRYPTO_AVAILABLE:
    from shared.pii_encryption import PIIEncryptor


class TestMasking:
    """Tests for PII masking utilities (no encryption needed)."""

    def test_mask_ssn_standard(self):
        """Test SSN masking with dashes."""
        assert mask_ssn("123-45-6789") == "***-**-6789"

    def test_mask_ssn_no_dashes(self):
        """Test SSN masking without dashes."""
        assert mask_ssn("123456789") == "***-**-6789"

    def test_mask_ssn_short(self):
        """Test SSN masking with short input."""
        assert mask_ssn("123") == "***-**-****"

    def test_mask_ein_standard(self):
        """Test EIN masking."""
        assert mask_ein("12-3456789") == "**-***6789"

    def test_mask_ein_no_dash(self):
        """Test EIN masking without dash."""
        assert mask_ein("123456789") == "**-***6789"

    def test_mask_credit_card(self):
        """Test credit card masking."""
        assert mask_credit_card("4111-1111-1111-1234") == "****-****-****-1234"

    def test_mask_credit_card_no_dashes(self):
        """Test credit card masking without dashes."""
        assert mask_credit_card("4111111111111234") == "****-****-****-1234"

    def test_mask_email_normal(self):
        """Test email masking."""
        assert mask_email("john.doe@example.com") == "j*******@example.com"

    def test_mask_email_short_local(self):
        """Test email masking with single char local part."""
        assert mask_email("j@example.com") == "*@example.com"

    def test_mask_email_invalid(self):
        """Test email masking with invalid email."""
        assert mask_email("not-an-email") == "***@***.***"

    def test_mask_phone_standard(self):
        """Test phone masking."""
        assert mask_phone("555-123-4567") == "***-***-4567"

    def test_mask_phone_with_country(self):
        """Test phone masking with country code."""
        assert mask_phone("+1-555-123-4567") == "***-***-4567"


class TestHashForLookup:
    """Tests for PII hashing."""

    def test_hash_deterministic(self):
        """Test hash is deterministic."""
        value = "123-45-6789"
        hash1 = hash_for_lookup(value, salt="test-salt")
        hash2 = hash_for_lookup(value, salt="test-salt")
        assert hash1 == hash2

    def test_hash_different_values(self):
        """Test different values produce different hashes."""
        hash1 = hash_for_lookup("123-45-6789", salt="test-salt")
        hash2 = hash_for_lookup("987-65-4321", salt="test-salt")
        assert hash1 != hash2

    def test_hash_different_salts(self):
        """Test same value with different salts produces different hashes."""
        value = "123-45-6789"
        hash1 = hash_for_lookup(value, salt="salt1")
        hash2 = hash_for_lookup(value, salt="salt2")
        assert hash1 != hash2

    def test_hash_is_hex(self):
        """Test hash output is valid hex."""
        result = hash_for_lookup("test-value", salt="salt")
        assert len(result) == 64  # SHA-256 = 32 bytes = 64 hex chars
        int(result, 16)  # Should not raise


class TestGenerateKey:
    """Tests for key generation."""

    def test_generate_key_length(self):
        """Test generated key is correct length."""
        key = generate_encryption_key()
        assert len(key) == 64  # 32 bytes = 64 hex chars

    def test_generate_key_is_hex(self):
        """Test generated key is valid hex."""
        key = generate_encryption_key()
        bytes.fromhex(key)  # Should not raise

    def test_generate_key_unique(self):
        """Test generated keys are unique."""
        keys = [generate_encryption_key() for _ in range(10)]
        assert len(set(keys)) == 10


@pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not installed")
class TestPIIEncryptor:
    """Tests for PIIEncryptor class."""

    @pytest.fixture
    def test_key(self):
        """Generate a test encryption key."""
        return bytes.fromhex(generate_encryption_key())

    @pytest.fixture
    def encryptor(self, test_key):
        """Create encryptor with test key."""
        return PIIEncryptor(key=test_key, key_id="test-key")

    def test_encrypt_decrypt_roundtrip(self, encryptor):
        """Test encrypt then decrypt returns original."""
        original = "123-45-6789"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_output(self, encryptor):
        """Test same plaintext encrypts to different ciphertext (unique nonce)."""
        plaintext = "test-value"
        enc1 = encryptor.encrypt(plaintext)
        enc2 = encryptor.encrypt(plaintext)
        assert enc1 != enc2

    def test_decrypt_both_produce_same_plaintext(self, encryptor):
        """Test different ciphertexts of same value decrypt correctly."""
        plaintext = "test-value"
        enc1 = encryptor.encrypt(plaintext)
        enc2 = encryptor.encrypt(plaintext)
        assert encryptor.decrypt(enc1) == plaintext
        assert encryptor.decrypt(enc2) == plaintext

    def test_encrypt_empty_raises(self, encryptor):
        """Test encrypting empty string raises."""
        with pytest.raises(PIIEncryptionError, match="Cannot encrypt empty"):
            encryptor.encrypt("")

    def test_decrypt_invalid_format_raises(self, encryptor):
        """Test decrypting invalid format raises."""
        with pytest.raises(PIIEncryptionError):
            encryptor.decrypt("not-valid-encrypted-format")

    def test_decrypt_wrong_key_raises(self, test_key):
        """Test decrypting with wrong key raises."""
        encryptor1 = PIIEncryptor(key=test_key, key_id="key1")
        wrong_key = bytes.fromhex(generate_encryption_key())
        encryptor2 = PIIEncryptor(key=wrong_key, key_id="key1")
        
        encrypted = encryptor1.encrypt("secret")
        
        with pytest.raises(PIIEncryptionError, match="Decryption failed"):
            encryptor2.decrypt(encrypted)

    def test_decrypt_key_id_mismatch_raises(self, test_key):
        """Test decrypting with different key ID raises."""
        encryptor1 = PIIEncryptor(key=test_key, key_id="key1")
        encryptor2 = PIIEncryptor(key=test_key, key_id="key2")
        
        encrypted = encryptor1.encrypt("secret")
        
        with pytest.raises(PIIEncryptionError, match="Key ID mismatch"):
            encryptor2.decrypt(encrypted)

    def test_encrypt_with_associated_data(self, encryptor):
        """Test encryption with associated data."""
        plaintext = "secret-value"
        aad = b"tenant-id:12345"
        
        encrypted = encryptor.encrypt(plaintext, associated_data=aad)
        decrypted = encryptor.decrypt(encrypted, associated_data=aad)
        
        assert decrypted == plaintext

    def test_decrypt_wrong_associated_data_raises(self, encryptor):
        """Test decryption fails with wrong AAD."""
        plaintext = "secret-value"
        
        encrypted = encryptor.encrypt(plaintext, associated_data=b"aad1")
        
        with pytest.raises(PIIEncryptionError, match="Decryption failed"):
            encryptor.decrypt(encrypted, associated_data=b"aad2")

    def test_is_encrypted_true(self, encryptor):
        """Test is_encrypted returns True for encrypted values."""
        encrypted = encryptor.encrypt("test")
        assert encryptor.is_encrypted(encrypted) is True

    def test_is_encrypted_false_plaintext(self, encryptor):
        """Test is_encrypted returns False for plaintext."""
        assert encryptor.is_encrypted("123-45-6789") is False

    def test_is_encrypted_false_empty(self, encryptor):
        """Test is_encrypted returns False for empty string."""
        assert encryptor.is_encrypted("") is False

    def test_encrypt_unicode(self, encryptor):
        """Test encrypting unicode characters."""
        original = "日本語テスト 🔐"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_long_value(self, encryptor):
        """Test encrypting long values."""
        original = "x" * 10000
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original


@pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not installed")
class TestPIIEncryptorEnvConfig:
    """Tests for PIIEncryptor environment configuration."""

    def test_from_env_success(self, monkeypatch):
        """Test encryptor initialization from environment."""
        key = generate_encryption_key()
        monkeypatch.setenv("PII_ENCRYPTION_KEY", key)
        monkeypatch.setenv("PII_ENCRYPTION_KEY_ID", "env-key")
        
        encryptor = PIIEncryptor()
        encrypted = encryptor.encrypt("test")
        
        assert encryptor.decrypt(encrypted) == "test"

    def test_from_env_missing_key_raises(self, monkeypatch):
        """Test error when env key not set."""
        monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)
        
        with pytest.raises(PIIKeyNotConfiguredError, match="not configured"):
            PIIEncryptor()

    def test_from_env_invalid_hex_raises(self, monkeypatch):
        """Test error when key is not valid hex."""
        monkeypatch.setenv("PII_ENCRYPTION_KEY", "not-valid-hex!")
        
        with pytest.raises(PIIEncryptionError, match="valid hexadecimal"):
            PIIEncryptor()

    def test_from_env_wrong_length_raises(self, monkeypatch):
        """Test error when key is wrong length."""
        monkeypatch.setenv("PII_ENCRYPTION_KEY", "abcd1234")  # Too short
        
        with pytest.raises(PIIEncryptionError, match="must be 32 bytes"):
            PIIEncryptor()
