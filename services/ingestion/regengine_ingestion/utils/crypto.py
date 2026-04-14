"""Cryptographic hashing utilities for document verification."""

import hashlib
from typing import Tuple


def hash_content(content: bytes) -> Tuple[str, str]:
    """
    Compute SHA-256 and SHA-512 hashes of content.
    
    Args:
        content: Raw bytes to hash
        
    Returns:
        Tuple of (sha256_hex, sha512_hex)
    """
    sha256 = hashlib.sha256(content).hexdigest()
    sha512 = hashlib.sha512(content).hexdigest()
    return sha256, sha512


def hash_text(text: str) -> Tuple[str, str]:
    """
    Compute SHA-256 and SHA-512 hashes of text.
    
    Args:
        text: Text string to hash
        
    Returns:
        Tuple of (sha256_hex, sha512_hex)
    """
    content = text.encode("utf-8")
    return hash_content(content)


def verify_hash(content: bytes, expected_sha256: str) -> bool:
    """
    Verify content matches expected SHA-256 hash.
    
    Args:
        content: Content to verify
        expected_sha256: Expected SHA-256 hex digest
        
    Returns:
        True if hash matches, False otherwise
    """
    actual_sha256, _ = hash_content(content)
    return actual_sha256 == expected_sha256


def generate_document_id(content_sha256: str, prefix_length: int = 64) -> str:
    """
    Generate a document ID from content hash.

    Uses full 64-char SHA-256 hex digest by default to prevent birthday
    collision risk in large corpora (#977).  Legacy callers passing
    prefix_length < 64 will still work but get a deprecation warning.

    Args:
        content_sha256: SHA-256 hash of content
        prefix_length: Length of hash prefix to use (default: 64, full digest)

    Returns:
        Document ID string
    """
    if prefix_length < 64:
        import warnings
        warnings.warn(
            f"generate_document_id prefix_length={prefix_length} is deprecated; "
            "use full 64-char digest for collision safety",
            DeprecationWarning,
            stacklevel=2,
        )
    return content_sha256[:prefix_length]
