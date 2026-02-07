"""
Tests for SEC-053: Cryptographic Signing Security Module.
"""

import pytest
import time
from unittest.mock import patch

from shared.crypto_signing import (
    SignatureAlgorithm,
    SignatureError,
    InvalidSignatureError,
    ExpiredSignatureError,
    KeyNotFoundError,
    SignatureConfig,
    SignedMessage,
    VerificationResult,
    HMACGenerator,
    TimestampedSigner,
    KeyStore,
    MultiKeySigner,
    RequestSigner,
    CryptoSigningService,
    get_signing_service,
    sign_message,
    verify_signature,
)


class TestSignatureConfig:
    """Tests for SignatureConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SignatureConfig()
        assert config.algorithm == SignatureAlgorithm.HMAC_SHA256
        assert config.timestamp_tolerance_seconds == 300
        assert config.include_timestamp is True
        assert config.key_min_length == 32
        assert config.encoding == "utf-8"
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = SignatureConfig(
            algorithm=SignatureAlgorithm.HMAC_SHA512,
            timestamp_tolerance_seconds=60,
            include_timestamp=False,
            key_min_length=64
        )
        assert config.algorithm == SignatureAlgorithm.HMAC_SHA512
        assert config.timestamp_tolerance_seconds == 60
        assert config.include_timestamp is False
        assert config.key_min_length == 64


class TestSignedMessage:
    """Tests for SignedMessage dataclass."""
    
    def test_create_signed_message(self):
        """Test creating a signed message."""
        msg = SignedMessage(
            message=b"test",
            signature="abc123",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=1234567890.0,
            key_id="key1"
        )
        assert msg.message == b"test"
        assert msg.signature == "abc123"
        assert msg.algorithm == SignatureAlgorithm.HMAC_SHA256
        assert msg.timestamp == 1234567890.0
        assert msg.key_id == "key1"
    
    def test_optional_fields(self):
        """Test optional fields default to None."""
        msg = SignedMessage(
            message=b"test",
            signature="abc",
            algorithm=SignatureAlgorithm.HMAC_SHA256
        )
        assert msg.timestamp is None
        assert msg.key_id is None


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""
    
    def test_valid_result(self):
        """Test valid verification result."""
        result = VerificationResult(valid=True, message=b"test")
        assert result.valid is True
        assert result.message == b"test"
        assert result.error is None
    
    def test_invalid_result(self):
        """Test invalid verification result."""
        result = VerificationResult(valid=False, error="Bad signature")
        assert result.valid is False
        assert result.error == "Bad signature"


class TestHMACGenerator:
    """Tests for HMACGenerator."""
    
    def test_generate_sha256(self):
        """Test SHA256 HMAC generation."""
        gen = HMACGenerator()
        key = "a" * 32  # 32 byte key
        sig = gen.generate("test message", key)
        assert isinstance(sig, str)
        assert len(sig) > 0
    
    def test_generate_sha384(self):
        """Test SHA384 HMAC generation."""
        gen = HMACGenerator()
        key = "a" * 32
        sig = gen.generate("test", key, SignatureAlgorithm.HMAC_SHA384)
        assert isinstance(sig, str)
    
    def test_generate_sha512(self):
        """Test SHA512 HMAC generation."""
        gen = HMACGenerator()
        key = "a" * 32
        sig = gen.generate("test", key, SignatureAlgorithm.HMAC_SHA512)
        assert isinstance(sig, str)
    
    def test_generate_bytes_input(self):
        """Test generation with bytes input."""
        gen = HMACGenerator()
        key = b"a" * 32
        sig = gen.generate(b"test message", key)
        assert isinstance(sig, str)
    
    def test_key_too_short(self):
        """Test rejection of short keys."""
        gen = HMACGenerator()
        with pytest.raises(ValueError, match="at least 32 bytes"):
            gen.generate("test", "short")
    
    def test_verify_valid(self):
        """Test valid signature verification."""
        gen = HMACGenerator()
        key = "a" * 32
        message = "test message"
        sig = gen.generate(message, key)
        assert gen.verify(message, sig, key) is True
    
    def test_verify_invalid(self):
        """Test invalid signature verification."""
        gen = HMACGenerator()
        key = "a" * 32
        assert gen.verify("test", "invalidsig", key) is False
    
    def test_verify_wrong_key(self):
        """Test verification with wrong key."""
        gen = HMACGenerator()
        key1 = "a" * 32
        key2 = "b" * 32
        sig = gen.generate("test", key1)
        assert gen.verify("test", sig, key2) is False
    
    def test_deterministic(self):
        """Test that same inputs produce same signature."""
        gen = HMACGenerator()
        key = "a" * 32
        sig1 = gen.generate("test", key)
        sig2 = gen.generate("test", key)
        assert sig1 == sig2
    
    def test_different_messages(self):
        """Test different messages produce different signatures."""
        gen = HMACGenerator()
        key = "a" * 32
        sig1 = gen.generate("test1", key)
        sig2 = gen.generate("test2", key)
        assert sig1 != sig2


class TestTimestampedSigner:
    """Tests for TimestampedSigner."""
    
    def test_sign_creates_message(self):
        """Test signing creates SignedMessage."""
        signer = TimestampedSigner("a" * 32)
        signed = signer.sign("test message")
        assert isinstance(signed, SignedMessage)
        assert signed.message == b"test message"
        assert signed.timestamp is not None
        assert signed.signature
    
    def test_verify_valid(self):
        """Test verification of valid signature."""
        signer = TimestampedSigner("a" * 32)
        signed = signer.sign("test")
        result = signer.verify(signed.message, signed.signature, signed.timestamp)
        assert result.valid is True
    
    def test_verify_signed_message(self):
        """Test verification via SignedMessage object."""
        signer = TimestampedSigner("a" * 32)
        signed = signer.sign("test")
        result = signer.verify_signed_message(signed)
        assert result.valid is True
    
    def test_verify_expired(self):
        """Test rejection of expired signature."""
        config = SignatureConfig(timestamp_tolerance_seconds=1)
        signer = TimestampedSigner("a" * 32, config)
        signed = signer.sign("test")
        
        # Mock time to be in the future
        with patch("shared.crypto_signing.time.time", return_value=time.time() + 100):
            result = signer.verify(signed.message, signed.signature, signed.timestamp)
        assert result.valid is False
        assert "expired" in result.error.lower()
    
    def test_verify_tampered_message(self):
        """Test rejection of tampered message."""
        signer = TimestampedSigner("a" * 32)
        signed = signer.sign("original")
        result = signer.verify("tampered", signed.signature, signed.timestamp)
        assert result.valid is False
    
    def test_verify_missing_timestamp(self):
        """Test rejection of missing timestamp."""
        signer = TimestampedSigner("a" * 32)
        signed = SignedMessage(
            message=b"test",
            signature="sig",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=None
        )
        result = signer.verify_signed_message(signed)
        assert result.valid is False
        assert "timestamp" in result.error.lower()
    
    def test_key_too_short(self):
        """Test rejection of short key."""
        with pytest.raises(ValueError, match="at least 32 bytes"):
            TimestampedSigner("short")


class TestKeyStore:
    """Tests for KeyStore."""
    
    def test_add_and_get_key(self):
        """Test adding and retrieving a key."""
        store = KeyStore()
        store.add_key("key1", "a" * 32)
        key = store.get_key("key1")
        assert key == b"a" * 32
    
    def test_get_missing_key(self):
        """Test error on missing key."""
        store = KeyStore()
        with pytest.raises(KeyNotFoundError):
            store.get_key("nonexistent")
    
    def test_remove_key(self):
        """Test removing a key."""
        store = KeyStore()
        store.add_key("key1", "a" * 32)
        assert store.remove_key("key1") is True
        assert store.has_key("key1") is False
    
    def test_remove_nonexistent(self):
        """Test removing nonexistent key returns False."""
        store = KeyStore()
        assert store.remove_key("nonexistent") is False
    
    def test_has_key(self):
        """Test key existence check."""
        store = KeyStore()
        assert store.has_key("key1") is False
        store.add_key("key1", "a" * 32)
        assert store.has_key("key1") is True
    
    def test_list_keys(self):
        """Test listing keys."""
        store = KeyStore()
        store.add_key("key1", "a" * 32)
        store.add_key("key2", "b" * 32)
        keys = store.list_keys()
        assert "key1" in keys
        assert "key2" in keys
    
    def test_get_metadata(self):
        """Test getting key metadata."""
        store = KeyStore()
        store.add_key("key1", "a" * 32, {"purpose": "signing"})
        meta = store.get_metadata("key1")
        assert meta["purpose"] == "signing"
        assert "added_at" in meta
    
    def test_generate_key(self):
        """Test generating a random key."""
        store = KeyStore()
        key = store.generate_key("new_key", 64)
        assert len(key) == 64
        assert store.has_key("new_key") is True


class TestMultiKeySigner:
    """Tests for MultiKeySigner."""
    
    def test_add_key_sets_current(self):
        """Test first key becomes current."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        assert signer._current_key_id == "key1"
    
    def test_set_current_key(self):
        """Test setting current key."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signer.add_key("key2", "b" * 32)
        signer.set_current_key("key2")
        assert signer._current_key_id == "key2"
    
    def test_set_nonexistent_current(self):
        """Test error setting nonexistent key as current."""
        signer = MultiKeySigner()
        with pytest.raises(KeyNotFoundError):
            signer.set_current_key("nonexistent")
    
    def test_sign_with_current_key(self):
        """Test signing with current key."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signed = signer.sign("test")
        assert signed.key_id == "key1"
    
    def test_sign_with_specific_key(self):
        """Test signing with specific key."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signer.add_key("key2", "b" * 32)
        signed = signer.sign("test", key_id="key2")
        assert signed.key_id == "key2"
    
    def test_sign_no_key_available(self):
        """Test error when no key available."""
        signer = MultiKeySigner()
        with pytest.raises(KeyNotFoundError):
            signer.sign("test")
    
    def test_verify_valid(self):
        """Test verification of valid signature."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signed = signer.sign("test")
        result = signer.verify(signed)
        assert result.valid is True
    
    def test_verify_missing_key_id(self):
        """Test verification fails without key ID."""
        signer = MultiKeySigner()
        signed = SignedMessage(
            message=b"test",
            signature="sig",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            key_id=None
        )
        result = signer.verify(signed)
        assert result.valid is False
        assert "key" in result.error.lower()
    
    def test_verify_unknown_key(self):
        """Test verification fails with unknown key."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signed = signer.sign("test")
        signed.key_id = "unknown"
        result = signer.verify(signed)
        assert result.valid is False
    
    def test_rotate_key(self):
        """Test key rotation."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        old_id = signer.rotate_key("key2", "b" * 32)
        assert old_id == "key1"
        assert signer._current_key_id == "key2"
    
    def test_verify_with_old_key_after_rotation(self):
        """Test old signatures still verify after rotation."""
        signer = MultiKeySigner()
        signer.add_key("key1", "a" * 32)
        signed = signer.sign("test")
        signer.rotate_key("key2", "b" * 32)
        result = signer.verify(signed)
        assert result.valid is True


class TestRequestSigner:
    """Tests for RequestSigner."""
    
    def test_sign_request(self):
        """Test signing a request."""
        signer = RequestSigner("a" * 32)
        headers = signer.sign_request("GET", "/api/data")
        assert "X-Signature" in headers
        assert "X-Timestamp" in headers
        assert "X-Signed-Headers" in headers
    
    def test_sign_with_headers(self):
        """Test signing with custom headers."""
        signer = RequestSigner("a" * 32)
        headers = signer.sign_request(
            "POST",
            "/api/data",
            headers={"Content-Type": "application/json"}
        )
        assert headers["X-Signed-Headers"] == "Content-Type"
    
    def test_sign_with_body(self):
        """Test signing with body."""
        signer = RequestSigner("a" * 32)
        headers = signer.sign_request(
            "POST",
            "/api/data",
            body='{"key": "value"}'
        )
        assert "X-Signature" in headers
    
    def test_verify_valid(self):
        """Test verification of valid request."""
        signer = RequestSigner("a" * 32)
        sig_headers = signer.sign_request("GET", "/api/data")
        result = signer.verify_request(
            "GET",
            "/api/data",
            sig_headers["X-Signature"],
            sig_headers["X-Timestamp"],
            sig_headers["X-Signed-Headers"]
        )
        assert result.valid is True
    
    def test_verify_expired(self):
        """Test rejection of expired request."""
        config = SignatureConfig(timestamp_tolerance_seconds=1)
        signer = RequestSigner("a" * 32, config)
        sig_headers = signer.sign_request("GET", "/api/data")
        
        # Mock time to be in the future
        with patch("shared.crypto_signing.time.time", return_value=time.time() + 100):
            result = signer.verify_request(
                "GET",
                "/api/data",
                sig_headers["X-Signature"],
                sig_headers["X-Timestamp"]
            )
        assert result.valid is False
        assert "expired" in result.error.lower()
    
    def test_verify_invalid_timestamp(self):
        """Test rejection of invalid timestamp."""
        signer = RequestSigner("a" * 32)
        result = signer.verify_request(
            "GET",
            "/api/data",
            "signature",
            "not-a-number"
        )
        assert result.valid is False
        assert "timestamp" in result.error.lower()
    
    def test_verify_tampered_method(self):
        """Test rejection of tampered method."""
        signer = RequestSigner("a" * 32)
        sig_headers = signer.sign_request("GET", "/api/data")
        result = signer.verify_request(
            "POST",  # Changed from GET
            "/api/data",
            sig_headers["X-Signature"],
            sig_headers["X-Timestamp"]
        )
        assert result.valid is False
    
    def test_verify_tampered_path(self):
        """Test rejection of tampered path."""
        signer = RequestSigner("a" * 32)
        sig_headers = signer.sign_request("GET", "/api/data")
        result = signer.verify_request(
            "GET",
            "/api/other",  # Changed path
            sig_headers["X-Signature"],
            sig_headers["X-Timestamp"]
        )
        assert result.valid is False


class TestCryptoSigningService:
    """Tests for CryptoSigningService."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        CryptoSigningService.reset()
    
    def test_singleton(self):
        """Test singleton pattern."""
        svc1 = CryptoSigningService()
        svc2 = CryptoSigningService()
        assert svc1 is svc2
    
    def test_configure(self):
        """Test configuration update."""
        svc = CryptoSigningService()
        config = SignatureConfig(algorithm=SignatureAlgorithm.HMAC_SHA512)
        svc.configure(config)
        assert svc.get_config().algorithm == SignatureAlgorithm.HMAC_SHA512
    
    def test_get_hmac_generator(self):
        """Test getting HMAC generator."""
        svc = CryptoSigningService()
        gen = svc.get_hmac_generator()
        assert isinstance(gen, HMACGenerator)
    
    def test_get_timestamped_signer(self):
        """Test getting timestamped signer."""
        svc = CryptoSigningService()
        signer = svc.get_timestamped_signer("a" * 32)
        assert isinstance(signer, TimestampedSigner)
    
    def test_get_multi_key_signer(self):
        """Test getting multi-key signer."""
        svc = CryptoSigningService()
        signer = svc.get_multi_key_signer()
        assert isinstance(signer, MultiKeySigner)
        # Same instance on second call
        assert svc.get_multi_key_signer() is signer
    
    def test_get_request_signer(self):
        """Test getting request signer."""
        svc = CryptoSigningService()
        signer = svc.get_request_signer("a" * 32)
        assert isinstance(signer, RequestSigner)
    
    def test_get_key_store(self):
        """Test getting key store."""
        svc = CryptoSigningService()
        store = svc.get_key_store()
        assert isinstance(store, KeyStore)
    
    def test_quick_sign(self):
        """Test quick signing."""
        svc = CryptoSigningService()
        sig = svc.quick_sign("test", "a" * 32)
        assert isinstance(sig, str)
    
    def test_quick_verify(self):
        """Test quick verification."""
        svc = CryptoSigningService()
        key = "a" * 32
        sig = svc.quick_sign("test", key)
        assert svc.quick_verify("test", sig, key) is True
        assert svc.quick_verify("other", sig, key) is False


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        CryptoSigningService.reset()
    
    def test_get_signing_service(self):
        """Test getting service singleton."""
        svc = get_signing_service()
        assert isinstance(svc, CryptoSigningService)
    
    def test_sign_message(self):
        """Test sign_message function."""
        key = "a" * 32
        sig = sign_message("test", key)
        assert isinstance(sig, str)
    
    def test_verify_signature(self):
        """Test verify_signature function."""
        key = "a" * 32
        sig = sign_message("test", key)
        assert verify_signature("test", sig, key) is True
        assert verify_signature("other", sig, key) is False


class TestSignatureAlgorithm:
    """Tests for SignatureAlgorithm enum."""
    
    def test_hmac_sha256(self):
        """Test HMAC-SHA256 value."""
        assert SignatureAlgorithm.HMAC_SHA256.value == "hmac-sha256"
    
    def test_hmac_sha384(self):
        """Test HMAC-SHA384 value."""
        assert SignatureAlgorithm.HMAC_SHA384.value == "hmac-sha384"
    
    def test_hmac_sha512(self):
        """Test HMAC-SHA512 value."""
        assert SignatureAlgorithm.HMAC_SHA512.value == "hmac-sha512"


class TestExceptionTypes:
    """Tests for exception types."""
    
    def test_signature_error_base(self):
        """Test SignatureError is base class."""
        assert issubclass(InvalidSignatureError, SignatureError)
        assert issubclass(ExpiredSignatureError, SignatureError)
        assert issubclass(KeyNotFoundError, SignatureError)
    
    def test_raise_invalid_signature(self):
        """Test raising InvalidSignatureError."""
        with pytest.raises(InvalidSignatureError):
            raise InvalidSignatureError("Bad signature")
    
    def test_raise_expired_signature(self):
        """Test raising ExpiredSignatureError."""
        with pytest.raises(ExpiredSignatureError):
            raise ExpiredSignatureError("Signature expired")
    
    def test_raise_key_not_found(self):
        """Test raising KeyNotFoundError."""
        with pytest.raises(KeyNotFoundError):
            raise KeyNotFoundError("Key not found")
