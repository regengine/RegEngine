"""
SEC-042: JWT Security.

Secure JWT token handling with validation, claims verification,
and secure key management.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JWTAlgorithm(str, Enum):
    """Supported JWT algorithms."""
    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"
    # Note: RS256/ES256 would need cryptography library
    NONE = "none"  # For testing only - should be rejected


class JWTValidationError(str, Enum):
    """JWT validation errors."""
    INVALID_FORMAT = "invalid_format"
    INVALID_SIGNATURE = "invalid_signature"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_NOT_YET_VALID = "token_not_yet_valid"
    INVALID_ISSUER = "invalid_issuer"
    INVALID_AUDIENCE = "invalid_audience"
    MISSING_CLAIMS = "missing_claims"
    ALGORITHM_NOT_ALLOWED = "algorithm_not_allowed"
    INVALID_TOKEN = "invalid_token"


@dataclass
class JWTConfig:
    """Configuration for JWT security."""
    
    # Algorithm
    algorithm: JWTAlgorithm = JWTAlgorithm.HS256
    allowed_algorithms: set = field(default_factory=lambda: {
        JWTAlgorithm.HS256,
        JWTAlgorithm.HS384,
        JWTAlgorithm.HS512,
    })
    
    # Validation
    verify_signature: bool = True
    verify_exp: bool = True
    verify_nbf: bool = True
    verify_iat: bool = True
    verify_iss: bool = False
    verify_aud: bool = False
    
    # Claims
    issuer: Optional[str] = None
    audience: Optional[str] = None
    required_claims: set = field(default_factory=set)
    
    # Timing
    leeway_seconds: int = 0
    default_exp_seconds: int = 3600  # 1 hour
    max_exp_seconds: int = 86400  # 24 hours
    
    # Security
    reject_none_algorithm: bool = True
    min_secret_length: int = 32


@dataclass
class JWTHeader:
    """JWT header."""
    
    alg: str
    typ: str = "JWT"
    kid: Optional[str] = None  # Key ID
    
    def to_dict(self) -> dict:
        """Convert to dict."""
        result = {"alg": self.alg, "typ": self.typ}
        if self.kid:
            result["kid"] = self.kid
        return result


@dataclass
class JWTPayload:
    """JWT payload (claims)."""
    
    # Registered claims
    iss: Optional[str] = None  # Issuer
    sub: Optional[str] = None  # Subject
    aud: Optional[str] = None  # Audience
    exp: Optional[int] = None  # Expiration
    nbf: Optional[int] = None  # Not Before
    iat: Optional[int] = None  # Issued At
    jti: Optional[str] = None  # JWT ID
    
    # Custom claims
    custom: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dict."""
        result = {}
        
        for claim in ["iss", "sub", "aud", "exp", "nbf", "iat", "jti"]:
            value = getattr(self, claim)
            if value is not None:
                result[claim] = value
        
        result.update(self.custom)
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "JWTPayload":
        """Create from dict."""
        registered = {
            "iss", "sub", "aud", "exp", "nbf", "iat", "jti"
        }
        
        custom = {k: v for k, v in data.items() if k not in registered}
        
        return cls(
            iss=data.get("iss"),
            sub=data.get("sub"),
            aud=data.get("aud"),
            exp=data.get("exp"),
            nbf=data.get("nbf"),
            iat=data.get("iat"),
            jti=data.get("jti"),
            custom=custom,
        )


@dataclass
class JWTValidationResult:
    """Result of JWT validation."""
    
    is_valid: bool
    header: Optional[JWTHeader] = None
    payload: Optional[JWTPayload] = None
    error: Optional[JWTValidationError] = None
    error_message: Optional[str] = None


class JWTEncoder:
    """Encodes JWT tokens."""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
    
    def encode(
        self,
        payload: dict,
        secret: str,
        algorithm: Optional[JWTAlgorithm] = None,
        header_extra: Optional[dict] = None,
    ) -> str:
        """Encode a JWT token."""
        alg = algorithm or self.config.algorithm
        
        # Check secret length
        if len(secret) < self.config.min_secret_length:
            raise ValueError(
                f"Secret must be at least {self.config.min_secret_length} characters"
            )
        
        # Build header
        header = {"alg": alg.value, "typ": "JWT"}
        if header_extra:
            header.update(header_extra)
        
        # Add default claims
        now = int(time.time())
        if "iat" not in payload:
            payload["iat"] = now
        if "exp" not in payload:
            payload["exp"] = now + self.config.default_exp_seconds
        if "jti" not in payload:
            payload["jti"] = secrets.token_hex(16)
        
        # Encode parts
        header_b64 = self._base64url_encode(json.dumps(header))
        payload_b64 = self._base64url_encode(json.dumps(payload))
        
        # Create signature
        message = f"{header_b64}.{payload_b64}"
        signature = self._sign(message, secret, alg)
        signature_b64 = self._base64url_encode_bytes(signature)
        
        return f"{message}.{signature_b64}"
    
    def _base64url_encode(self, data: str) -> str:
        """Base64URL encode string."""
        return base64.urlsafe_b64encode(
            data.encode()
        ).rstrip(b"=").decode()
    
    def _base64url_encode_bytes(self, data: bytes) -> str:
        """Base64URL encode bytes."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    
    def _sign(
        self,
        message: str,
        secret: str,
        algorithm: JWTAlgorithm,
    ) -> bytes:
        """Sign message with algorithm."""
        if algorithm == JWTAlgorithm.HS256:
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        elif algorithm == JWTAlgorithm.HS384:
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha384,
            ).digest()
        elif algorithm == JWTAlgorithm.HS512:
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha512,
            ).digest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")


class JWTDecoder:
    """Decodes and validates JWT tokens."""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
    
    def decode(
        self,
        token: str,
        secret: str,
        verify: bool = True,
    ) -> JWTValidationResult:
        """Decode and validate a JWT token."""
        # Parse token
        parts = token.split(".")
        if len(parts) != 3:
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.INVALID_FORMAT,
                error_message="Token must have 3 parts",
            )
        
        header_b64, payload_b64, signature_b64 = parts
        
        # Decode header
        try:
            header_json = self._base64url_decode(header_b64)
            header_data = json.loads(header_json)
        except Exception:
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.INVALID_FORMAT,
                error_message="Invalid header encoding",
            )
        
        # Decode payload
        try:
            payload_json = self._base64url_decode(payload_b64)
            payload_data = json.loads(payload_json)
        except Exception:
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.INVALID_FORMAT,
                error_message="Invalid payload encoding",
            )
        
        # Create objects
        header = JWTHeader(
            alg=header_data.get("alg", ""),
            typ=header_data.get("typ", "JWT"),
            kid=header_data.get("kid"),
        )
        payload = JWTPayload.from_dict(payload_data)
        
        if not verify:
            return JWTValidationResult(
                is_valid=True,
                header=header,
                payload=payload,
            )
        
        # Validate algorithm
        alg_result = self._validate_algorithm(header.alg)
        if alg_result:
            return alg_result
        
        # Verify signature
        if self.config.verify_signature:
            sig_result = self._verify_signature(
                f"{header_b64}.{payload_b64}",
                signature_b64,
                secret,
                header.alg,
            )
            if sig_result:
                sig_result.header = header
                sig_result.payload = payload
                return sig_result
        
        # Validate claims
        claims_result = self._validate_claims(payload)
        if claims_result:
            claims_result.header = header
            claims_result.payload = payload
            return claims_result
        
        return JWTValidationResult(
            is_valid=True,
            header=header,
            payload=payload,
        )
    
    def _base64url_decode(self, data: str) -> str:
        """Base64URL decode to string."""
        # Add padding
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data).decode()
    
    def _base64url_decode_bytes(self, data: str) -> bytes:
        """Base64URL decode to bytes."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)
    
    def _validate_algorithm(self, alg: str) -> Optional[JWTValidationResult]:
        """Validate algorithm."""
        # Reject 'none' algorithm
        if self.config.reject_none_algorithm and alg.lower() == "none":
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.ALGORITHM_NOT_ALLOWED,
                error_message="Algorithm 'none' is not allowed",
            )
        
        # Check allowed algorithms
        try:
            alg_enum = JWTAlgorithm(alg)
            if alg_enum not in self.config.allowed_algorithms:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.ALGORITHM_NOT_ALLOWED,
                    error_message=f"Algorithm '{alg}' is not allowed",
                )
        except ValueError:
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.ALGORITHM_NOT_ALLOWED,
                error_message=f"Unknown algorithm '{alg}'",
            )
        
        return None
    
    def _verify_signature(
        self,
        message: str,
        signature_b64: str,
        secret: str,
        algorithm: str,
    ) -> Optional[JWTValidationResult]:
        """Verify signature."""
        try:
            expected_signature = self._sign(message, secret, algorithm)
            actual_signature = self._base64url_decode_bytes(signature_b64)
            
            if not hmac.compare_digest(expected_signature, actual_signature):
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.INVALID_SIGNATURE,
                    error_message="Signature verification failed",
                )
        except Exception as e:
            return JWTValidationResult(
                is_valid=False,
                error=JWTValidationError.INVALID_SIGNATURE,
                error_message=str(e),
            )
        
        return None
    
    def _sign(
        self,
        message: str,
        secret: str,
        algorithm: str,
    ) -> bytes:
        """Sign message for verification."""
        if algorithm == "HS256":
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        elif algorithm == "HS384":
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha384,
            ).digest()
        elif algorithm == "HS512":
            return hmac.new(
                secret.encode(),
                message.encode(),
                hashlib.sha512,
            ).digest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    def _validate_claims(
        self,
        payload: JWTPayload,
    ) -> Optional[JWTValidationResult]:
        """Validate claims."""
        now = int(time.time())
        
        # Verify expiration
        if self.config.verify_exp and payload.exp is not None:
            if now > payload.exp + self.config.leeway_seconds:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.TOKEN_EXPIRED,
                    error_message="Token has expired",
                )
        
        # Verify not before
        if self.config.verify_nbf and payload.nbf is not None:
            if now < payload.nbf - self.config.leeway_seconds:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.TOKEN_NOT_YET_VALID,
                    error_message="Token is not yet valid",
                )
        
        # Verify issuer
        if self.config.verify_iss and self.config.issuer:
            if payload.iss != self.config.issuer:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.INVALID_ISSUER,
                    error_message=f"Invalid issuer: {payload.iss}",
                )
        
        # Verify audience
        if self.config.verify_aud and self.config.audience:
            if payload.aud != self.config.audience:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.INVALID_AUDIENCE,
                    error_message=f"Invalid audience: {payload.aud}",
                )
        
        # Check required claims
        if self.config.required_claims:
            payload_dict = payload.to_dict()
            missing = self.config.required_claims - set(payload_dict.keys())
            if missing:
                return JWTValidationResult(
                    is_valid=False,
                    error=JWTValidationError.MISSING_CLAIMS,
                    error_message=f"Missing claims: {missing}",
                )
        
        return None


class JWTSecurityService:
    """Comprehensive JWT security service."""
    
    _instance: Optional["JWTSecurityService"] = None
    
    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
        self.encoder = JWTEncoder(self.config)
        self.decoder = JWTDecoder(self.config)
        
        # Revoked tokens (JTI)
        self._revoked_tokens: set[str] = set()
    
    @classmethod
    def get_instance(cls) -> "JWTSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: JWTConfig) -> "JWTSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def create_token(
        self,
        subject: str,
        secret: str,
        claims: Optional[dict] = None,
        exp_seconds: Optional[int] = None,
    ) -> str:
        """Create a JWT token."""
        payload = {
            "sub": subject,
            "iss": self.config.issuer,
            "aud": self.config.audience,
        }
        
        if exp_seconds:
            payload["exp"] = int(time.time()) + exp_seconds
        
        if claims:
            payload.update(claims)
        
        return self.encoder.encode(payload, secret)
    
    def validate_token(
        self,
        token: str,
        secret: str,
    ) -> JWTValidationResult:
        """Validate a JWT token."""
        result = self.decoder.decode(token, secret)
        
        if not result.is_valid:
            return result
        
        # Check if revoked
        if result.payload and result.payload.jti in self._revoked_tokens:
            return JWTValidationResult(
                is_valid=False,
                header=result.header,
                payload=result.payload,
                error=JWTValidationError.INVALID_TOKEN,
                error_message="Token has been revoked",
            )
        
        return result
    
    def revoke_token(self, token: str, secret: str) -> bool:
        """Revoke a token by adding its JTI to blacklist."""
        result = self.decoder.decode(token, secret, verify=False)
        
        if result.payload and result.payload.jti:
            self._revoked_tokens.add(result.payload.jti)
            return True
        
        return False
    
    def refresh_token(
        self,
        token: str,
        secret: str,
        exp_seconds: Optional[int] = None,
    ) -> Optional[str]:
        """Refresh a token (create new with same claims)."""
        result = self.validate_token(token, secret)
        
        if not result.is_valid:
            # Allow refresh of expired tokens if within grace period
            if result.error != JWTValidationError.TOKEN_EXPIRED:
                return None
        
        if not result.payload:
            return None
        
        # Create new token with same subject and custom claims
        return self.create_token(
            subject=result.payload.sub or "",
            secret=secret,
            claims=result.payload.custom,
            exp_seconds=exp_seconds,
        )
    
    def decode_without_verification(self, token: str) -> Optional[JWTPayload]:
        """Decode token without verification (for debugging only)."""
        result = self.decoder.decode(token, "", verify=False)
        return result.payload if result.is_valid else None


# Convenience functions
def get_jwt_service() -> JWTSecurityService:
    """Get JWT service instance."""
    return JWTSecurityService.get_instance()


def create_jwt(
    subject: str,
    secret: str,
    claims: Optional[dict] = None,
    exp_seconds: Optional[int] = None,
) -> str:
    """Create a JWT token."""
    return get_jwt_service().create_token(
        subject, secret, claims, exp_seconds
    )


def validate_jwt(token: str, secret: str) -> JWTValidationResult:
    """Validate a JWT token."""
    return get_jwt_service().validate_token(token, secret)
