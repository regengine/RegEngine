"""
Tests for SEC-024: Digital Signatures.

Tests cover:
- Key pair generation (RSA, ECDSA, Ed25519)
- Signature creation
- Signature verification
- Document signing
- JSON signing
- Signature service
"""

import pytest
import json

from shared.digital_signatures import (
    # Enums
    SignatureAlgorithm,
    KeySize,
    HashAlgorithm,
    # Exceptions
    SignatureError,
    SignatureVerificationError,
    KeyGenerationError,
    InvalidKeyError,
    # Data classes
    KeyPair,
    Signature,
    SignedDocument,
    VerificationResult,
    # Classes
    KeyGenerator,
    Signer,
    DocumentSigner,
    SignatureService,
    # Convenience functions
    get_signature_service,
    generate_key_pair,
    sign_data,
    verify_signature,
    CRYPTOGRAPHY_AVAILABLE,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def rsa_key_pair():
    """Generate RSA key pair for testing."""
    if not CRYPTOGRAPHY_AVAILABLE:
        pytest.skip("cryptography not available")
    return KeyGenerator.generate_rsa(KeySize.RSA_2048)


@pytest.fixture
def ecdsa_key_pair():
    """Generate ECDSA key pair for testing."""
    if not CRYPTOGRAPHY_AVAILABLE:
        pytest.skip("cryptography not available")
    return KeyGenerator.generate_ecdsa("P-256")


@pytest.fixture
def ed25519_key_pair():
    """Generate Ed25519 key pair for testing."""
    if not CRYPTOGRAPHY_AVAILABLE:
        pytest.skip("cryptography not available")
    return KeyGenerator.generate_ed25519()


@pytest.fixture
def signer():
    """Create signer instance."""
    return Signer(key_id="test-key")


@pytest.fixture
def service():
    """Create signature service."""
    return SignatureService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_signature_algorithms(self):
        """Should have expected algorithms."""
        assert SignatureAlgorithm.RSA_PSS_SHA256 == "rsa-pss-sha256"
        assert SignatureAlgorithm.ECDSA_P256_SHA256 == "ecdsa-p256-sha256"
        assert SignatureAlgorithm.ED25519 == "ed25519"
    
    def test_key_sizes(self):
        """Should have secure key sizes."""
        assert KeySize.RSA_2048 == 2048
        assert KeySize.RSA_4096 == 4096
    
    def test_hash_algorithms(self):
        """Should have expected hashes."""
        assert HashAlgorithm.SHA256 == "sha256"
        assert HashAlgorithm.SHA512 == "sha512"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""
    
    def test_signature_to_base64(self):
        """Should encode signature to base64."""
        sig = Signature(
            value=b"test-signature",
            algorithm=SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        encoded = sig.to_base64()
        assert isinstance(encoded, str)
    
    def test_signature_from_base64(self):
        """Should decode signature from base64."""
        sig = Signature(
            value=b"test-signature",
            algorithm=SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        encoded = sig.to_base64()
        decoded = Signature.from_base64(encoded, SignatureAlgorithm.RSA_PSS_SHA256)
        
        assert decoded.value == sig.value
    
    def test_signature_to_dict(self):
        """Should convert to dictionary."""
        sig = Signature(
            value=b"test-signature",
            algorithm=SignatureAlgorithm.RSA_PSS_SHA256,
            key_id="test-key",
        )
        
        data = sig.to_dict()
        
        assert "value" in data
        assert "algorithm" in data
        assert data["key_id"] == "test-key"
    
    def test_key_pair_generates_id(self):
        """Should auto-generate key ID."""
        key_pair = KeyPair(
            private_key=b"private",
            public_key=b"public",
            algorithm=SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        assert key_pair.key_id != ""


# =============================================================================
# Test: Key Generation
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestKeyGenerator:
    """Test key generation."""
    
    def test_generate_rsa_2048(self):
        """Should generate RSA-2048 key pair."""
        key_pair = KeyGenerator.generate_rsa(KeySize.RSA_2048)
        
        assert key_pair.private_key.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert key_pair.public_key.startswith(b"-----BEGIN PUBLIC KEY-----")
    
    def test_generate_rsa_4096(self):
        """Should generate RSA-4096 key pair."""
        key_pair = KeyGenerator.generate_rsa(KeySize.RSA_4096)
        
        assert key_pair.algorithm.value.startswith("rsa")
    
    def test_generate_ecdsa_p256(self):
        """Should generate ECDSA P-256 key pair."""
        key_pair = KeyGenerator.generate_ecdsa("P-256")
        
        assert key_pair.algorithm == SignatureAlgorithm.ECDSA_P256_SHA256
    
    def test_generate_ecdsa_p384(self):
        """Should generate ECDSA P-384 key pair."""
        key_pair = KeyGenerator.generate_ecdsa("P-384")
        
        assert key_pair.algorithm == SignatureAlgorithm.ECDSA_P384_SHA384
    
    def test_generate_ecdsa_p521(self):
        """Should generate ECDSA P-521 key pair."""
        key_pair = KeyGenerator.generate_ecdsa("P-521")
        
        assert key_pair.algorithm == SignatureAlgorithm.ECDSA_P521_SHA512
    
    def test_generate_ecdsa_unsupported_curve(self):
        """Should reject unsupported curve."""
        with pytest.raises(KeyGenerationError):
            KeyGenerator.generate_ecdsa("P-999")
    
    def test_generate_ed25519(self):
        """Should generate Ed25519 key pair."""
        key_pair = KeyGenerator.generate_ed25519()
        
        assert key_pair.algorithm == SignatureAlgorithm.ED25519


# =============================================================================
# Test: RSA Signatures
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestRSASignatures:
    """Test RSA signatures."""
    
    def test_sign_rsa_pss_sha256(self, rsa_key_pair, signer):
        """Should sign with RSA-PSS SHA-256."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            rsa_key_pair.private_key,
            SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        assert signature.value is not None
        assert signature.algorithm == SignatureAlgorithm.RSA_PSS_SHA256
    
    def test_verify_rsa_pss_sha256(self, rsa_key_pair, signer):
        """Should verify RSA-PSS SHA-256 signature."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            rsa_key_pair.private_key,
            SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        result = signer.verify(data, signature, rsa_key_pair.public_key)
        
        assert result.valid is True
    
    def test_verify_wrong_data(self, rsa_key_pair, signer):
        """Should reject tampered data."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            rsa_key_pair.private_key,
            SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        result = signer.verify(b"Tampered data", signature, rsa_key_pair.public_key)
        
        assert result.valid is False
        assert result.error is not None
    
    def test_sign_rsa_pkcs1(self, rsa_key_pair, signer):
        """Should sign with RSA PKCS#1 v1.5."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            rsa_key_pair.private_key,
            SignatureAlgorithm.RSA_PKCS1_SHA256,
        )
        
        result = signer.verify(data, signature, rsa_key_pair.public_key)
        
        assert result.valid is True


# =============================================================================
# Test: ECDSA Signatures
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestECDSASignatures:
    """Test ECDSA signatures."""
    
    def test_sign_ecdsa_p256(self, ecdsa_key_pair, signer):
        """Should sign with ECDSA P-256."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            ecdsa_key_pair.private_key,
            SignatureAlgorithm.ECDSA_P256_SHA256,
        )
        
        assert signature.value is not None
    
    def test_verify_ecdsa_p256(self, ecdsa_key_pair, signer):
        """Should verify ECDSA P-256 signature."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            ecdsa_key_pair.private_key,
            SignatureAlgorithm.ECDSA_P256_SHA256,
        )
        
        result = signer.verify(data, signature, ecdsa_key_pair.public_key)
        
        assert result.valid is True
    
    def test_verify_ecdsa_wrong_key(self, signer):
        """Should reject signature with wrong key."""
        data = b"Test data to sign"
        
        key_pair1 = KeyGenerator.generate_ecdsa("P-256")
        key_pair2 = KeyGenerator.generate_ecdsa("P-256")
        
        signature = signer.sign(
            data,
            key_pair1.private_key,
            SignatureAlgorithm.ECDSA_P256_SHA256,
        )
        
        # Verify with wrong public key
        result = signer.verify(data, signature, key_pair2.public_key)
        
        assert result.valid is False


# =============================================================================
# Test: Ed25519 Signatures
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestEd25519Signatures:
    """Test Ed25519 signatures."""
    
    def test_sign_ed25519(self, ed25519_key_pair, signer):
        """Should sign with Ed25519."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            ed25519_key_pair.private_key,
            SignatureAlgorithm.ED25519,
        )
        
        assert signature.value is not None
        assert signature.algorithm == SignatureAlgorithm.ED25519
    
    def test_verify_ed25519(self, ed25519_key_pair, signer):
        """Should verify Ed25519 signature."""
        data = b"Test data to sign"
        
        signature = signer.sign(
            data,
            ed25519_key_pair.private_key,
            SignatureAlgorithm.ED25519,
        )
        
        result = signer.verify(data, signature, ed25519_key_pair.public_key)
        
        assert result.valid is True
    
    def test_ed25519_fast(self, signer):
        """Ed25519 should be fast for signing."""
        key_pair = KeyGenerator.generate_ed25519()
        data = b"Test data" * 100
        
        # Should complete quickly
        for _ in range(10):
            signature = signer.sign(data, key_pair.private_key, SignatureAlgorithm.ED25519)
            assert signature.value is not None


# =============================================================================
# Test: Document Signer
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestDocumentSigner:
    """Test document signing workflow."""
    
    def test_sign_document(self, ecdsa_key_pair):
        """Should sign document."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        content = b"Document content to sign"
        
        signed = doc_signer.sign_document(content, signer_id="user123")
        
        assert signed.content == content
        assert signed.content_hash != ""
        assert signed.signature is not None
        assert signed.signer_id == "user123"
    
    def test_verify_document(self, ecdsa_key_pair):
        """Should verify signed document."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        content = b"Document content to sign"
        
        signed = doc_signer.sign_document(content)
        result = doc_signer.verify_document(signed)
        
        assert result.valid is True
    
    def test_verify_tampered_document(self, ecdsa_key_pair):
        """Should detect tampered document."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        content = b"Document content to sign"
        
        signed = doc_signer.sign_document(content)
        
        # Tamper with content
        signed.content = b"Tampered content"
        
        result = doc_signer.verify_document(signed)
        
        assert result.valid is False
        assert "hash mismatch" in result.error.lower()
    
    def test_sign_json(self, ecdsa_key_pair):
        """Should sign JSON data."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        data = {"key": "value", "count": 42}
        
        signed = doc_signer.sign_json(data, signer_id="user123")
        
        assert "data" in signed
        assert "signature" in signed
        assert "content_hash" in signed
    
    def test_verify_json(self, ecdsa_key_pair):
        """Should verify signed JSON."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        data = {"key": "value", "count": 42}
        
        signed = doc_signer.sign_json(data)
        result = doc_signer.verify_json(signed)
        
        assert result.valid is True
    
    def test_document_metadata(self, ecdsa_key_pair):
        """Should include metadata."""
        doc_signer = DocumentSigner(key_pair=ecdsa_key_pair)
        content = b"Content"
        metadata = {"version": "1.0", "classification": "confidential"}
        
        signed = doc_signer.sign_document(content, metadata=metadata)
        
        assert signed.metadata == metadata


# =============================================================================
# Test: Signature Service
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestSignatureService:
    """Test signature service."""
    
    def test_generate_key_pair(self, service):
        """Should generate and store key pair."""
        key_pair = service.generate_key_pair()
        
        assert key_pair.key_id != ""
        
        # Should be stored
        retrieved = service.get_key_pair(key_pair.key_id)
        assert retrieved is not None
    
    def test_generate_with_custom_id(self, service):
        """Should use custom key ID."""
        key_pair = service.generate_key_pair(key_id="my-custom-key")
        
        assert key_pair.key_id == "my-custom-key"
    
    def test_sign_with_key_id(self, service):
        """Should sign using stored key."""
        key_pair = service.generate_key_pair()
        data = b"Test data"
        
        signature = service.sign(data, key_id=key_pair.key_id)
        
        assert signature.key_id == key_pair.key_id
    
    def test_sign_with_key_pair(self, service):
        """Should sign using provided key pair."""
        key_pair = service.generate_key_pair()
        data = b"Test data"
        
        signature = service.sign(data, key_pair=key_pair)
        
        assert signature is not None
    
    def test_verify_with_key_id(self, service):
        """Should verify using stored key."""
        key_pair = service.generate_key_pair()
        data = b"Test data"
        
        signature = service.sign(data, key_id=key_pair.key_id)
        result = service.verify(data, signature, key_id=key_pair.key_id)
        
        assert result.valid is True
    
    def test_create_document_signer(self, service):
        """Should create document signer."""
        key_pair = service.generate_key_pair()
        
        doc_signer = service.create_document_signer(key_id=key_pair.key_id)
        
        assert doc_signer is not None
        assert doc_signer.key_pair == key_pair
    
    def test_configure_singleton(self):
        """Should configure global instance."""
        service = SignatureService.configure(
            default_algorithm=SignatureAlgorithm.RSA_PSS_SHA256,
        )
        
        assert service.default_algorithm == SignatureAlgorithm.RSA_PSS_SHA256


# =============================================================================
# Test: Convenience Functions
# =============================================================================

@pytest.mark.skipif(not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not available")
class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_signature_service(self):
        """Should return service instance."""
        service = get_signature_service()
        assert service is not None
    
    def test_generate_key_pair_function(self):
        """Should generate via convenience function."""
        key_pair = generate_key_pair()
        
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None
    
    def test_sign_and_verify(self):
        """Should sign and verify via convenience functions."""
        key_pair = generate_key_pair(SignatureAlgorithm.ED25519)
        data = b"Test data"
        
        signature = sign_data(data, key_pair)
        result = verify_signature(data, signature, key_pair.public_key)
        
        assert result.valid is True
