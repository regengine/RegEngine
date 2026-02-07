"""
SEC-024: Digital Signature Implementation.

Provides comprehensive digital signature functionality:
- RSA signatures (PSS, PKCS#1 v1.5)
- ECDSA signatures (P-256, P-384, P-521)
- EdDSA signatures (Ed25519)
- Signature verification
- Key pair generation
- Document signing workflows
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union, Protocol

# Cryptography imports
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import (
        rsa,
        ec,
        ed25519,
        padding,
    )
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateKey,
        EllipticCurvePublicKey,
        SECP256R1,
        SECP384R1,
        SECP521R1,
        ECDSA,
    )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    from cryptography.x509 import load_pem_x509_certificate
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class SignatureError(Exception):
    """Base exception for signature operations."""
    pass


class SignatureVerificationError(SignatureError):
    """Raised when signature verification fails."""
    pass


class KeyGenerationError(SignatureError):
    """Raised when key generation fails."""
    pass


class InvalidKeyError(SignatureError):
    """Raised when key is invalid or unsupported."""
    pass


# =============================================================================
# Enums
# =============================================================================

class SignatureAlgorithm(str, Enum):
    """Supported signature algorithms."""
    RSA_PSS_SHA256 = "rsa-pss-sha256"
    RSA_PSS_SHA384 = "rsa-pss-sha384"
    RSA_PSS_SHA512 = "rsa-pss-sha512"
    RSA_PKCS1_SHA256 = "rsa-pkcs1-sha256"
    RSA_PKCS1_SHA384 = "rsa-pkcs1-sha384"
    RSA_PKCS1_SHA512 = "rsa-pkcs1-sha512"
    ECDSA_P256_SHA256 = "ecdsa-p256-sha256"
    ECDSA_P384_SHA384 = "ecdsa-p384-sha384"
    ECDSA_P521_SHA512 = "ecdsa-p521-sha512"
    ED25519 = "ed25519"


class KeySize(int, Enum):
    """RSA key sizes."""
    RSA_2048 = 2048
    RSA_3072 = 3072
    RSA_4096 = 4096


class HashAlgorithm(str, Enum):
    """Hash algorithms for signatures."""
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class KeyPair:
    """Cryptographic key pair."""
    private_key: bytes  # PEM encoded
    public_key: bytes  # PEM encoded
    algorithm: SignatureAlgorithm
    key_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        if not self.key_id:
            self.key_id = secrets.token_hex(16)


@dataclass
class Signature:
    """Digital signature with metadata."""
    value: bytes
    algorithm: SignatureAlgorithm
    key_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_base64(self) -> str:
        """Encode signature as base64."""
        return base64.b64encode(self.value).decode('utf-8')
    
    @classmethod
    def from_base64(
        cls,
        encoded: str,
        algorithm: SignatureAlgorithm,
        key_id: str = "",
    ) -> "Signature":
        """Create signature from base64 encoded value."""
        return cls(
            value=base64.b64decode(encoded),
            algorithm=algorithm,
            key_id=key_id,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "value": self.to_base64(),
            "algorithm": self.algorithm.value,
            "key_id": self.key_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SignedDocument:
    """Document with digital signature."""
    content: bytes
    content_hash: str
    signature: Signature
    signer_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content_hash": self.content_hash,
            "signature": self.signature.to_dict(),
            "signer_id": self.signer_id,
            "metadata": self.metadata,
        }


@dataclass
class VerificationResult:
    """Result of signature verification."""
    valid: bool
    algorithm: SignatureAlgorithm
    key_id: str = ""
    error: Optional[str] = None
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Key Generator
# =============================================================================

class KeyGenerator:
    """Generates cryptographic key pairs for signatures."""
    
    @staticmethod
    def generate_rsa(
        key_size: KeySize = KeySize.RSA_4096,
        algorithm: SignatureAlgorithm = SignatureAlgorithm.RSA_PSS_SHA256,
    ) -> KeyPair:
        """
        Generate RSA key pair.
        
        Args:
            key_size: RSA key size (2048, 3072, 4096)
            algorithm: Signature algorithm to use
            
        Returns:
            KeyPair with PEM-encoded keys
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise KeyGenerationError("cryptography library not installed")
        
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size.value,
                backend=default_backend(),
            )
            
            # Serialize keys
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            
            return KeyPair(
                private_key=private_pem,
                public_key=public_pem,
                algorithm=algorithm,
            )
            
        except Exception as e:
            raise KeyGenerationError(f"Failed to generate RSA key: {e}")
    
    @staticmethod
    def generate_ecdsa(
        curve: str = "P-256",
        algorithm: Optional[SignatureAlgorithm] = None,
    ) -> KeyPair:
        """
        Generate ECDSA key pair.
        
        Args:
            curve: Elliptic curve (P-256, P-384, P-521)
            algorithm: Signature algorithm (auto-selected if not provided)
            
        Returns:
            KeyPair with PEM-encoded keys
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise KeyGenerationError("cryptography library not installed")
        
        # Select curve
        curve_map = {
            "P-256": (SECP256R1(), SignatureAlgorithm.ECDSA_P256_SHA256),
            "P-384": (SECP384R1(), SignatureAlgorithm.ECDSA_P384_SHA384),
            "P-521": (SECP521R1(), SignatureAlgorithm.ECDSA_P521_SHA512),
        }
        
        if curve not in curve_map:
            raise KeyGenerationError(f"Unsupported curve: {curve}")
        
        ec_curve, default_algo = curve_map[curve]
        
        if algorithm is None:
            algorithm = default_algo
        
        try:
            private_key = ec.generate_private_key(ec_curve, default_backend())
            
            # Serialize keys
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            
            return KeyPair(
                private_key=private_pem,
                public_key=public_pem,
                algorithm=algorithm,
            )
            
        except Exception as e:
            raise KeyGenerationError(f"Failed to generate ECDSA key: {e}")
    
    @staticmethod
    def generate_ed25519() -> KeyPair:
        """
        Generate Ed25519 key pair.
        
        Returns:
            KeyPair with PEM-encoded keys
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise KeyGenerationError("cryptography library not installed")
        
        try:
            private_key = ed25519.Ed25519PrivateKey.generate()
            
            # Serialize keys
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            
            return KeyPair(
                private_key=private_pem,
                public_key=public_pem,
                algorithm=SignatureAlgorithm.ED25519,
            )
            
        except Exception as e:
            raise KeyGenerationError(f"Failed to generate Ed25519 key: {e}")


# =============================================================================
# Signer Implementation
# =============================================================================

class Signer:
    """Digital signature creation and verification."""
    
    def __init__(self, key_id: str = ""):
        """Initialize signer."""
        self.key_id = key_id
    
    def _load_private_key(self, pem_data: bytes):
        """Load private key from PEM."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise SignatureError("cryptography library not installed")
        
        return serialization.load_pem_private_key(
            pem_data,
            password=None,
            backend=default_backend(),
        )
    
    def _load_public_key(self, pem_data: bytes):
        """Load public key from PEM."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise SignatureError("cryptography library not installed")
        
        return serialization.load_pem_public_key(
            pem_data,
            backend=default_backend(),
        )
    
    def _get_hash_algorithm(self, algorithm: SignatureAlgorithm):
        """Get hash algorithm for signature algorithm."""
        if "sha512" in algorithm.value:
            return hashes.SHA512()
        elif "sha384" in algorithm.value:
            return hashes.SHA384()
        else:
            return hashes.SHA256()
    
    def sign(
        self,
        data: bytes,
        private_key: bytes,
        algorithm: SignatureAlgorithm,
    ) -> Signature:
        """
        Create digital signature.
        
        Args:
            data: Data to sign
            private_key: PEM-encoded private key
            algorithm: Signature algorithm
            
        Returns:
            Signature object
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise SignatureError("cryptography library not installed")
        
        key = self._load_private_key(private_key)
        
        try:
            if algorithm in {
                SignatureAlgorithm.RSA_PSS_SHA256,
                SignatureAlgorithm.RSA_PSS_SHA384,
                SignatureAlgorithm.RSA_PSS_SHA512,
            }:
                signature = self._sign_rsa_pss(key, data, algorithm)
            elif algorithm in {
                SignatureAlgorithm.RSA_PKCS1_SHA256,
                SignatureAlgorithm.RSA_PKCS1_SHA384,
                SignatureAlgorithm.RSA_PKCS1_SHA512,
            }:
                signature = self._sign_rsa_pkcs1(key, data, algorithm)
            elif algorithm in {
                SignatureAlgorithm.ECDSA_P256_SHA256,
                SignatureAlgorithm.ECDSA_P384_SHA384,
                SignatureAlgorithm.ECDSA_P521_SHA512,
            }:
                signature = self._sign_ecdsa(key, data, algorithm)
            elif algorithm == SignatureAlgorithm.ED25519:
                signature = self._sign_ed25519(key, data)
            else:
                raise SignatureError(f"Unsupported algorithm: {algorithm}")
            
            return Signature(
                value=signature,
                algorithm=algorithm,
                key_id=self.key_id,
            )
            
        except Exception as e:
            if isinstance(e, SignatureError):
                raise
            raise SignatureError(f"Signing failed: {e}")
    
    def _sign_rsa_pss(
        self,
        key: RSAPrivateKey,
        data: bytes,
        algorithm: SignatureAlgorithm,
    ) -> bytes:
        """Sign with RSA-PSS."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        return key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hash_algo),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hash_algo,
        )
    
    def _sign_rsa_pkcs1(
        self,
        key: RSAPrivateKey,
        data: bytes,
        algorithm: SignatureAlgorithm,
    ) -> bytes:
        """Sign with RSA PKCS#1 v1.5."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        return key.sign(data, padding.PKCS1v15(), hash_algo)
    
    def _sign_ecdsa(
        self,
        key: EllipticCurvePrivateKey,
        data: bytes,
        algorithm: SignatureAlgorithm,
    ) -> bytes:
        """Sign with ECDSA."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        return key.sign(data, ECDSA(hash_algo))
    
    def _sign_ed25519(self, key: Ed25519PrivateKey, data: bytes) -> bytes:
        """Sign with Ed25519."""
        return key.sign(data)
    
    def verify(
        self,
        data: bytes,
        signature: Signature,
        public_key: bytes,
    ) -> VerificationResult:
        """
        Verify digital signature.
        
        Args:
            data: Original data
            signature: Signature to verify
            public_key: PEM-encoded public key
            
        Returns:
            VerificationResult
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            return VerificationResult(
                valid=False,
                algorithm=signature.algorithm,
                error="cryptography library not installed",
            )
        
        key = self._load_public_key(public_key)
        algorithm = signature.algorithm
        
        try:
            if algorithm in {
                SignatureAlgorithm.RSA_PSS_SHA256,
                SignatureAlgorithm.RSA_PSS_SHA384,
                SignatureAlgorithm.RSA_PSS_SHA512,
            }:
                self._verify_rsa_pss(key, data, signature.value, algorithm)
            elif algorithm in {
                SignatureAlgorithm.RSA_PKCS1_SHA256,
                SignatureAlgorithm.RSA_PKCS1_SHA384,
                SignatureAlgorithm.RSA_PKCS1_SHA512,
            }:
                self._verify_rsa_pkcs1(key, data, signature.value, algorithm)
            elif algorithm in {
                SignatureAlgorithm.ECDSA_P256_SHA256,
                SignatureAlgorithm.ECDSA_P384_SHA384,
                SignatureAlgorithm.ECDSA_P521_SHA512,
            }:
                self._verify_ecdsa(key, data, signature.value, algorithm)
            elif algorithm == SignatureAlgorithm.ED25519:
                self._verify_ed25519(key, data, signature.value)
            else:
                return VerificationResult(
                    valid=False,
                    algorithm=algorithm,
                    key_id=signature.key_id,
                    error=f"Unsupported algorithm: {algorithm}",
                )
            
            return VerificationResult(
                valid=True,
                algorithm=algorithm,
                key_id=signature.key_id,
            )
            
        except InvalidSignature:
            return VerificationResult(
                valid=False,
                algorithm=algorithm,
                key_id=signature.key_id,
                error="Invalid signature",
            )
        except Exception as e:
            return VerificationResult(
                valid=False,
                algorithm=algorithm,
                key_id=signature.key_id,
                error=str(e),
            )
    
    def _verify_rsa_pss(
        self,
        key: RSAPublicKey,
        data: bytes,
        signature: bytes,
        algorithm: SignatureAlgorithm,
    ) -> None:
        """Verify RSA-PSS signature."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        key.verify(
            signature,
            data,
            padding.PSS(
                mgf=padding.MGF1(hash_algo),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hash_algo,
        )
    
    def _verify_rsa_pkcs1(
        self,
        key: RSAPublicKey,
        data: bytes,
        signature: bytes,
        algorithm: SignatureAlgorithm,
    ) -> None:
        """Verify RSA PKCS#1 v1.5 signature."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        key.verify(signature, data, padding.PKCS1v15(), hash_algo)
    
    def _verify_ecdsa(
        self,
        key: EllipticCurvePublicKey,
        data: bytes,
        signature: bytes,
        algorithm: SignatureAlgorithm,
    ) -> None:
        """Verify ECDSA signature."""
        hash_algo = self._get_hash_algorithm(algorithm)
        
        key.verify(signature, data, ECDSA(hash_algo))
    
    def _verify_ed25519(
        self,
        key: Ed25519PublicKey,
        data: bytes,
        signature: bytes,
    ) -> None:
        """Verify Ed25519 signature."""
        key.verify(signature, data)


# =============================================================================
# Document Signer
# =============================================================================

class DocumentSigner:
    """
    High-level document signing workflow.
    
    Handles:
    - Document hashing
    - Signature creation
    - Signature verification
    - Metadata attachment
    """
    
    def __init__(
        self,
        key_pair: Optional[KeyPair] = None,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ):
        """
        Initialize document signer.
        
        Args:
            key_pair: Key pair for signing (optional for verification only)
            hash_algorithm: Hash algorithm for document digest
        """
        self.key_pair = key_pair
        self.hash_algorithm = hash_algorithm
        self.signer = Signer(key_id=key_pair.key_id if key_pair else "")
    
    def _compute_hash(self, content: bytes) -> str:
        """Compute content hash."""
        if self.hash_algorithm == HashAlgorithm.SHA512:
            return hashlib.sha512(content).hexdigest()
        elif self.hash_algorithm == HashAlgorithm.SHA384:
            return hashlib.sha384(content).hexdigest()
        else:
            return hashlib.sha256(content).hexdigest()
    
    def sign_document(
        self,
        content: bytes,
        signer_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SignedDocument:
        """
        Sign a document.
        
        Args:
            content: Document content
            signer_id: Identifier of the signer
            metadata: Additional metadata
            
        Returns:
            SignedDocument with signature
        """
        if self.key_pair is None:
            raise SignatureError("No key pair configured for signing")
        
        # Compute hash
        content_hash = self._compute_hash(content)
        
        # Sign the hash
        signature = self.signer.sign(
            content_hash.encode('utf-8'),
            self.key_pair.private_key,
            self.key_pair.algorithm,
        )
        
        return SignedDocument(
            content=content,
            content_hash=content_hash,
            signature=signature,
            signer_id=signer_id,
            metadata=metadata or {},
        )
    
    def verify_document(
        self,
        document: SignedDocument,
        public_key: Optional[bytes] = None,
    ) -> VerificationResult:
        """
        Verify a signed document.
        
        Args:
            document: Signed document to verify
            public_key: Public key for verification (uses key_pair if not provided)
            
        Returns:
            VerificationResult
        """
        # Use provided key or key from key_pair
        if public_key is None:
            if self.key_pair is None:
                raise SignatureError("No public key available for verification")
            public_key = self.key_pair.public_key
        
        # Verify content hash
        computed_hash = self._compute_hash(document.content)
        if computed_hash != document.content_hash:
            return VerificationResult(
                valid=False,
                algorithm=document.signature.algorithm,
                key_id=document.signature.key_id,
                error="Content hash mismatch",
            )
        
        # Verify signature
        return self.signer.verify(
            document.content_hash.encode('utf-8'),
            document.signature,
            public_key,
        )
    
    def sign_json(
        self,
        data: Dict[str, Any],
        signer_id: str = "",
    ) -> Dict[str, Any]:
        """
        Sign JSON data.
        
        Args:
            data: JSON data to sign
            signer_id: Identifier of the signer
            
        Returns:
            Signed JSON with signature embedded
        """
        # Serialize JSON canonically
        content = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
        
        signed = self.sign_document(content, signer_id)
        
        return {
            "data": data,
            "signature": signed.signature.to_dict(),
            "content_hash": signed.content_hash,
            "signer_id": signer_id,
        }
    
    def verify_json(
        self,
        signed_data: Dict[str, Any],
        public_key: Optional[bytes] = None,
    ) -> VerificationResult:
        """
        Verify signed JSON data.
        
        Args:
            signed_data: Signed JSON with embedded signature
            public_key: Public key for verification
            
        Returns:
            VerificationResult
        """
        # Extract components
        data = signed_data.get("data", {})
        sig_dict = signed_data.get("signature", {})
        content_hash = signed_data.get("content_hash", "")
        
        # Recreate content
        content = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
        
        # Recreate signature
        signature = Signature.from_base64(
            sig_dict.get("value", ""),
            SignatureAlgorithm(sig_dict.get("algorithm", "rsa-pss-sha256")),
            sig_dict.get("key_id", ""),
        )
        
        # Create signed document
        document = SignedDocument(
            content=content,
            content_hash=content_hash,
            signature=signature,
            signer_id=signed_data.get("signer_id", ""),
        )
        
        return self.verify_document(document, public_key)


# =============================================================================
# Signature Service
# =============================================================================

class SignatureService:
    """
    High-level signature service for application use.
    
    Provides:
    - Key management
    - Signing operations
    - Verification
    - Algorithm selection
    """
    
    _instance: Optional["SignatureService"] = None
    _configured: bool = False
    
    def __init__(
        self,
        default_algorithm: SignatureAlgorithm = SignatureAlgorithm.ECDSA_P256_SHA256,
    ):
        """
        Initialize signature service.
        
        Args:
            default_algorithm: Default signature algorithm
        """
        self.default_algorithm = default_algorithm
        self._key_pairs: Dict[str, KeyPair] = {}
        self._signer = Signer()
    
    @classmethod
    def configure(
        cls,
        default_algorithm: SignatureAlgorithm = SignatureAlgorithm.ECDSA_P256_SHA256,
    ) -> "SignatureService":
        """Configure the global signature service."""
        cls._instance = cls(default_algorithm=default_algorithm)
        cls._configured = True
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "SignatureService":
        """Get the configured instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def generate_key_pair(
        self,
        algorithm: Optional[SignatureAlgorithm] = None,
        key_id: Optional[str] = None,
    ) -> KeyPair:
        """
        Generate a new key pair.
        
        Args:
            algorithm: Signature algorithm (uses default if not provided)
            key_id: Optional key identifier
            
        Returns:
            Generated KeyPair
        """
        algo = algorithm or self.default_algorithm
        
        if algo.value.startswith("rsa"):
            key_pair = KeyGenerator.generate_rsa(algorithm=algo)
        elif algo.value.startswith("ecdsa"):
            # Map algorithm to curve
            if "p256" in algo.value:
                key_pair = KeyGenerator.generate_ecdsa("P-256", algo)
            elif "p384" in algo.value:
                key_pair = KeyGenerator.generate_ecdsa("P-384", algo)
            elif "p521" in algo.value:
                key_pair = KeyGenerator.generate_ecdsa("P-521", algo)
            else:
                key_pair = KeyGenerator.generate_ecdsa("P-256", algo)
        elif algo == SignatureAlgorithm.ED25519:
            key_pair = KeyGenerator.generate_ed25519()
        else:
            raise InvalidKeyError(f"Unsupported algorithm: {algo}")
        
        if key_id:
            key_pair.key_id = key_id
        
        # Store key pair
        self._key_pairs[key_pair.key_id] = key_pair
        
        return key_pair
    
    def get_key_pair(self, key_id: str) -> Optional[KeyPair]:
        """Get stored key pair by ID."""
        return self._key_pairs.get(key_id)
    
    def sign(
        self,
        data: bytes,
        key_id: Optional[str] = None,
        key_pair: Optional[KeyPair] = None,
    ) -> Signature:
        """
        Sign data.
        
        Args:
            data: Data to sign
            key_id: ID of stored key pair to use
            key_pair: Key pair to use (alternative to key_id)
            
        Returns:
            Signature
        """
        if key_pair is None:
            if key_id is None:
                raise SignatureError("Either key_id or key_pair must be provided")
            key_pair = self._key_pairs.get(key_id)
            if key_pair is None:
                raise SignatureError(f"Key pair not found: {key_id}")
        
        self._signer.key_id = key_pair.key_id
        
        return self._signer.sign(
            data,
            key_pair.private_key,
            key_pair.algorithm,
        )
    
    def verify(
        self,
        data: bytes,
        signature: Signature,
        public_key: Optional[bytes] = None,
        key_id: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify signature.
        
        Args:
            data: Original data
            signature: Signature to verify
            public_key: Public key bytes (optional)
            key_id: ID of stored key pair (optional)
            
        Returns:
            VerificationResult
        """
        if public_key is None:
            if key_id is None:
                key_id = signature.key_id
            
            key_pair = self._key_pairs.get(key_id)
            if key_pair is None:
                return VerificationResult(
                    valid=False,
                    algorithm=signature.algorithm,
                    key_id=key_id,
                    error=f"Key pair not found: {key_id}",
                )
            public_key = key_pair.public_key
        
        return self._signer.verify(data, signature, public_key)
    
    def create_document_signer(
        self,
        key_id: Optional[str] = None,
        key_pair: Optional[KeyPair] = None,
    ) -> DocumentSigner:
        """
        Create a document signer.
        
        Args:
            key_id: ID of stored key pair
            key_pair: Key pair to use
            
        Returns:
            DocumentSigner instance
        """
        if key_pair is None and key_id:
            key_pair = self._key_pairs.get(key_id)
        
        return DocumentSigner(key_pair=key_pair)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_signature_service() -> SignatureService:
    """Get the global signature service instance."""
    return SignatureService.get_instance()


def generate_key_pair(
    algorithm: Optional[SignatureAlgorithm] = None,
) -> KeyPair:
    """Generate a key pair using the global service."""
    return get_signature_service().generate_key_pair(algorithm)


def sign_data(
    data: bytes,
    key_pair: KeyPair,
) -> Signature:
    """Sign data using the global service."""
    return get_signature_service().sign(data, key_pair=key_pair)


def verify_signature(
    data: bytes,
    signature: Signature,
    public_key: bytes,
) -> VerificationResult:
    """Verify signature using the global service."""
    return get_signature_service().verify(data, signature, public_key)
