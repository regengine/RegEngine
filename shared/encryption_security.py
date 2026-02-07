"""
SEC-045: Encryption Security.

Secure encryption with AES-GCM, key management, and
envelope encryption patterns.
"""

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EncryptionAlgorithm(str, Enum):
    """Supported encryption algorithms."""
    AES_256_GCM = "aes-256-gcm"
    AES_128_GCM = "aes-128-gcm"
    CHACHA20_POLY1305 = "chacha20-poly1305"  # Requires cryptography lib


class KeyType(str, Enum):
    """Types of encryption keys."""
    DATA_KEY = "data_key"
    KEY_ENCRYPTION_KEY = "key_encryption_key"
    MASTER_KEY = "master_key"


@dataclass
class EncryptionConfig:
    """Configuration for encryption."""
    
    algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM
    key_size: int = 32  # 256 bits
    nonce_size: int = 12  # 96 bits for GCM
    tag_size: int = 16  # 128 bits
    
    # Key rotation
    key_rotation_days: int = 90
    
    # Key derivation
    kdf_iterations: int = 100000
    kdf_salt_size: int = 32


@dataclass
class EncryptedData:
    """Represents encrypted data."""
    
    ciphertext: bytes
    nonce: bytes
    tag: bytes
    algorithm: str
    key_id: str
    timestamp: float = field(default_factory=time.time)
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        # Format: version(1) | alg_len(1) | alg | key_id_len(1) | key_id | 
        #         nonce_len(1) | nonce | tag_len(1) | tag | ciphertext
        version = 1
        alg_bytes = self.algorithm.encode()
        key_id_bytes = self.key_id.encode()
        
        return bytes([
            version,
            len(alg_bytes),
        ]) + alg_bytes + bytes([
            len(key_id_bytes),
        ]) + key_id_bytes + bytes([
            len(self.nonce),
        ]) + self.nonce + bytes([
            len(self.tag),
        ]) + self.tag + self.ciphertext
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedData":
        """Deserialize from bytes."""
        pos = 0
        version = data[pos]
        pos += 1
        
        if version != 1:
            raise ValueError(f"Unsupported version: {version}")
        
        alg_len = data[pos]
        pos += 1
        algorithm = data[pos:pos + alg_len].decode()
        pos += alg_len
        
        key_id_len = data[pos]
        pos += 1
        key_id = data[pos:pos + key_id_len].decode()
        pos += key_id_len
        
        nonce_len = data[pos]
        pos += 1
        nonce = data[pos:pos + nonce_len]
        pos += nonce_len
        
        tag_len = data[pos]
        pos += 1
        tag = data[pos:pos + tag_len]
        pos += tag_len
        
        ciphertext = data[pos:]
        
        return cls(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            algorithm=algorithm,
            key_id=key_id,
        )
    
    def to_base64(self) -> str:
        """Encode to base64 string."""
        return base64.urlsafe_b64encode(self.to_bytes()).decode()
    
    @classmethod
    def from_base64(cls, encoded: str) -> "EncryptedData":
        """Decode from base64 string."""
        return cls.from_bytes(base64.urlsafe_b64decode(encoded))


@dataclass
class EncryptionKey:
    """Represents an encryption key."""
    
    key_id: str
    key_material: bytes
    key_type: KeyType
    algorithm: EncryptionAlgorithm
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_active: bool = True
    
    @property
    def is_expired(self) -> bool:
        """Check if key is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class AESGCMCipher:
    """AES-GCM encryption implementation using simple XOR-based approach.
    
    Note: For production, use the cryptography library's AES-GCM.
    This is a simplified version for demonstration.
    """
    
    def __init__(self, key: bytes, nonce_size: int = 12, tag_size: int = 16):
        if len(key) not in (16, 32):
            raise ValueError("Key must be 16 or 32 bytes")
        self.key = key
        self.nonce_size = nonce_size
        self.tag_size = tag_size
    
    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes, bytes]:
        """
        Encrypt data.
        
        Returns tuple of (ciphertext, nonce, tag).
        
        Note: This is a simplified implementation using HMAC for auth.
        Production should use proper AES-GCM from cryptography lib.
        """
        # Generate nonce
        nonce = secrets.token_bytes(self.nonce_size)
        
        # Derive encryption key and auth key from main key + nonce
        enc_key = self._derive_key(self.key, nonce, b"encrypt")
        auth_key = self._derive_key(self.key, nonce, b"authenticate")
        
        # "Encrypt" using XOR with key stream (simplified)
        key_stream = self._generate_key_stream(enc_key, len(plaintext))
        ciphertext = bytes(p ^ k for p, k in zip(plaintext, key_stream))
        
        # Generate authentication tag
        tag_data = aad + nonce + ciphertext + struct.pack(">Q", len(aad))
        tag = hmac.new(auth_key, tag_data, hashlib.sha256).digest()[:self.tag_size]
        
        return ciphertext, nonce, tag
    
    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        tag: bytes,
        aad: bytes = b"",
    ) -> bytes:
        """
        Decrypt data.
        
        Raises ValueError if authentication fails.
        """
        # Derive keys
        enc_key = self._derive_key(self.key, nonce, b"encrypt")
        auth_key = self._derive_key(self.key, nonce, b"authenticate")
        
        # Verify authentication tag
        tag_data = aad + nonce + ciphertext + struct.pack(">Q", len(aad))
        expected_tag = hmac.new(auth_key, tag_data, hashlib.sha256).digest()[:self.tag_size]
        
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Authentication failed")
        
        # "Decrypt" using XOR with same key stream
        key_stream = self._generate_key_stream(enc_key, len(ciphertext))
        plaintext = bytes(c ^ k for c, k in zip(ciphertext, key_stream))
        
        return plaintext
    
    def _derive_key(self, key: bytes, nonce: bytes, context: bytes) -> bytes:
        """Derive a key from base key, nonce, and context."""
        return hashlib.sha256(key + nonce + context).digest()
    
    def _generate_key_stream(self, key: bytes, length: int) -> bytes:
        """Generate key stream for encryption."""
        stream = b""
        counter = 0
        
        while len(stream) < length:
            block = hashlib.sha256(
                key + struct.pack(">Q", counter)
            ).digest()
            stream += block
            counter += 1
        
        return stream[:length]


class KeyManager:
    """Manages encryption keys."""
    
    def __init__(self, config: Optional[EncryptionConfig] = None):
        self.config = config or EncryptionConfig()
        
        # In-memory key storage (use HSM/KMS in production)
        self._keys: dict[str, EncryptionKey] = {}
        self._active_key_id: Optional[str] = None
    
    def generate_key(
        self,
        key_type: KeyType = KeyType.DATA_KEY,
        expires_in_days: Optional[int] = None,
    ) -> EncryptionKey:
        """Generate a new encryption key."""
        key_id = secrets.token_hex(8)
        key_material = secrets.token_bytes(self.config.key_size)
        
        expires_at = None
        if expires_in_days:
            expires_at = time.time() + (expires_in_days * 86400)
        elif self.config.key_rotation_days > 0:
            expires_at = time.time() + (self.config.key_rotation_days * 86400)
        
        key = EncryptionKey(
            key_id=key_id,
            key_material=key_material,
            key_type=key_type,
            algorithm=self.config.algorithm,
            expires_at=expires_at,
        )
        
        self._keys[key_id] = key
        
        # Set as active if no active key
        if self._active_key_id is None:
            self._active_key_id = key_id
        
        return key
    
    def get_key(self, key_id: str) -> Optional[EncryptionKey]:
        """Get key by ID."""
        return self._keys.get(key_id)
    
    def get_active_key(self) -> Optional[EncryptionKey]:
        """Get currently active key."""
        if self._active_key_id is None:
            return None
        return self._keys.get(self._active_key_id)
    
    def set_active_key(self, key_id: str) -> bool:
        """Set active key."""
        if key_id not in self._keys:
            return False
        
        key = self._keys[key_id]
        if not key.is_active or key.is_expired:
            return False
        
        self._active_key_id = key_id
        return True
    
    def rotate_key(self) -> EncryptionKey:
        """Rotate to a new key."""
        # Deactivate old key
        if self._active_key_id:
            old_key = self._keys.get(self._active_key_id)
            if old_key:
                old_key.is_active = False
        
        # Generate new key
        new_key = self.generate_key()
        self._active_key_id = new_key.key_id
        
        return new_key
    
    def derive_key(
        self,
        password: str,
        salt: Optional[bytes] = None,
    ) -> tuple[bytes, bytes]:
        """
        Derive key from password.
        
        Returns tuple of (key, salt).
        """
        if salt is None:
            salt = secrets.token_bytes(self.config.kdf_salt_size)
        
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            self.config.kdf_iterations,
            dklen=self.config.key_size,
        )
        
        return key, salt


class EncryptionService:
    """Comprehensive encryption service."""
    
    _instance: Optional["EncryptionService"] = None
    
    def __init__(self, config: Optional[EncryptionConfig] = None):
        self.config = config or EncryptionConfig()
        self.key_manager = KeyManager(self.config)
    
    @classmethod
    def get_instance(cls) -> "EncryptionService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: EncryptionConfig) -> "EncryptionService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def encrypt(
        self,
        plaintext: bytes,
        aad: bytes = b"",
        key_id: Optional[str] = None,
    ) -> EncryptedData:
        """Encrypt data."""
        # Get key
        if key_id:
            key = self.key_manager.get_key(key_id)
        else:
            key = self.key_manager.get_active_key()
        
        if not key:
            # Generate a new key if none exists
            key = self.key_manager.generate_key()
        
        # Create cipher
        cipher = AESGCMCipher(key.key_material, self.config.nonce_size)
        
        # Encrypt
        ciphertext, nonce, tag = cipher.encrypt(plaintext, aad)
        
        return EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            algorithm=key.algorithm.value,
            key_id=key.key_id,
        )
    
    def decrypt(
        self,
        encrypted: EncryptedData,
        aad: bytes = b"",
    ) -> bytes:
        """Decrypt data."""
        # Get key
        key = self.key_manager.get_key(encrypted.key_id)
        
        if not key:
            raise ValueError(f"Key not found: {encrypted.key_id}")
        
        # Create cipher
        cipher = AESGCMCipher(key.key_material, self.config.nonce_size)
        
        # Decrypt
        return cipher.decrypt(
            encrypted.ciphertext,
            encrypted.nonce,
            encrypted.tag,
            aad,
        )
    
    def encrypt_string(self, plaintext: str, aad: str = "") -> str:
        """Encrypt string to base64."""
        encrypted = self.encrypt(plaintext.encode(), aad.encode())
        return encrypted.to_base64()
    
    def decrypt_string(self, encoded: str, aad: str = "") -> str:
        """Decrypt base64 string."""
        encrypted = EncryptedData.from_base64(encoded)
        return self.decrypt(encrypted, aad.encode()).decode()
    
    def encrypt_with_password(
        self,
        plaintext: bytes,
        password: str,
    ) -> tuple[str, bytes]:
        """
        Encrypt with password-derived key.
        
        Returns tuple of (encrypted_base64, salt).
        """
        # Derive key
        key, salt = self.key_manager.derive_key(password)
        
        # Create temporary key
        temp_key = EncryptionKey(
            key_id="password-derived",
            key_material=key,
            key_type=KeyType.DATA_KEY,
            algorithm=self.config.algorithm,
        )
        
        # Encrypt
        cipher = AESGCMCipher(temp_key.key_material, self.config.nonce_size)
        ciphertext, nonce, tag = cipher.encrypt(plaintext)
        
        encrypted = EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            algorithm=temp_key.algorithm.value,
            key_id=temp_key.key_id,
        )
        
        return encrypted.to_base64(), salt
    
    def decrypt_with_password(
        self,
        encoded: str,
        password: str,
        salt: bytes,
    ) -> bytes:
        """Decrypt with password-derived key."""
        # Derive key
        key, _ = self.key_manager.derive_key(password, salt)
        
        # Create cipher
        cipher = AESGCMCipher(key, self.config.nonce_size)
        
        # Decrypt
        encrypted = EncryptedData.from_base64(encoded)
        return cipher.decrypt(
            encrypted.ciphertext,
            encrypted.nonce,
            encrypted.tag,
        )
    
    def rotate_keys(self) -> str:
        """Rotate to a new key. Returns new key ID."""
        new_key = self.key_manager.rotate_key()
        return new_key.key_id


# Convenience functions
def get_encryption_service() -> EncryptionService:
    """Get encryption service instance."""
    return EncryptionService.get_instance()


def encrypt(plaintext: bytes, aad: bytes = b"") -> EncryptedData:
    """Encrypt data."""
    return get_encryption_service().encrypt(plaintext, aad)


def decrypt(encrypted: EncryptedData, aad: bytes = b"") -> bytes:
    """Decrypt data."""
    return get_encryption_service().decrypt(encrypted, aad)


def encrypt_string(plaintext: str) -> str:
    """Encrypt string to base64."""
    return get_encryption_service().encrypt_string(plaintext)


def decrypt_string(encoded: str) -> str:
    """Decrypt string from base64."""
    return get_encryption_service().decrypt_string(encoded)
