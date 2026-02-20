"""
SEC-039: File Upload Security.

Provides secure file upload handling:
- File type validation
- Size limits
- Content inspection
- Filename sanitization
- Path traversal prevention
"""

import hashlib
import mimetypes
import os
import re
import secrets
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Set, Tuple


# =============================================================================
# Enums
# =============================================================================

class FileValidationResult(str, Enum):
    """File validation results."""
    VALID = "valid"
    INVALID_TYPE = "invalid_type"
    INVALID_EXTENSION = "invalid_extension"
    SIZE_EXCEEDED = "size_exceeded"
    DANGEROUS_CONTENT = "dangerous_content"
    INVALID_FILENAME = "invalid_filename"
    PATH_TRAVERSAL = "path_traversal"


class FileCategory(str, Enum):
    """File categories."""
    IMAGE = "image"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    TEXT = "text"
    DATA = "data"
    UNKNOWN = "unknown"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FileUploadConfig:
    """File upload configuration."""
    max_size_bytes: int = 512 * 1024 * 1024  # 512MB
    allowed_extensions: Set[str] = field(default_factory=lambda: {
        ".jpg", ".jpeg", ".png", ".gif", ".webp",  # Images
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",  # Documents
        ".txt", ".csv", ".json", ".xml",  # Text/Data
    })
    blocked_extensions: Set[str] = field(default_factory=lambda: {
        ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1",  # Executables
        ".php", ".asp", ".aspx", ".jsp", ".cgi",  # Server scripts
        ".js", ".html", ".htm", ".svg",  # Web content
        ".scr", ".pif", ".com", ".msi", ".jar",  # More executables
    })
    allowed_mime_types: Optional[Set[str]] = None
    check_magic_bytes: bool = True
    sanitize_filename: bool = True
    generate_safe_name: bool = False


@dataclass
class FileInfo:
    """Information about an uploaded file."""
    original_filename: str
    safe_filename: str
    extension: str
    size_bytes: int
    mime_type: str
    category: FileCategory
    content_hash: str
    is_valid: bool
    validation_result: FileValidationResult
    validation_message: str = ""


@dataclass
class MagicBytes:
    """Magic bytes signature for file type."""
    bytes: bytes
    offset: int = 0
    mime_type: str = ""
    extension: str = ""


# =============================================================================
# File Type Detector
# =============================================================================

class FileTypeDetector:
    """
    Detects file types by magic bytes and extension.
    """
    
    # Common file signatures
    SIGNATURES: Dict[str, MagicBytes] = {
        "jpeg": MagicBytes(b"\xff\xd8\xff", mime_type="image/jpeg", extension=".jpg"),
        "png": MagicBytes(b"\x89PNG\r\n\x1a\n", mime_type="image/png", extension=".png"),
        "gif": MagicBytes(b"GIF8", mime_type="image/gif", extension=".gif"),
        "webp": MagicBytes(b"RIFF", mime_type="image/webp", extension=".webp"),
        "pdf": MagicBytes(b"%PDF", mime_type="application/pdf", extension=".pdf"),
        "zip": MagicBytes(b"PK\x03\x04", mime_type="application/zip", extension=".zip"),
        "docx": MagicBytes(b"PK\x03\x04", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", extension=".docx"),
        "xlsx": MagicBytes(b"PK\x03\x04", mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", extension=".xlsx"),
        "exe": MagicBytes(b"MZ", mime_type="application/x-msdownload", extension=".exe"),
        "elf": MagicBytes(b"\x7fELF", mime_type="application/x-executable", extension=""),
    }
    
    def detect_by_magic(self, content: bytes) -> Optional[MagicBytes]:
        """Detect file type by magic bytes."""
        for name, sig in self.SIGNATURES.items():
            if content[sig.offset:sig.offset + len(sig.bytes)] == sig.bytes:
                return sig
        return None
    
    def detect_by_extension(self, filename: str) -> Tuple[str, str]:
        """
        Detect file type by extension.
        
        Returns:
            Tuple of (mime_type, extension)
        """
        ext = Path(filename).suffix.lower()
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return mime_type, ext
    
    def get_category(self, mime_type: str) -> FileCategory:
        """Get file category from mime type."""
        if mime_type.startswith("image/"):
            return FileCategory.IMAGE
        elif mime_type.startswith("text/"):
            return FileCategory.TEXT
        elif mime_type in (
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            return FileCategory.DOCUMENT
        elif mime_type in (
            "application/zip",
            "application/x-tar",
            "application/gzip",
        ):
            return FileCategory.ARCHIVE
        elif mime_type in (
            "application/json",
            "application/xml",
            "text/csv",
        ):
            return FileCategory.DATA
        return FileCategory.UNKNOWN


# =============================================================================
# Filename Sanitizer
# =============================================================================

class FilenameSanitizer:
    """
    Sanitizes filenames to prevent security issues.
    """
    
    # Dangerous filename patterns
    DANGEROUS_PATTERNS = [
        r"\.\.",  # Path traversal
        r"[/\\]",  # Directory separators
        r"[\x00-\x1f]",  # Control characters
        r"^\.+$",  # All dots
        r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\.|$)",  # Windows reserved
    ]
    
    # Characters to remove
    UNSAFE_CHARS = '<>:"|?*\x00'
    
    def __init__(self, max_length: int = 255):
        """Initialize sanitizer."""
        self.max_length = max_length
        self._patterns = [re.compile(p, re.I) for p in self.DANGEROUS_PATTERNS]
    
    def sanitize(self, filename: str) -> str:
        """
        Sanitize a filename.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Normalize path separators (handle both Unix and Windows)
        filename = filename.replace("\\", "/")
        
        # Remove directory components
        filename = os.path.basename(filename)
        
        # Remove any remaining path separators
        filename = filename.replace("/", "").replace("\\", "")
        
        # Remove unsafe characters
        for char in self.UNSAFE_CHARS:
            filename = filename.replace(char, "")
        
        # Remove leading/trailing whitespace and dots
        filename = filename.strip(". \t\n\r")
        
        # Replace spaces with underscores
        filename = filename.replace(" ", "_")
        
        # Check for dangerous patterns
        for pattern in self._patterns:
            if pattern.search(filename):
                # Generate safe name
                return self.generate_safe_name(filename)
        
        # Truncate if too long (preserve extension)
        if len(filename) > self.max_length:
            name, ext = os.path.splitext(filename)
            max_name_len = self.max_length - len(ext)
            filename = name[:max_name_len] + ext
        
        # If empty after sanitization
        if not filename:
            return self.generate_safe_name("")
        
        return filename
    
    def generate_safe_name(self, original: str) -> str:
        """Generate a safe random filename preserving extension."""
        ext = Path(original).suffix.lower() if original else ""
        random_name = secrets.token_hex(8)
        
        if ext and ext not in (".exe", ".dll", ".bat", ".cmd", ".sh"):
            return f"{random_name}{ext}"
        return random_name
    
    def is_safe(self, filename: str) -> bool:
        """Check if filename is safe."""
        if not filename:
            return False
        
        for pattern in self._patterns:
            if pattern.search(filename):
                return False
        
        for char in self.UNSAFE_CHARS:
            if char in filename:
                return False
        
        return True


# =============================================================================
# File Validator
# =============================================================================

class FileValidator:
    """
    Validates uploaded files for security.
    """
    
    def __init__(self, config: Optional[FileUploadConfig] = None):
        """Initialize validator."""
        self.config = config or FileUploadConfig()
        self.type_detector = FileTypeDetector()
        self.filename_sanitizer = FilenameSanitizer()
    
    def validate(
        self,
        filename: str,
        content: bytes,
        declared_mime: Optional[str] = None,
    ) -> FileInfo:
        """
        Validate an uploaded file.
        
        Args:
            filename: Original filename
            content: File content
            declared_mime: Declared MIME type
            
        Returns:
            FileInfo with validation result
        """
        # Check for path traversal in original filename FIRST
        if ".." in filename or "/" in filename or "\\" in filename:
            safe_filename = self.filename_sanitizer.sanitize(filename)
            ext = Path(safe_filename).suffix.lower()
            return self._create_info(
                filename, safe_filename, ext, content,
                is_valid=False,
                result=FileValidationResult.PATH_TRAVERSAL,
                message="Path traversal detected in filename",
            )
        
        # Sanitize filename
        safe_filename = self.filename_sanitizer.sanitize(filename)
        if self.config.generate_safe_name:
            safe_filename = self.filename_sanitizer.generate_safe_name(filename)
        
        # Get extension
        ext = Path(safe_filename).suffix.lower()
        
        # Check extension
        if ext in self.config.blocked_extensions:
            return self._create_info(
                filename, safe_filename, ext, content,
                is_valid=False,
                result=FileValidationResult.INVALID_EXTENSION,
                message=f"Extension {ext} is blocked",
            )
        
        if self.config.allowed_extensions and ext not in self.config.allowed_extensions:
            return self._create_info(
                filename, safe_filename, ext, content,
                is_valid=False,
                result=FileValidationResult.INVALID_EXTENSION,
                message=f"Extension {ext} is not allowed",
            )
        
        # Check size
        if len(content) > self.config.max_size_bytes:
            return self._create_info(
                filename, safe_filename, ext, content,
                is_valid=False,
                result=FileValidationResult.SIZE_EXCEEDED,
                message=f"File size {len(content)} exceeds limit {self.config.max_size_bytes}",
            )
        
        # Detect actual type
        detected_mime, _ = self.type_detector.detect_by_extension(safe_filename)
        
        if self.config.check_magic_bytes and content:
            magic = self.type_detector.detect_by_magic(content)
            if magic:
                detected_mime = magic.mime_type
                
                # Check for executable disguised as other type
                if magic.extension in (".exe", "") and ext not in (".exe", ".dll"):
                    return self._create_info(
                        filename, safe_filename, ext, content,
                        is_valid=False,
                        result=FileValidationResult.DANGEROUS_CONTENT,
                        message="File content does not match extension",
                    )
        
        # Check MIME type
        if self.config.allowed_mime_types:
            if detected_mime not in self.config.allowed_mime_types:
                return self._create_info(
                    filename, safe_filename, ext, content,
                    is_valid=False,
                    result=FileValidationResult.INVALID_TYPE,
                    message=f"MIME type {detected_mime} is not allowed",
                )
        
        return self._create_info(
            filename, safe_filename, ext, content,
            is_valid=True,
            result=FileValidationResult.VALID,
            message="File is valid",
        )
    
    def _create_info(
        self,
        original: str,
        safe: str,
        ext: str,
        content: bytes,
        is_valid: bool,
        result: FileValidationResult,
        message: str,
    ) -> FileInfo:
        """Create FileInfo object."""
        mime_type, _ = self.type_detector.detect_by_extension(safe)
        category = self.type_detector.get_category(mime_type)
        content_hash = hashlib.sha256(content).hexdigest() if content else ""
        
        return FileInfo(
            original_filename=original,
            safe_filename=safe,
            extension=ext,
            size_bytes=len(content),
            mime_type=mime_type,
            category=category,
            content_hash=content_hash,
            is_valid=is_valid,
            validation_result=result,
            validation_message=message,
        )


# =============================================================================
# Content Scanner
# =============================================================================

class ContentScanner:
    """
    Scans file content for dangerous patterns.
    """
    
    # Dangerous patterns to check
    DANGEROUS_PATTERNS = [
        b"<%",  # ASP/JSP
        b"<?php",  # PHP
        b"<script",  # JavaScript
        b"javascript:",  # JavaScript URL
        b"onerror=",  # Event handlers
        b"onload=",
        b"eval(",  # Code execution
    ]
    
    def scan(self, content: bytes) -> List[str]:
        """
        Scan content for dangerous patterns.
        
        Returns:
            List of detected threats
        """
        threats = []
        content_lower = content.lower()
        
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in content_lower:
                threats.append(f"Dangerous pattern detected: {pattern.decode('utf-8', errors='ignore')}")
        
        return threats
    
    def is_safe(self, content: bytes) -> bool:
        """Check if content is safe."""
        return len(self.scan(content)) == 0


# =============================================================================
# File Upload Service
# =============================================================================

class FileUploadService:
    """
    High-level service for secure file uploads.
    """
    
    _instance: Optional["FileUploadService"] = None
    
    def __init__(self, config: Optional[FileUploadConfig] = None):
        """Initialize service."""
        self.config = config or FileUploadConfig()
        self.validator = FileValidator(self.config)
        self.scanner = ContentScanner()
        self.sanitizer = FilenameSanitizer()
    
    @classmethod
    def get_instance(cls) -> "FileUploadService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: FileUploadConfig) -> "FileUploadService":
        """Configure the service."""
        cls._instance = cls(config)
        return cls._instance
    
    def validate(
        self,
        filename: str,
        content: bytes,
    ) -> FileInfo:
        """Validate an uploaded file."""
        return self.validator.validate(filename, content)
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename."""
        return self.sanitizer.sanitize(filename)
    
    def scan_content(self, content: bytes) -> List[str]:
        """Scan content for threats."""
        return self.scanner.scan(content)
    
    def is_allowed_extension(self, filename: str) -> bool:
        """Check if extension is allowed."""
        ext = Path(filename).suffix.lower()
        
        if ext in self.config.blocked_extensions:
            return False
        
        if self.config.allowed_extensions:
            return ext in self.config.allowed_extensions
        
        return True
    
    def generate_safe_filename(self, original: str) -> str:
        """Generate a safe random filename."""
        return self.sanitizer.generate_safe_name(original)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_upload_service() -> FileUploadService:
    """Get the global file upload service."""
    return FileUploadService.get_instance()


def validate_upload(filename: str, content: bytes) -> FileInfo:
    """Validate an uploaded file."""
    return get_upload_service().validate(filename, content)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename."""
    return get_upload_service().sanitize_filename(filename)


def is_safe_upload(filename: str, content: bytes) -> bool:
    """Check if upload is safe."""
    info = get_upload_service().validate(filename, content)
    return info.is_valid
