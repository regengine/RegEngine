"""Field-level encryption utilities for PII protection.

This module provides encryption/decryption for sensitive fields like SSN, EIN,
and other personally identifiable information (PII).

Security Features:
- AES-256-GCM encryption with authenticated encryption
- Unique nonce per encryption operation
- Key derivation from master secret
- Tokenization support for display masking
- External KMS integration ready (optional)

Usage:
    from shared.pii_encryption import PIIEncryptor
    
    encryptor = PIIEncryptor()
    
    # Encrypt sensitive data
    encrypted = encryptor.encrypt("123-45-6789")
    
    # Decrypt when needed
    original = encryptor.decrypt(encrypted)
    
    # Get masked version for display
    masked = encryptor.mask_ssn("123-45-6789")  # Returns "***-**-6789"
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger("pii-encryption")

# Environment variable for encryption key
PII_ENCRYPTION_KEY_ENV = "PII_ENCRYPTION_KEY"
PII_ENCRYPTION_KEY_ID_ENV = "PII_ENCRYPTION_KEY_ID"

# Encryption constants
NONCE_SIZE = 12  # 96 bits for AES-GCM
TAG_SIZE = 16    # 128 bits authentication tag
KEY_SIZE = 32    # 256 bits for AES-256


class PIIEncryptionError(Exception):
    """Raised when PII encryption/decryption fails."""
    pass


class PIIKeyNotConfiguredError(PIIEncryptionError):
    """Raised when encryption key is not configured."""
    pass


@dataclass
class EncryptedValue:
    """Container for encrypted PII value with metadata."""
    ciphertext: str  # Base64 encoded
    key_id: str      # Key identifier for rotation support
    version: str = "v1"
    
    def to_string(self) -> str:
        """Serialize to storable string format."""
        return f"{self.version}:{self.key_id}:{self.ciphertext}"
    
    @classmethod
    def from_string(cls, value: str) -> "EncryptedValue":
        """Parse from stored string format."""
        parts = value.split(":", 2)
        if len(parts) != 3:
            raise PIIEncryptionError("Invalid encrypted value format")
        return cls(
            version=parts[0],
            key_id=parts[1],
            ciphertext=parts[2],
        )


def _get_encryption_key() -> tuple[bytes, str]:
    """Get encryption key and key ID from environment.
    
    Returns:
        Tuple of (key_bytes, key_id)
        
    Raises:
        PIIKeyNotConfiguredError: If key not configured.
    """
    key_hex = os.getenv(PII_ENCRYPTION_KEY_ENV)
    if not key_hex:
        raise PIIKeyNotConfiguredError(
            f"PII encryption key not configured. "
            f"Set {PII_ENCRYPTION_KEY_ENV} to a 64-character hex string (32 bytes)."
        )
    
    try:
        key_bytes = bytes.fromhex(key_hex)
    except ValueError:
        raise PIIEncryptionError("PII encryption key must be valid hexadecimal")
    
    if len(key_bytes) != KEY_SIZE:
        raise PIIEncryptionError(
            f"PII encryption key must be {KEY_SIZE} bytes ({KEY_SIZE * 2} hex chars)"
        )
    
    key_id = os.getenv(PII_ENCRYPTION_KEY_ID_ENV, "default")
    return key_bytes, key_id


class PIIEncryptor:
    """Handles encryption and decryption of PII fields.
    
    Uses AES-256-GCM for authenticated encryption.
    """
    
    def __init__(self, key: Optional[bytes] = None, key_id: Optional[str] = None):
        """Initialize encryptor.
        
        Args:
            key: Optional 32-byte encryption key. If None, uses environment.
            key_id: Optional key identifier. If None, uses environment.
        """
        if key is not None:
            if len(key) != KEY_SIZE:
                raise PIIEncryptionError(f"Key must be {KEY_SIZE} bytes")
            self._key = key
            self._key_id = key_id or "custom"
        else:
            self._key, self._key_id = _get_encryption_key()
        
        # Import cryptography here to make it optional
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._aesgcm = AESGCM(self._key)
        except ImportError:
            raise PIIEncryptionError(
                "cryptography package required for PII encryption. "
                "Install with: pip install cryptography"
            )
    
    def encrypt(self, plaintext: str, associated_data: Optional[bytes] = None) -> str:
        """Encrypt a PII value.
        
        Args:
            plaintext: The sensitive value to encrypt.
            associated_data: Optional AAD for additional authentication.
            
        Returns:
            Encrypted value as string (format: "v1:key_id:base64_ciphertext")
        """
        if not plaintext:
            raise PIIEncryptionError("Cannot encrypt empty value")
        
        # Generate unique nonce
        nonce = secrets.token_bytes(NONCE_SIZE)
        
        # Encrypt with AES-GCM
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, plaintext_bytes, associated_data)
        
        # Combine nonce + ciphertext and encode
        combined = nonce + ciphertext
        encoded = base64.b64encode(combined).decode("ascii")
        
        encrypted = EncryptedValue(
            ciphertext=encoded,
            key_id=self._key_id,
            version="v1",
        )
        
        logger.debug(
            "pii_encrypted",
            key_id=self._key_id,
            plaintext_len=len(plaintext),
        )
        
        return encrypted.to_string()
    
    def decrypt(self, encrypted_value: str, associated_data: Optional[bytes] = None) -> str:
        """Decrypt a PII value.
        
        Args:
            encrypted_value: The encrypted string from encrypt().
            associated_data: Must match AAD used during encryption.
            
        Returns:
            Original plaintext value.
            
        Raises:
            PIIEncryptionError: If decryption fails.
        """
        try:
            parsed = EncryptedValue.from_string(encrypted_value)
        except Exception as exc:
            raise PIIEncryptionError(f"Invalid encrypted value: {exc}")
        
        if parsed.key_id != self._key_id:
            raise PIIEncryptionError(
                f"Key ID mismatch. Value encrypted with '{parsed.key_id}', "
                f"but current key is '{self._key_id}'"
            )
        
        try:
            combined = base64.b64decode(parsed.ciphertext)
        except Exception:
            raise PIIEncryptionError("Invalid ciphertext encoding")
        
        if len(combined) < NONCE_SIZE + TAG_SIZE:
            raise PIIEncryptionError("Ciphertext too short")
        
        nonce = combined[:NONCE_SIZE]
        ciphertext = combined[NONCE_SIZE:]
        
        try:
            plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext, associated_data)
        except Exception as exc:
            raise PIIEncryptionError(f"Decryption failed: {exc}")
        
        logger.debug("pii_decrypted", key_id=self._key_id)
        
        return plaintext_bytes.decode("utf-8")
    
    def is_encrypted(self, value: str) -> bool:
        """Check if a value appears to be encrypted.
        
        Args:
            value: Value to check.
            
        Returns:
            True if value appears to be in encrypted format.
        """
        if not value:
            return False
        try:
            parsed = EncryptedValue.from_string(value)
            return parsed.version in ("v1",)
        except Exception:
            return False


# Masking utilities for display purposes

def mask_ssn(ssn: str) -> str:
    """Mask SSN for display, showing only last 4 digits.
    
    Args:
        ssn: Social Security Number (with or without dashes).
        
    Returns:
        Masked SSN like "***-**-1234"
    """
    # Remove non-digits
    digits = re.sub(r"\D", "", ssn)
    if len(digits) < 4:
        return "***-**-****"
    return f"***-**-{digits[-4:]}"


def mask_ein(ein: str) -> str:
    """Mask EIN for display, showing only last 4 digits.
    
    Args:
        ein: Employer Identification Number.
        
    Returns:
        Masked EIN like "**-***1234"
    """
    digits = re.sub(r"\D", "", ein)
    if len(digits) < 4:
        return "**-*******"
    return f"**-***{digits[-4:]}"


def mask_credit_card(card_number: str) -> str:
    """Mask credit card number, showing only last 4 digits.
    
    Args:
        card_number: Credit card number.
        
    Returns:
        Masked number like "****-****-****-1234"
    """
    digits = re.sub(r"\D", "", card_number)
    if len(digits) < 4:
        return "****-****-****-****"
    return f"****-****-****-{digits[-4:]}"


def mask_email(email: str) -> str:
    """Mask email address for display.
    
    Args:
        email: Email address.
        
    Returns:
        Masked email like "j***@example.com"
    """
    if "@" not in email:
        return "***@***.***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 1)
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask phone number for display.
    
    Args:
        phone: Phone number.
        
    Returns:
        Masked phone like "***-***-1234"
    """
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "***-***-****"
    return f"***-***-{digits[-4:]}"


def generate_encryption_key() -> str:
    """Generate a new random encryption key.
    
    Returns:
        64-character hex string suitable for PII_ENCRYPTION_KEY.
    """
    return secrets.token_hex(KEY_SIZE)


def hash_for_lookup(value: str, salt: Optional[str] = None) -> str:
    """Generate a searchable hash of a PII value.
    
    This allows looking up records by PII without storing plaintext.
    
    Args:
        value: The PII value to hash.
        salt: Optional salt. If None, uses environment variable.
        
    Returns:
        Hex-encoded SHA-256 hash.
    """
    if salt is None:
        salt = os.getenv("PII_HASH_SALT", "")
    
    salted = f"{salt}:{value}"
    return hashlib.sha256(salted.encode()).hexdigest()
