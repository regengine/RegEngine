"""
SEC-053: Cryptographic Signing Security Module.

Provides secure cryptographic signing with:
- HMAC-based message authentication
- RSA digital signatures
- Signature verification
- Key management
- Timestamp-based replay protection
"""

import hashlib
import hmac
import secrets
import time
import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta


class SignatureAlgorithm(Enum):
    """Supported signature algorithms."""
    HMAC_SHA256 = "hmac-sha256"
    HMAC_SHA384 = "hmac-sha384"
    HMAC_SHA512 = "hmac-sha512"


class SignatureError(Exception):
    """Base exception for signature operations."""
    pass


class InvalidSignatureError(SignatureError):
    """Raised when signature verification fails."""
    pass


class ExpiredSignatureError(SignatureError):
    """Raised when signature has expired."""
    pass


class KeyNotFoundError(SignatureError):
    """Raised when signing key is not found."""
    pass


@dataclass
class SignatureConfig:
    """Configuration for signature operations."""
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256
    timestamp_tolerance_seconds: int = 300  # 5 minutes
    include_timestamp: bool = True
    key_min_length: int = 32
    encoding: str = "utf-8"


@dataclass
class SignedMessage:
    """Represents a signed message with metadata."""
    message: bytes
    signature: str
    algorithm: SignatureAlgorithm
    timestamp: Optional[float] = None
    key_id: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of signature verification."""
    valid: bool
    message: Optional[bytes] = None
    error: Optional[str] = None
    verified_at: datetime = field(default_factory=datetime.utcnow)


class HMACGenerator:
    """Generates HMAC signatures for messages."""
    
    HASH_ALGORITHMS = {
        SignatureAlgorithm.HMAC_SHA256: hashlib.sha256,
        SignatureAlgorithm.HMAC_SHA384: hashlib.sha384,
        SignatureAlgorithm.HMAC_SHA512: hashlib.sha512,
    }
    
    def __init__(self, config: Optional[SignatureConfig] = None):
        """Initialize HMAC generator."""
        self.config = config or SignatureConfig()
    
    def generate(
        self,
        message: Union[str, bytes],
        key: Union[str, bytes],
        algorithm: Optional[SignatureAlgorithm] = None
    ) -> str:
        """Generate HMAC signature for message."""
        algo = algorithm or self.config.algorithm
        
        # Normalize inputs
        if isinstance(message, str):
            message = message.encode(self.config.encoding)
        if isinstance(key, str):
            key = key.encode(self.config.encoding)
        
        # Validate key length
        if len(key) < self.config.key_min_length:
            raise ValueError(
                f"Key must be at least {self.config.key_min_length} bytes"
            )
        
        # Get hash function
        hash_func = self.HASH_ALGORITHMS.get(algo)
        if not hash_func:
            raise ValueError(f"Unsupported algorithm: {algo}")
        
        # Generate HMAC
        signature = hmac.new(key, message, hash_func).digest()
        return base64.urlsafe_b64encode(signature).decode("ascii")
    
    def verify(
        self,
        message: Union[str, bytes],
        signature: str,
        key: Union[str, bytes],
        algorithm: Optional[SignatureAlgorithm] = None
    ) -> bool:
        """Verify HMAC signature."""
        try:
            expected = self.generate(message, key, algorithm)
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False


class TimestampedSigner:
    """Signs messages with timestamps for replay protection."""
    
    SEPARATOR = b"."
    
    def __init__(
        self,
        key: Union[str, bytes],
        config: Optional[SignatureConfig] = None
    ):
        """Initialize timestamped signer."""
        self.config = config or SignatureConfig()
        self._hmac = HMACGenerator(self.config)
        
        if isinstance(key, str):
            key = key.encode(self.config.encoding)
        
        if len(key) < self.config.key_min_length:
            raise ValueError(
                f"Key must be at least {self.config.key_min_length} bytes"
            )
        
        self._key = key
    
    def sign(self, message: Union[str, bytes]) -> SignedMessage:
        """Sign message with timestamp."""
        if isinstance(message, str):
            message = message.encode(self.config.encoding)
        
        timestamp = time.time()
        timestamp_bytes = str(timestamp).encode("ascii")
        
        # Combine message and timestamp
        data = message + self.SEPARATOR + timestamp_bytes
        
        # Generate signature
        signature = self._hmac.generate(data, self._key)
        
        return SignedMessage(
            message=message,
            signature=signature,
            algorithm=self.config.algorithm,
            timestamp=timestamp
        )
    
    def verify(
        self,
        message: Union[str, bytes],
        signature: str,
        timestamp: float
    ) -> VerificationResult:
        """Verify timestamped signature."""
        if isinstance(message, str):
            message = message.encode(self.config.encoding)
        
        # Check timestamp freshness
        current_time = time.time()
        age = abs(current_time - timestamp)
        
        if age > self.config.timestamp_tolerance_seconds:
            return VerificationResult(
                valid=False,
                error=f"Signature expired (age: {age:.1f}s)"
            )
        
        # Reconstruct signed data
        timestamp_bytes = str(timestamp).encode("ascii")
        data = message + self.SEPARATOR + timestamp_bytes
        
        # Verify signature
        if self._hmac.verify(data, signature, self._key):
            return VerificationResult(valid=True, message=message)
        
        return VerificationResult(valid=False, error="Invalid signature")
    
    def verify_signed_message(self, signed: SignedMessage) -> VerificationResult:
        """Verify a SignedMessage object."""
        if signed.timestamp is None:
            return VerificationResult(
                valid=False,
                error="Missing timestamp"
            )
        
        return self.verify(signed.message, signed.signature, signed.timestamp)


class KeyStore:
    """Secure storage for signing keys."""
    
    def __init__(self):
        """Initialize key store."""
        self._keys: Dict[str, bytes] = {}
        self._key_metadata: Dict[str, Dict[str, Any]] = {}
    
    def add_key(
        self,
        key_id: str,
        key: Union[str, bytes],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a key to the store."""
        if isinstance(key, str):
            key = key.encode("utf-8")
        
        self._keys[key_id] = key
        self._key_metadata[key_id] = metadata or {}
        self._key_metadata[key_id]["added_at"] = datetime.utcnow().isoformat()
    
    def get_key(self, key_id: str) -> bytes:
        """Get a key by ID."""
        if key_id not in self._keys:
            raise KeyNotFoundError(f"Key not found: {key_id}")
        return self._keys[key_id]
    
    def remove_key(self, key_id: str) -> bool:
        """Remove a key from the store."""
        if key_id in self._keys:
            del self._keys[key_id]
            del self._key_metadata[key_id]
            return True
        return False
    
    def has_key(self, key_id: str) -> bool:
        """Check if key exists."""
        return key_id in self._keys
    
    def list_keys(self) -> list:
        """List all key IDs."""
        return list(self._keys.keys())
    
    def get_metadata(self, key_id: str) -> Dict[str, Any]:
        """Get key metadata."""
        if key_id not in self._key_metadata:
            raise KeyNotFoundError(f"Key not found: {key_id}")
        return self._key_metadata[key_id].copy()
    
    def generate_key(self, key_id: str, length: int = 32) -> bytes:
        """Generate and store a new random key."""
        key = secrets.token_bytes(length)
        self.add_key(key_id, key, {"generated": True, "length": length})
        return key


class MultiKeySigner:
    """Signer that supports multiple keys with key rotation."""
    
    def __init__(self, config: Optional[SignatureConfig] = None):
        """Initialize multi-key signer."""
        self.config = config or SignatureConfig()
        self._key_store = KeyStore()
        self._current_key_id: Optional[str] = None
        self._hmac = HMACGenerator(self.config)
    
    def add_key(
        self,
        key_id: str,
        key: Union[str, bytes],
        set_current: bool = False
    ) -> None:
        """Add a signing key."""
        self._key_store.add_key(key_id, key)
        if set_current or self._current_key_id is None:
            self._current_key_id = key_id
    
    def set_current_key(self, key_id: str) -> None:
        """Set the current signing key."""
        if not self._key_store.has_key(key_id):
            raise KeyNotFoundError(f"Key not found: {key_id}")
        self._current_key_id = key_id
    
    def sign(
        self,
        message: Union[str, bytes],
        key_id: Optional[str] = None
    ) -> SignedMessage:
        """Sign message with specified or current key."""
        kid = key_id or self._current_key_id
        if kid is None:
            raise KeyNotFoundError("No signing key available")
        
        key = self._key_store.get_key(kid)
        
        if isinstance(message, str):
            message = message.encode(self.config.encoding)
        
        timestamp = time.time() if self.config.include_timestamp else None
        
        # Build data to sign
        data = message
        if timestamp is not None:
            data = message + b"." + str(timestamp).encode("ascii")
        
        signature = self._hmac.generate(data, key)
        
        return SignedMessage(
            message=message,
            signature=signature,
            algorithm=self.config.algorithm,
            timestamp=timestamp,
            key_id=kid
        )
    
    def verify(self, signed: SignedMessage) -> VerificationResult:
        """Verify a signed message."""
        if signed.key_id is None:
            return VerificationResult(
                valid=False,
                error="Missing key ID"
            )
        
        try:
            key = self._key_store.get_key(signed.key_id)
        except KeyNotFoundError as e:
            return VerificationResult(valid=False, error=str(e))
        
        # Check timestamp if included
        if signed.timestamp is not None:
            age = abs(time.time() - signed.timestamp)
            if age > self.config.timestamp_tolerance_seconds:
                return VerificationResult(
                    valid=False,
                    error=f"Signature expired (age: {age:.1f}s)"
                )
        
        # Rebuild data
        data = signed.message
        if signed.timestamp is not None:
            data = signed.message + b"." + str(signed.timestamp).encode("ascii")
        
        if self._hmac.verify(data, signed.signature, key):
            return VerificationResult(valid=True, message=signed.message)
        
        return VerificationResult(valid=False, error="Invalid signature")
    
    def rotate_key(self, new_key_id: str, new_key: Union[str, bytes]) -> str:
        """Rotate to a new key, keeping old keys for verification."""
        old_key_id = self._current_key_id
        self.add_key(new_key_id, new_key, set_current=True)
        return old_key_id or ""


class RequestSigner:
    """Signs HTTP-like requests for API authentication."""
    
    def __init__(
        self,
        key: Union[str, bytes],
        config: Optional[SignatureConfig] = None
    ):
        """Initialize request signer."""
        self.config = config or SignatureConfig()
        self._hmac = HMACGenerator(self.config)
        
        if isinstance(key, str):
            key = key.encode(self.config.encoding)
        self._key = key
    
    def sign_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Union[str, bytes]] = None
    ) -> Dict[str, str]:
        """Sign a request and return signature headers."""
        timestamp = str(int(time.time()))
        
        # Build canonical request
        canonical_parts = [
            method.upper(),
            path,
            timestamp
        ]
        
        # Add sorted headers
        if headers:
            signed_headers = sorted(headers.keys())
            for header in signed_headers:
                canonical_parts.append(f"{header.lower()}:{headers[header]}")
        else:
            signed_headers = []
        
        # Add body hash
        if body:
            if isinstance(body, str):
                body = body.encode(self.config.encoding)
            body_hash = hashlib.sha256(body).hexdigest()
            canonical_parts.append(body_hash)
        
        canonical_request = "\n".join(canonical_parts)
        
        # Generate signature
        signature = self._hmac.generate(canonical_request, self._key)
        
        return {
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Signed-Headers": ";".join(signed_headers) if signed_headers else ""
        }
    
    def verify_request(
        self,
        method: str,
        path: str,
        signature: str,
        timestamp: str,
        signed_headers_str: str = "",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Union[str, bytes]] = None
    ) -> VerificationResult:
        """Verify a signed request."""
        # Check timestamp
        try:
            ts = int(timestamp)
            age = abs(time.time() - ts)
            if age > self.config.timestamp_tolerance_seconds:
                return VerificationResult(
                    valid=False,
                    error=f"Request expired (age: {age:.1f}s)"
                )
        except ValueError:
            return VerificationResult(
                valid=False,
                error="Invalid timestamp format"
            )
        
        # Rebuild canonical request
        canonical_parts = [
            method.upper(),
            path,
            timestamp
        ]
        
        # Add headers
        if signed_headers_str:
            signed_headers = signed_headers_str.split(";")
            headers = headers or {}
            for header in signed_headers:
                value = headers.get(header, headers.get(header.lower(), ""))
                canonical_parts.append(f"{header.lower()}:{value}")
        
        # Add body hash
        if body:
            if isinstance(body, str):
                body = body.encode(self.config.encoding)
            body_hash = hashlib.sha256(body).hexdigest()
            canonical_parts.append(body_hash)
        
        canonical_request = "\n".join(canonical_parts)
        
        # Verify
        if self._hmac.verify(canonical_request, signature, self._key):
            return VerificationResult(valid=True)
        
        return VerificationResult(valid=False, error="Invalid signature")


class CryptoSigningService:
    """Main service for cryptographic signing operations."""
    
    _instance: Optional["CryptoSigningService"] = None
    
    def __new__(cls) -> "CryptoSigningService":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize service."""
        if self._initialized:
            return
        
        self._config = SignatureConfig()
        self._key_store = KeyStore()
        self._multi_signer: Optional[MultiKeySigner] = None
        self._initialized = True
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance."""
        cls._instance = None
    
    def configure(self, config: SignatureConfig) -> None:
        """Update configuration."""
        self._config = config
    
    def get_config(self) -> SignatureConfig:
        """Get current configuration."""
        return self._config
    
    def get_hmac_generator(self) -> HMACGenerator:
        """Get HMAC generator instance."""
        return HMACGenerator(self._config)
    
    def get_timestamped_signer(self, key: Union[str, bytes]) -> TimestampedSigner:
        """Get timestamped signer instance."""
        return TimestampedSigner(key, self._config)
    
    def get_multi_key_signer(self) -> MultiKeySigner:
        """Get or create multi-key signer."""
        if self._multi_signer is None:
            self._multi_signer = MultiKeySigner(self._config)
        return self._multi_signer
    
    def get_request_signer(self, key: Union[str, bytes]) -> RequestSigner:
        """Get request signer instance."""
        return RequestSigner(key, self._config)
    
    def get_key_store(self) -> KeyStore:
        """Get key store instance."""
        return self._key_store
    
    def quick_sign(
        self,
        message: Union[str, bytes],
        key: Union[str, bytes]
    ) -> str:
        """Quick HMAC signature generation."""
        return self.get_hmac_generator().generate(message, key)
    
    def quick_verify(
        self,
        message: Union[str, bytes],
        signature: str,
        key: Union[str, bytes]
    ) -> bool:
        """Quick HMAC signature verification."""
        return self.get_hmac_generator().verify(message, signature, key)


# Convenience functions
def get_signing_service() -> CryptoSigningService:
    """Get the crypto signing service singleton."""
    return CryptoSigningService()


def sign_message(message: Union[str, bytes], key: Union[str, bytes]) -> str:
    """Sign a message with HMAC-SHA256."""
    return get_signing_service().quick_sign(message, key)


def verify_signature(
    message: Union[str, bytes],
    signature: str,
    key: Union[str, bytes]
) -> bool:
    """Verify an HMAC signature."""
    return get_signing_service().quick_verify(message, signature, key)
