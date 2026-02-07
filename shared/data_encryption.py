"""
SEC-022: Secure Data Encryption.

Comprehensive data encryption including:
- AES-256-GCM authenticated encryption
- Envelope encryption for large data
- Field-level encryption
- Searchable encryption support
- Encryption key binding/context
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Nonce sizes
AES_GCM_NONCE_SIZE = 12  # 96 bits
CHACHA20_NONCE_SIZE = 12

# Tag sizes
AES_GCM_TAG_SIZE = 16  # 128 bits

# Version byte for encrypted data format
ENCRYPTION_VERSION = 1


# =============================================================================
# Enums
# =============================================================================

class EncryptionAlgorithm(str, Enum):
    """Supported encryption algorithms."""
    AES_256_GCM = "aes-256-gcm"
    AES_128_GCM = "aes-128-gcm"
    CHACHA20_POLY1305 = "chacha20-poly1305"


class DataClassification(str, Enum):
    """Data sensitivity classification."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # Highest sensitivity


# =============================================================================
# Exceptions
# =============================================================================

class EncryptionError(Exception):
    """Base exception for encryption errors."""
    pass


class DecryptionError(Exception):
    """Error during decryption."""
    pass


class IntegrityError(Exception):
    """Data integrity verification failed."""
    pass


class KeyNotFoundError(Exception):
    """Encryption key not found."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EncryptedData:
    """
    Container for encrypted data with metadata.
    
    Format:
    - version: Protocol version
    - algorithm: Encryption algorithm used
    - key_id: ID of encryption key (for key lookup)
    - nonce: Unique nonce/IV
    - ciphertext: Encrypted data with auth tag
    - aad: Additional authenticated data (not encrypted)
    """
    version: int
    algorithm: EncryptionAlgorithm
    key_id: str
    key_version: int
    nonce: bytes
    ciphertext: bytes
    aad: Optional[bytes] = None
    
    # Metadata
    encrypted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    classification: DataClassification = DataClassification.CONFIDENTIAL
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage."""
        # Simple format: version|algo|key_id_len|key_id|key_ver|nonce_len|nonce|ct
        header = struct.pack(
            ">B",  # version (1 byte)
            self.version,
        )
        
        algo_bytes = self.algorithm.value.encode()
        key_id_bytes = self.key_id.encode()
        
        data = (
            header +
            struct.pack(">H", len(algo_bytes)) + algo_bytes +
            struct.pack(">H", len(key_id_bytes)) + key_id_bytes +
            struct.pack(">I", self.key_version) +
            struct.pack(">H", len(self.nonce)) + self.nonce +
            self.ciphertext
        )
        
        return data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedData":
        """Deserialize from bytes."""
        offset = 0
        
        # Version
        version = struct.unpack_from(">B", data, offset)[0]
        offset += 1
        
        # Algorithm
        algo_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        algo = data[offset:offset + algo_len].decode()
        offset += algo_len
        
        # Key ID
        key_id_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        key_id = data[offset:offset + key_id_len].decode()
        offset += key_id_len
        
        # Key version
        key_version = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        
        # Nonce
        nonce_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        nonce = data[offset:offset + nonce_len]
        offset += nonce_len
        
        # Ciphertext (rest of data)
        ciphertext = data[offset:]
        
        return cls(
            version=version,
            algorithm=EncryptionAlgorithm(algo),
            key_id=key_id,
            key_version=key_version,
            nonce=nonce,
            ciphertext=ciphertext,
        )
    
    def to_base64(self) -> str:
        """Encode as base64 string."""
        return base64.b64encode(self.to_bytes()).decode()
    
    @classmethod
    def from_base64(cls, data: str) -> "EncryptedData":
        """Decode from base64 string."""
        return cls.from_bytes(base64.b64decode(data))


@dataclass
class EncryptionContext:
    """
    Context for encryption operations.
    
    Used to bind ciphertext to a specific context,
    preventing ciphertext from being used in wrong context.
    """
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    purpose: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)
    
    def to_aad(self) -> bytes:
        """Convert context to AAD bytes."""
        parts = []
        if self.tenant_id:
            parts.append(f"tenant:{self.tenant_id}")
        if self.user_id:
            parts.append(f"user:{self.user_id}")
        if self.resource_type:
            parts.append(f"type:{self.resource_type}")
        if self.resource_id:
            parts.append(f"id:{self.resource_id}")
        if self.purpose:
            parts.append(f"purpose:{self.purpose}")
        for key, value in sorted(self.extra.items()):
            parts.append(f"{key}:{value}")
        
        return "|".join(parts).encode()


# =============================================================================
# Core Encryption Engine
# =============================================================================

class EncryptionEngine:
    """
    Core encryption/decryption engine.
    
    Provides authenticated encryption with AES-GCM or ChaCha20-Poly1305.
    """
    
    def __init__(self, algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        self._algorithm = algorithm
    
    def encrypt(
        self,
        plaintext: bytes,
        key: bytes,
        aad: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        """
        Encrypt data with authenticated encryption.
        
        Args:
            plaintext: Data to encrypt
            key: Encryption key
            aad: Additional authenticated data (optional)
        
        Returns:
            (nonce, ciphertext) tuple
        """
        if self._algorithm in {EncryptionAlgorithm.AES_256_GCM, EncryptionAlgorithm.AES_128_GCM}:
            return self._encrypt_aes_gcm(plaintext, key, aad)
        elif self._algorithm == EncryptionAlgorithm.CHACHA20_POLY1305:
            return self._encrypt_chacha20(plaintext, key, aad)
        else:
            raise EncryptionError(f"Unsupported algorithm: {self._algorithm}")
    
    def decrypt(
        self,
        ciphertext: bytes,
        key: bytes,
        nonce: bytes,
        aad: Optional[bytes] = None,
    ) -> bytes:
        """
        Decrypt data with authenticated decryption.
        
        Args:
            ciphertext: Encrypted data
            key: Decryption key
            nonce: Nonce used during encryption
            aad: Additional authenticated data (must match encryption)
        
        Returns:
            Decrypted plaintext
        
        Raises:
            DecryptionError: If decryption or authentication fails
        """
        if self._algorithm in {EncryptionAlgorithm.AES_256_GCM, EncryptionAlgorithm.AES_128_GCM}:
            return self._decrypt_aes_gcm(ciphertext, key, nonce, aad)
        elif self._algorithm == EncryptionAlgorithm.CHACHA20_POLY1305:
            return self._decrypt_chacha20(ciphertext, key, nonce, aad)
        else:
            raise DecryptionError(f"Unsupported algorithm: {self._algorithm}")
    
    def _encrypt_aes_gcm(
        self,
        plaintext: bytes,
        key: bytes,
        aad: Optional[bytes],
    ) -> Tuple[bytes, bytes]:
        """Encrypt with AES-GCM."""
        nonce = secrets.token_bytes(AES_GCM_NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
        return nonce, ciphertext
    
    def _decrypt_aes_gcm(
        self,
        ciphertext: bytes,
        key: bytes,
        nonce: bytes,
        aad: Optional[bytes],
    ) -> bytes:
        """Decrypt with AES-GCM."""
        try:
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise DecryptionError(f"AES-GCM decryption failed: {e}")
    
    def _encrypt_chacha20(
        self,
        plaintext: bytes,
        key: bytes,
        aad: Optional[bytes],
    ) -> Tuple[bytes, bytes]:
        """Encrypt with ChaCha20-Poly1305."""
        nonce = secrets.token_bytes(CHACHA20_NONCE_SIZE)
        chacha = ChaCha20Poly1305(key)
        ciphertext = chacha.encrypt(nonce, plaintext, aad)
        return nonce, ciphertext
    
    def _decrypt_chacha20(
        self,
        ciphertext: bytes,
        key: bytes,
        nonce: bytes,
        aad: Optional[bytes],
    ) -> bytes:
        """Decrypt with ChaCha20-Poly1305."""
        try:
            chacha = ChaCha20Poly1305(key)
            return chacha.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise DecryptionError(f"ChaCha20 decryption failed: {e}")


# =============================================================================
# Envelope Encryption
# =============================================================================

class EnvelopeEncryption:
    """
    Envelope encryption for large data.
    
    Uses a randomly generated Data Encryption Key (DEK) to encrypt data,
    then encrypts the DEK with a Key Encryption Key (KEK).
    
    Benefits:
    - Efficient for large data
    - Allows key rotation without re-encrypting data
    - Limits exposure of master keys
    """
    
    def __init__(
        self,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM,
    ):
        self._algorithm = algorithm
        self._engine = EncryptionEngine(algorithm)
    
    def encrypt(
        self,
        plaintext: bytes,
        kek: bytes,
        aad: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes, bytes, bytes]:
        """
        Encrypt data using envelope encryption.
        
        Args:
            plaintext: Data to encrypt
            kek: Key Encryption Key
            aad: Additional authenticated data
        
        Returns:
            (encrypted_dek, dek_nonce, ciphertext, data_nonce)
        """
        # Generate random DEK
        dek = secrets.token_bytes(32)  # 256-bit DEK
        
        # Encrypt data with DEK
        data_nonce, ciphertext = self._engine.encrypt(plaintext, dek, aad)
        
        # Encrypt DEK with KEK
        dek_nonce, encrypted_dek = self._engine.encrypt(dek, kek, None)
        
        # Clear DEK from memory
        dek = b'\x00' * 32
        
        return encrypted_dek, dek_nonce, ciphertext, data_nonce
    
    def decrypt(
        self,
        encrypted_dek: bytes,
        dek_nonce: bytes,
        ciphertext: bytes,
        data_nonce: bytes,
        kek: bytes,
        aad: Optional[bytes] = None,
    ) -> bytes:
        """
        Decrypt data using envelope encryption.
        
        Args:
            encrypted_dek: Encrypted Data Encryption Key
            dek_nonce: Nonce for DEK encryption
            ciphertext: Encrypted data
            data_nonce: Nonce for data encryption
            kek: Key Encryption Key
            aad: Additional authenticated data
        
        Returns:
            Decrypted plaintext
        """
        # Decrypt DEK
        dek = self._engine.decrypt(encrypted_dek, kek, dek_nonce, None)
        
        # Decrypt data
        try:
            plaintext = self._engine.decrypt(ciphertext, dek, data_nonce, aad)
        finally:
            # Clear DEK from memory
            dek = b'\x00' * len(dek)
        
        return plaintext


# =============================================================================
# Field-Level Encryption
# =============================================================================

class FieldEncryptor:
    """
    Field-level encryption for structured data.
    
    Encrypts individual fields in a dictionary/object while
    preserving the structure. Useful for database column encryption
    or API payload encryption.
    """
    
    def __init__(
        self,
        key: bytes,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM,
    ):
        self._key = key
        self._engine = EncryptionEngine(algorithm)
        self._algorithm = algorithm
    
    def encrypt_field(
        self,
        value: Any,
        field_name: str,
        context: Optional[EncryptionContext] = None,
    ) -> str:
        """
        Encrypt a single field value.
        
        Returns base64-encoded encrypted value.
        """
        # Serialize value
        if isinstance(value, str):
            plaintext = value.encode()
        elif isinstance(value, bytes):
            plaintext = value
        else:
            plaintext = json.dumps(value).encode()
        
        # Build AAD from context
        aad = None
        if context:
            context.extra["field"] = field_name
            aad = context.to_aad()
        else:
            aad = f"field:{field_name}".encode()
        
        # Encrypt
        nonce, ciphertext = self._engine.encrypt(plaintext, self._key, aad)
        
        # Combine nonce and ciphertext, encode as base64
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode()
    
    def decrypt_field(
        self,
        encrypted_value: str,
        field_name: str,
        value_type: type = str,
        context: Optional[EncryptionContext] = None,
    ) -> Any:
        """
        Decrypt a single field value.
        
        Args:
            encrypted_value: Base64-encoded encrypted value
            field_name: Name of the field (must match encryption)
            value_type: Expected type of decrypted value
            context: Encryption context (must match encryption)
        
        Returns:
            Decrypted value
        """
        # Decode
        combined = base64.b64decode(encrypted_value)
        nonce = combined[:AES_GCM_NONCE_SIZE]
        ciphertext = combined[AES_GCM_NONCE_SIZE:]
        
        # Build AAD
        aad = None
        if context:
            context.extra["field"] = field_name
            aad = context.to_aad()
        else:
            aad = f"field:{field_name}".encode()
        
        # Decrypt
        plaintext = self._engine.decrypt(ciphertext, self._key, nonce, aad)
        
        # Deserialize
        if value_type == bytes:
            return plaintext
        elif value_type == str:
            return plaintext.decode()
        else:
            return json.loads(plaintext.decode())
    
    def encrypt_fields(
        self,
        data: Dict[str, Any],
        fields_to_encrypt: Set[str],
        context: Optional[EncryptionContext] = None,
    ) -> Dict[str, Any]:
        """
        Encrypt specific fields in a dictionary.
        
        Returns copy with encrypted fields.
        """
        result = dict(data)
        
        for field in fields_to_encrypt:
            if field in result and result[field] is not None:
                result[field] = self.encrypt_field(
                    result[field],
                    field,
                    context,
                )
        
        return result
    
    def decrypt_fields(
        self,
        data: Dict[str, Any],
        fields_to_decrypt: Dict[str, type],
        context: Optional[EncryptionContext] = None,
    ) -> Dict[str, Any]:
        """
        Decrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with encrypted fields
            fields_to_decrypt: Mapping of field name to expected type
            context: Encryption context
        
        Returns:
            Copy with decrypted fields
        """
        result = dict(data)
        
        for field, value_type in fields_to_decrypt.items():
            if field in result and result[field] is not None:
                result[field] = self.decrypt_field(
                    result[field],
                    field,
                    value_type,
                    context,
                )
        
        return result


# =============================================================================
# Searchable Encryption (Deterministic)
# =============================================================================

class SearchableEncryption:
    """
    Deterministic encryption for searchable encrypted fields.
    
    WARNING: Less secure than randomized encryption because
    identical plaintexts produce identical ciphertexts.
    Only use when search functionality is required.
    """
    
    def __init__(self, key: bytes):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        self._key = key
        # Derive separate keys for encryption and HMAC
        self._enc_key = self._derive_key(key, b"encryption")
        self._mac_key = self._derive_key(key, b"mac")
    
    def _derive_key(self, master: bytes, info: bytes) -> bytes:
        """Derive a sub-key."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=info,
            backend=default_backend(),
        )
        return hkdf.derive(master)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext deterministically.
        
        Same plaintext always produces same ciphertext.
        """
        # Create deterministic "nonce" from plaintext
        nonce = hmac.new(
            self._mac_key,
            plaintext.encode(),
            hashlib.sha256,
        ).digest()[:AES_GCM_NONCE_SIZE]
        
        # Encrypt
        aesgcm = AESGCM(self._enc_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        
        # Combine and encode
        return base64.b64encode(nonce + ciphertext).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt deterministically encrypted value."""
        combined = base64.b64decode(encrypted)
        nonce = combined[:AES_GCM_NONCE_SIZE]
        ciphertext = combined[AES_GCM_NONCE_SIZE:]
        
        aesgcm = AESGCM(self._enc_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode()
    
    def create_search_token(self, plaintext: str) -> str:
        """
        Create a search token for a value.
        
        The token can be compared against encrypted values
        to find matches without decryption.
        """
        return self.encrypt(plaintext)


# =============================================================================
# Data Encryption Service
# =============================================================================

class DataEncryptionService:
    """
    High-level service for data encryption operations.
    
    Manages encryption keys and provides simple API for
    encrypting/decrypting data with proper key handling.
    """
    
    _instance: Optional["DataEncryptionService"] = None
    
    def __init__(
        self,
        default_key: Optional[bytes] = None,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM,
    ):
        self._default_key = default_key or secrets.token_bytes(32)
        self._algorithm = algorithm
        self._engine = EncryptionEngine(algorithm)
        self._envelope = EnvelopeEncryption(algorithm)
        self._keys: Dict[str, Tuple[bytes, int]] = {}  # key_id -> (key, version)
        self._lock = asyncio.Lock()
    
    @classmethod
    def configure(
        cls,
        default_key: Optional[bytes] = None,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM,
    ) -> "DataEncryptionService":
        """Configure singleton instance."""
        cls._instance = cls(default_key=default_key, algorithm=algorithm)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "DataEncryptionService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_key(
        self,
        key_id: str,
        key: bytes,
        version: int = 1,
    ) -> None:
        """Register an encryption key."""
        self._keys[key_id] = (key, version)
    
    def get_key(self, key_id: str) -> Optional[Tuple[bytes, int]]:
        """Get a registered key."""
        return self._keys.get(key_id)
    
    async def encrypt(
        self,
        plaintext: Union[str, bytes],
        key_id: Optional[str] = None,
        context: Optional[EncryptionContext] = None,
    ) -> EncryptedData:
        """
        Encrypt data.
        
        Args:
            plaintext: Data to encrypt
            key_id: ID of encryption key (uses default if not specified)
            context: Encryption context for AAD binding
        
        Returns:
            EncryptedData container
        """
        # Get key
        if key_id and key_id in self._keys:
            key, version = self._keys[key_id]
        else:
            key = self._default_key
            key_id = "default"
            version = 1
        
        # Convert to bytes
        if isinstance(plaintext, str):
            plaintext_bytes = plaintext.encode()
        else:
            plaintext_bytes = plaintext
        
        # Build AAD
        aad = context.to_aad() if context else None
        
        # Encrypt
        nonce, ciphertext = self._engine.encrypt(plaintext_bytes, key, aad)
        
        return EncryptedData(
            version=ENCRYPTION_VERSION,
            algorithm=self._algorithm,
            key_id=key_id,
            key_version=version,
            nonce=nonce,
            ciphertext=ciphertext,
            aad=aad,
        )
    
    async def decrypt(
        self,
        encrypted: EncryptedData,
        context: Optional[EncryptionContext] = None,
    ) -> bytes:
        """
        Decrypt data.
        
        Args:
            encrypted: EncryptedData container
            context: Encryption context (must match encryption)
        
        Returns:
            Decrypted bytes
        """
        # Get key
        if encrypted.key_id in self._keys:
            key, _ = self._keys[encrypted.key_id]
        elif encrypted.key_id == "default":
            key = self._default_key
        else:
            raise KeyNotFoundError(f"Key not found: {encrypted.key_id}")
        
        # Build AAD
        aad = context.to_aad() if context else encrypted.aad
        
        # Decrypt
        return self._engine.decrypt(
            encrypted.ciphertext,
            key,
            encrypted.nonce,
            aad,
        )
    
    async def encrypt_string(
        self,
        plaintext: str,
        key_id: Optional[str] = None,
        context: Optional[EncryptionContext] = None,
    ) -> str:
        """Encrypt string and return base64-encoded result."""
        encrypted = await self.encrypt(plaintext, key_id, context)
        return encrypted.to_base64()
    
    async def decrypt_string(
        self,
        encrypted_base64: str,
        context: Optional[EncryptionContext] = None,
    ) -> str:
        """Decrypt base64-encoded string."""
        encrypted = EncryptedData.from_base64(encrypted_base64)
        plaintext = await self.decrypt(encrypted, context)
        return plaintext.decode()
    
    def create_field_encryptor(
        self,
        key_id: Optional[str] = None,
    ) -> FieldEncryptor:
        """Create a field encryptor with specified key."""
        if key_id and key_id in self._keys:
            key, _ = self._keys[key_id]
        else:
            key = self._default_key
        
        return FieldEncryptor(key, self._algorithm)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_encryption_service() -> DataEncryptionService:
    """Get the singleton encryption service."""
    return DataEncryptionService.get_instance()


async def encrypt_data(
    plaintext: Union[str, bytes],
    key_id: Optional[str] = None,
    context: Optional[EncryptionContext] = None,
) -> EncryptedData:
    """Encrypt data using the default service."""
    service = get_encryption_service()
    return await service.encrypt(plaintext, key_id, context)


async def decrypt_data(
    encrypted: EncryptedData,
    context: Optional[EncryptionContext] = None,
) -> bytes:
    """Decrypt data using the default service."""
    service = get_encryption_service()
    return await service.decrypt(encrypted, context)


async def encrypt_string(
    plaintext: str,
    key_id: Optional[str] = None,
) -> str:
    """Encrypt string and return base64-encoded result."""
    service = get_encryption_service()
    return await service.encrypt_string(plaintext, key_id)


async def decrypt_string(encrypted_base64: str) -> str:
    """Decrypt base64-encoded encrypted string."""
    service = get_encryption_service()
    return await service.decrypt_string(encrypted_base64)
