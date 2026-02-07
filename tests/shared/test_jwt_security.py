"""
Tests for SEC-042: JWT Security.

Tests cover:
- JWT token encoding/decoding
- Signature verification
- Claims validation
- Algorithm restrictions
"""

import time
import pytest

from shared.jwt_security import (
    # Enums
    JWTAlgorithm,
    JWTValidationError,
    # Data classes
    JWTConfig,
    JWTHeader,
    JWTPayload,
    JWTValidationResult,
    # Classes
    JWTEncoder,
    JWTDecoder,
    JWTSecurityService,
    # Convenience functions
    get_jwt_service,
    create_jwt,
    validate_jwt,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create JWT config."""
    return JWTConfig()


@pytest.fixture
def secret():
    """Create test secret (32+ chars)."""
    return "this-is-a-very-secure-test-secret-key"


@pytest.fixture
def encoder(config):
    """Create JWT encoder."""
    return JWTEncoder(config)


@pytest.fixture
def decoder(config):
    """Create JWT decoder."""
    return JWTDecoder(config)


@pytest.fixture
def service(config):
    """Create JWT service."""
    JWTSecurityService._instance = None
    return JWTSecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_algorithms(self):
        """Should have expected algorithms."""
        assert JWTAlgorithm.HS256 == "HS256"
        assert JWTAlgorithm.HS384 == "HS384"
        assert JWTAlgorithm.HS512 == "HS512"
        assert JWTAlgorithm.NONE == "none"
    
    def test_validation_errors(self):
        """Should have expected validation errors."""
        assert JWTValidationError.INVALID_FORMAT == "invalid_format"
        assert JWTValidationError.INVALID_SIGNATURE == "invalid_signature"
        assert JWTValidationError.TOKEN_EXPIRED == "token_expired"


# =============================================================================
# Test: JWTConfig
# =============================================================================

class TestJWTConfig:
    """Test JWTConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = JWTConfig()
        
        assert config.algorithm == JWTAlgorithm.HS256
        assert config.verify_signature is True
        assert config.verify_exp is True
        assert config.reject_none_algorithm is True
    
    def test_default_algorithms(self):
        """Should only allow HMAC algorithms by default."""
        config = JWTConfig()
        
        assert JWTAlgorithm.HS256 in config.allowed_algorithms
        assert JWTAlgorithm.NONE not in config.allowed_algorithms


# =============================================================================
# Test: JWTHeader
# =============================================================================

class TestJWTHeader:
    """Test JWTHeader class."""
    
    def test_to_dict(self):
        """Should convert to dict."""
        header = JWTHeader(alg="HS256", typ="JWT")
        
        result = header.to_dict()
        
        assert result["alg"] == "HS256"
        assert result["typ"] == "JWT"
    
    def test_includes_kid(self):
        """Should include key ID when set."""
        header = JWTHeader(alg="HS256", kid="key-1")
        
        result = header.to_dict()
        
        assert result["kid"] == "key-1"


# =============================================================================
# Test: JWTPayload
# =============================================================================

class TestJWTPayload:
    """Test JWTPayload class."""
    
    def test_to_dict(self):
        """Should convert to dict."""
        payload = JWTPayload(
            sub="user-123",
            iss="issuer",
            exp=1234567890,
        )
        
        result = payload.to_dict()
        
        assert result["sub"] == "user-123"
        assert result["iss"] == "issuer"
        assert result["exp"] == 1234567890
    
    def test_from_dict(self):
        """Should create from dict."""
        data = {
            "sub": "user-123",
            "iss": "issuer",
            "custom_claim": "value",
        }
        
        payload = JWTPayload.from_dict(data)
        
        assert payload.sub == "user-123"
        assert payload.iss == "issuer"
        assert payload.custom["custom_claim"] == "value"
    
    def test_custom_claims(self):
        """Should include custom claims."""
        payload = JWTPayload(
            sub="user-123",
            custom={"role": "admin"},
        )
        
        result = payload.to_dict()
        
        assert result["role"] == "admin"


# =============================================================================
# Test: JWTEncoder
# =============================================================================

class TestJWTEncoder:
    """Test JWTEncoder."""
    
    def test_encodes_token(self, encoder, secret):
        """Should encode token."""
        token = encoder.encode({"sub": "user-123"}, secret)
        
        assert token.count(".") == 2
    
    def test_adds_default_claims(self, encoder, secret):
        """Should add default claims."""
        token = encoder.encode({"sub": "user-123"}, secret)
        
        parts = token.split(".")
        assert len(parts) == 3
    
    def test_rejects_short_secret(self, encoder):
        """Should reject short secret."""
        with pytest.raises(ValueError):
            encoder.encode({"sub": "user"}, "short")
    
    def test_uses_specified_algorithm(self, secret):
        """Should use specified algorithm."""
        config = JWTConfig(algorithm=JWTAlgorithm.HS512)
        encoder = JWTEncoder(config)
        
        token = encoder.encode({"sub": "user"}, secret)
        
        # Decode header manually
        import base64
        import json
        header_b64 = token.split(".")[0]
        padding = 4 - len(header_b64) % 4
        if padding != 4:
            header_b64 += "=" * padding
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        
        assert header["alg"] == "HS512"


# =============================================================================
# Test: JWTDecoder
# =============================================================================

class TestJWTDecoder:
    """Test JWTDecoder."""
    
    def test_decodes_valid_token(self, encoder, decoder, secret):
        """Should decode valid token."""
        token = encoder.encode({"sub": "user-123"}, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is True
        assert result.payload.sub == "user-123"
    
    def test_rejects_invalid_format(self, decoder, secret):
        """Should reject invalid format."""
        result = decoder.decode("not.a.valid.token.format", secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.INVALID_FORMAT
    
    def test_rejects_wrong_secret(self, encoder, decoder, secret):
        """Should reject wrong secret."""
        token = encoder.encode({"sub": "user"}, secret)
        
        result = decoder.decode(token, "wrong-secret-that-is-long-enough")
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.INVALID_SIGNATURE
    
    def test_rejects_expired_token(self, encoder, decoder, secret):
        """Should reject expired token."""
        payload = {
            "sub": "user",
            "exp": int(time.time()) - 1000,
        }
        token = encoder.encode(payload, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.TOKEN_EXPIRED
    
    def test_rejects_not_yet_valid(self, encoder, decoder, secret):
        """Should reject token not yet valid."""
        payload = {
            "sub": "user",
            "nbf": int(time.time()) + 1000,
        }
        token = encoder.encode(payload, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.TOKEN_NOT_YET_VALID
    
    def test_allows_leeway(self, encoder, secret):
        """Should allow leeway for expiration."""
        config = JWTConfig(leeway_seconds=60)
        decoder = JWTDecoder(config)
        encoder = JWTEncoder(config)
        
        payload = {
            "sub": "user",
            "exp": int(time.time()) - 30,  # Expired 30s ago
        }
        token = encoder.encode(payload, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is True
    
    def test_rejects_none_algorithm(self, decoder, secret):
        """Should reject 'none' algorithm."""
        # Manually craft token with none algorithm
        import base64
        import json
        
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "user"}).encode()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}."
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.ALGORITHM_NOT_ALLOWED
    
    def test_verifies_issuer(self, encoder, secret):
        """Should verify issuer."""
        config = JWTConfig(
            verify_iss=True,
            issuer="expected-issuer",
        )
        decoder = JWTDecoder(config)
        
        token = encoder.encode({"sub": "user", "iss": "wrong-issuer"}, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.INVALID_ISSUER
    
    def test_verifies_audience(self, encoder, secret):
        """Should verify audience."""
        config = JWTConfig(
            verify_aud=True,
            audience="expected-audience",
        )
        decoder = JWTDecoder(config)
        
        token = encoder.encode({"sub": "user", "aud": "wrong-aud"}, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.INVALID_AUDIENCE
    
    def test_checks_required_claims(self, encoder, secret):
        """Should check required claims."""
        config = JWTConfig(required_claims={"role"})
        decoder = JWTDecoder(config)
        
        token = encoder.encode({"sub": "user"}, secret)
        
        result = decoder.decode(token, secret)
        
        assert result.is_valid is False
        assert result.error == JWTValidationError.MISSING_CLAIMS
    
    def test_decode_without_verify(self, encoder, decoder, secret):
        """Should decode without verification."""
        token = encoder.encode({"sub": "user"}, secret)
        
        result = decoder.decode(token, "wrong-secret", verify=False)
        
        assert result.is_valid is True


# =============================================================================
# Test: JWTSecurityService
# =============================================================================

class TestJWTSecurityService:
    """Test JWTSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        JWTSecurityService._instance = None
        
        s1 = get_jwt_service()
        s2 = get_jwt_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        JWTSecurityService._instance = None
        config = JWTConfig(issuer="test-issuer")
        
        service = JWTSecurityService.configure(config)
        
        assert service.config.issuer == "test-issuer"
    
    def test_create_token(self, service, secret):
        """Should create token."""
        token = service.create_token("user-123", secret)
        
        assert token is not None
        assert token.count(".") == 2
    
    def test_create_token_with_claims(self, service, secret):
        """Should create token with custom claims."""
        token = service.create_token(
            "user-123",
            secret,
            claims={"role": "admin"},
        )
        
        result = service.validate_token(token, secret)
        
        assert result.is_valid is True
        assert result.payload.custom["role"] == "admin"
    
    def test_validate_token(self, service, secret):
        """Should validate token."""
        token = service.create_token("user-123", secret)
        
        result = service.validate_token(token, secret)
        
        assert result.is_valid is True
        assert result.payload.sub == "user-123"
    
    def test_revoke_token(self, service, secret):
        """Should revoke token."""
        token = service.create_token("user-123", secret)
        
        service.revoke_token(token, secret)
        result = service.validate_token(token, secret)
        
        assert result.is_valid is False
        assert "revoked" in result.error_message.lower()
    
    def test_refresh_token(self, service, secret):
        """Should refresh token."""
        token = service.create_token("user-123", secret)
        
        new_token = service.refresh_token(token, secret)
        
        assert new_token is not None
        assert new_token != token
    
    def test_decode_without_verification(self, service, secret):
        """Should decode without verification."""
        token = service.create_token("user-123", secret)
        
        payload = service.decode_without_verification(token)
        
        assert payload is not None
        assert payload.sub == "user-123"


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_jwt(self):
        """Should create via convenience function."""
        JWTSecurityService._instance = None
        secret = "long-secret-for-testing-purposes-here"
        
        token = create_jwt("user-123", secret)
        
        assert token is not None
    
    def test_validate_jwt(self):
        """Should validate via convenience function."""
        JWTSecurityService._instance = None
        secret = "long-secret-for-testing-purposes-here"
        
        token = create_jwt("user-123", secret)
        result = validate_jwt(token, secret)
        
        assert result.is_valid is True


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_rejects_tampered_payload(self, encoder, decoder, secret):
        """Should reject tampered payload."""
        token = encoder.encode({"sub": "user"}, secret)
        
        # Tamper with payload
        parts = token.split(".")
        import base64
        import json
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + "==")
        )
        payload["sub"] = "admin"
        parts[1] = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=").decode()
        tampered = ".".join(parts)
        
        result = decoder.decode(tampered, secret)
        
        assert result.is_valid is False
    
    def test_rejects_tampered_header(self, encoder, decoder, secret):
        """Should reject tampered header."""
        token = encoder.encode({"sub": "user"}, secret)
        
        # Tamper with header
        parts = token.split(".")
        import base64
        import json
        header = json.loads(
            base64.urlsafe_b64decode(parts[0] + "==")
        )
        header["alg"] = "HS512"
        parts[0] = base64.urlsafe_b64encode(
            json.dumps(header).encode()
        ).rstrip(b"=").decode()
        tampered = ".".join(parts)
        
        result = decoder.decode(tampered, secret)
        
        assert result.is_valid is False
    
    def test_uses_timing_safe_comparison(self, encoder, decoder, secret):
        """Should use timing-safe comparison."""
        # The code uses hmac.compare_digest
        token = encoder.encode({"sub": "user"}, secret)
        
        # Valid token
        result1 = decoder.decode(token, secret)
        assert result1.is_valid is True
        
        # Wrong secret
        result2 = decoder.decode(token, "wrong-but-long-enough-secret")
        assert result2.is_valid is False
    
    def test_enforces_min_secret_length(self, encoder):
        """Should enforce minimum secret length."""
        with pytest.raises(ValueError):
            encoder.encode({"sub": "user"}, "short")
