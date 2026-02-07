"""
SEC-013: Path Traversal Prevention for RegEngine.

This module provides protection against path traversal attacks:
- Path normalization and validation
- Directory boundary enforcement
- Filename sanitization
- Symlink protection

Usage:
    from shared.path_security import PathValidator, SafePathJoin
    
    validator = PathValidator(base_dir="/app/uploads")
    
    # Validate a path
    safe_path = validator.validate(user_input)
    
    # Safe path joining
    final_path = SafePathJoin.join("/app/uploads", user_filename)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePath
from typing import Optional, Union

import structlog

logger = structlog.get_logger("path_security")


# =============================================================================
# Exceptions
# =============================================================================

class PathSecurityError(Exception):
    """Base exception for path security issues."""
    
    def __init__(self, message: str, attempted_path: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.attempted_path = attempted_path


class PathTraversalError(PathSecurityError):
    """Raised when path traversal is detected."""
    pass


class PathOutOfBoundsError(PathSecurityError):
    """Raised when path is outside allowed directory."""
    pass


class InvalidPathError(PathSecurityError):
    """Raised when path is invalid."""
    pass


class SymlinkError(PathSecurityError):
    """Raised when symlink leads outside allowed directory."""
    pass


# =============================================================================
# Path Traversal Patterns
# =============================================================================

class TraversalPatterns:
    """Patterns for detecting path traversal attempts."""
    
    # Basic traversal patterns
    BASIC: list[re.Pattern] = [
        re.compile(r'\.\.(/|\\)'),  # ../  ..\
        re.compile(r'(/|\\)\.\.'),  # /../  \..
        re.compile(r'^\.\.'),  # Starts with ..
    ]
    
    # URL-encoded traversal
    URL_ENCODED: list[re.Pattern] = [
        re.compile(r'%2e%2e[/\\%]', re.IGNORECASE),  # %2e%2e/
        re.compile(r'%2e%2e$', re.IGNORECASE),  # Ends with %2e%2e
        re.compile(r'\.%2e[/\\%]', re.IGNORECASE),  # .%2e/
        re.compile(r'%2e\.[/\\%]', re.IGNORECASE),  # %2e./
    ]
    
    # Double URL-encoded
    DOUBLE_ENCODED: list[re.Pattern] = [
        re.compile(r'%252e', re.IGNORECASE),  # Double-encoded .
        re.compile(r'%255c', re.IGNORECASE),  # Double-encoded \
        re.compile(r'%252f', re.IGNORECASE),  # Double-encoded /
    ]
    
    # Unicode/overlong UTF-8
    UNICODE: list[re.Pattern] = [
        re.compile(r'%c0%ae', re.IGNORECASE),  # Overlong UTF-8 for .
        re.compile(r'%c0%af', re.IGNORECASE),  # Overlong UTF-8 for /
        re.compile(r'%e0%80%ae', re.IGNORECASE),  # 3-byte overlong .
    ]
    
    # Null byte injection
    NULL_BYTE: list[re.Pattern] = [
        re.compile(r'%00'),  # URL-encoded null
        re.compile(r'\x00'),  # Literal null
    ]
    
    # Windows-specific
    WINDOWS: list[re.Pattern] = [
        re.compile(r'[a-zA-Z]:'),  # Drive letters
        re.compile(r'\\\\'),  # UNC paths
        re.compile(r'\.\.\\'),  # Windows traversal
    ]
    
    # Dangerous filenames
    DANGEROUS_NAMES: set[str] = {
        'con', 'prn', 'aux', 'nul',
        'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
        'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
        '.htaccess', '.htpasswd', 'web.config',
    }


# =============================================================================
# Path Sanitizer
# =============================================================================

class PathSanitizer:
    """Sanitize path components."""
    
    # Characters not allowed in filenames
    FORBIDDEN_CHARS = set('<>:"|?*\x00')
    
    # Characters to replace (Windows-specific)
    REPLACE_CHARS = {'\\': '/', ':': '_'}
    
    @classmethod
    def sanitize_filename(
        cls,
        filename: str,
        allow_spaces: bool = True,
        max_length: int = 255,
    ) -> str:
        """Sanitize a filename.
        
        Args:
            filename: Filename to sanitize
            allow_spaces: Whether to allow spaces
            max_length: Maximum filename length
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return ""
        
        # Remove path separators
        filename = os.path.basename(filename)
        
        # Replace problematic characters
        for char, replacement in cls.REPLACE_CHARS.items():
            filename = filename.replace(char, replacement)
        
        # Remove forbidden characters
        filename = ''.join(
            c for c in filename
            if c not in cls.FORBIDDEN_CHARS
        )
        
        # Handle spaces
        if not allow_spaces:
            filename = filename.replace(' ', '_')
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Truncate to max length
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            max_name_len = max_length - len(ext)
            filename = name[:max_name_len] + ext
        
        return filename
    
    @classmethod
    def sanitize_path(cls, path: str) -> str:
        """Sanitize a full path.
        
        Args:
            path: Path to sanitize
            
        Returns:
            Sanitized path
        """
        if not path:
            return ""
        
        # Normalize separators
        path = path.replace('\\', '/')
        
        # Remove null bytes
        path = path.replace('\x00', '')
        
        # URL decode (single pass for safety)
        import urllib.parse
        try:
            decoded = urllib.parse.unquote(path)
            # Only use decoded if it doesn't introduce traversal
            if '..' not in decoded:
                path = decoded
        except Exception:
            pass
        
        return path


# =============================================================================
# Path Validator
# =============================================================================

@dataclass
class PathValidationResult:
    """Result of path validation."""
    
    is_valid: bool
    resolved_path: Optional[str] = None
    error: Optional[str] = None
    
    def __bool__(self) -> bool:
        return self.is_valid


class PathValidator:
    """Validate paths to prevent traversal attacks."""
    
    def __init__(
        self,
        base_dir: Union[str, Path],
        allow_symlinks: bool = False,
        check_exists: bool = False,
        allow_absolute: bool = False,
    ):
        """Initialize path validator.
        
        Args:
            base_dir: Base directory that paths must stay within
            allow_symlinks: Whether to allow symlinks
            check_exists: Whether to require path to exist
            allow_absolute: Whether to allow absolute paths
        """
        self._base_dir = Path(base_dir).resolve()
        self._allow_symlinks = allow_symlinks
        self._check_exists = check_exists
        self._allow_absolute = allow_absolute
    
    def validate(self, path: Union[str, Path]) -> str:
        """Validate a path.
        
        Args:
            path: Path to validate
            
        Returns:
            Resolved absolute path
            
        Raises:
            PathTraversalError: If traversal detected
            PathOutOfBoundsError: If path is outside base_dir
            InvalidPathError: If path is invalid
        """
        result = self.check(path)
        
        if not result.is_valid:
            if "traversal" in (result.error or "").lower():
                raise PathTraversalError(result.error, str(path))
            elif "outside" in (result.error or "").lower():
                raise PathOutOfBoundsError(result.error, str(path))
            else:
                raise InvalidPathError(result.error or "Invalid path", str(path))
        
        return result.resolved_path
    
    def check(self, path: Union[str, Path]) -> PathValidationResult:
        """Check a path without raising exceptions.
        
        Args:
            path: Path to check
            
        Returns:
            Validation result
        """
        if not path:
            return PathValidationResult(False, error="Empty path")
        
        path_str = str(path)
        
        # Check for traversal patterns
        if self._has_traversal_patterns(path_str):
            logger.warning(
                "path_traversal_detected",
                path=path_str[:100],
            )
            return PathValidationResult(
                False,
                error="Path traversal detected",
            )
        
        # Handle absolute vs relative
        path_obj = Path(path_str)
        
        if path_obj.is_absolute():
            if not self._allow_absolute:
                return PathValidationResult(
                    False,
                    error="Absolute paths not allowed",
                )
            resolved = path_obj.resolve()
        else:
            # Join with base dir
            resolved = (self._base_dir / path_obj).resolve()
        
        # Check if within base directory
        try:
            resolved.relative_to(self._base_dir)
        except ValueError:
            logger.warning(
                "path_outside_base",
                path=str(resolved)[:100],
                base=str(self._base_dir),
            )
            return PathValidationResult(
                False,
                error=f"Path is outside allowed directory",
            )
        
        # Check symlinks
        if not self._allow_symlinks and resolved.is_symlink():
            # Resolve symlink and check again
            real_path = resolved.resolve()
            try:
                real_path.relative_to(self._base_dir)
            except ValueError:
                logger.warning(
                    "symlink_escape",
                    symlink=str(resolved)[:100],
                    target=str(real_path)[:100],
                )
                return PathValidationResult(
                    False,
                    error="Symlink points outside allowed directory",
                )
        
        # Check existence if required
        if self._check_exists and not resolved.exists():
            return PathValidationResult(
                False,
                error="Path does not exist",
            )
        
        return PathValidationResult(
            True,
            resolved_path=str(resolved),
        )
    
    def _has_traversal_patterns(self, path: str) -> bool:
        """Check for traversal patterns in path."""
        # Check basic patterns
        for pattern in TraversalPatterns.BASIC:
            if pattern.search(path):
                return True
        
        # Check URL-encoded patterns
        for pattern in TraversalPatterns.URL_ENCODED:
            if pattern.search(path):
                return True
        
        # Check double-encoded patterns
        for pattern in TraversalPatterns.DOUBLE_ENCODED:
            if pattern.search(path):
                return True
        
        # Check null byte patterns
        for pattern in TraversalPatterns.NULL_BYTE:
            if pattern.search(path):
                return True
        
        # Check Windows patterns
        for pattern in TraversalPatterns.WINDOWS:
            if pattern.search(path):
                return True
        
        return False
    
    def is_dangerous_filename(self, filename: str) -> bool:
        """Check if filename is dangerous."""
        name_lower = filename.lower()
        
        # Check against dangerous names
        base_name = os.path.splitext(name_lower)[0]
        if base_name in TraversalPatterns.DANGEROUS_NAMES:
            return True
        
        if name_lower in TraversalPatterns.DANGEROUS_NAMES:
            return True
        
        return False


# =============================================================================
# Safe Path Join
# =============================================================================

class SafePathJoin:
    """Safely join paths preventing traversal."""
    
    @staticmethod
    def join(base: Union[str, Path], *parts: str) -> str:
        """Safely join path parts to base.
        
        Args:
            base: Base directory
            *parts: Path parts to join
            
        Returns:
            Joined path that stays within base
            
        Raises:
            PathTraversalError: If any part attempts traversal
        """
        base_path = Path(base).resolve()
        
        # Process each part
        current = base_path
        for part in parts:
            if not part:
                continue
            
            # Sanitize the part
            sanitized = PathSanitizer.sanitize_path(part)
            
            # Check for traversal
            if '..' in sanitized:
                raise PathTraversalError(
                    "Path traversal in component",
                    part,
                )
            
            # Remove leading slashes to prevent absolute path injection
            sanitized = sanitized.lstrip('/')
            
            # Join and resolve
            current = (current / sanitized).resolve()
            
            # Verify still within base
            try:
                current.relative_to(base_path)
            except ValueError:
                raise PathTraversalError(
                    "Resulting path outside base directory",
                    str(current),
                )
        
        return str(current)
    
    @staticmethod
    def join_safe(base: Union[str, Path], *parts: str) -> Optional[str]:
        """Safely join paths, returning None on error.
        
        Args:
            base: Base directory
            *parts: Path parts to join
            
        Returns:
            Joined path or None if invalid
        """
        try:
            return SafePathJoin.join(base, *parts)
        except PathSecurityError:
            return None


# =============================================================================
# File Upload Validator
# =============================================================================

class FileUploadValidator:
    """Validate file uploads for security."""
    
    # Dangerous file extensions
    DANGEROUS_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib',  # Executables
        '.bat', '.cmd', '.sh', '.ps1',  # Scripts
        '.php', '.php3', '.php4', '.php5', '.phtml',  # PHP
        '.asp', '.aspx', '.ascx', '.ashx',  # ASP
        '.jsp', '.jspx',  # JSP
        '.py', '.pyc', '.pyo',  # Python
        '.rb',  # Ruby
        '.pl', '.cgi',  # Perl/CGI
        '.htaccess', '.htpasswd',  # Apache config
        '.config',  # Various config files
    }
    
    # Extension to MIME type mapping
    EXTENSION_MIME_MAP = {
        '.jpg': {'image/jpeg'},
        '.jpeg': {'image/jpeg'},
        '.png': {'image/png'},
        '.gif': {'image/gif'},
        '.pdf': {'application/pdf'},
        '.doc': {'application/msword'},
        '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
        '.txt': {'text/plain'},
        '.csv': {'text/csv', 'text/plain'},
        '.json': {'application/json', 'text/plain'},
        '.xml': {'application/xml', 'text/xml'},
    }
    
    def __init__(
        self,
        allowed_extensions: Optional[set[str]] = None,
        max_filename_length: int = 255,
        allow_hidden_files: bool = False,
    ):
        """Initialize upload validator.
        
        Args:
            allowed_extensions: Set of allowed extensions (with dot)
            max_filename_length: Maximum filename length
            allow_hidden_files: Whether to allow files starting with .
        """
        self._allowed_extensions = allowed_extensions
        self._max_filename_length = max_filename_length
        self._allow_hidden = allow_hidden_files
    
    def validate_filename(self, filename: str) -> str:
        """Validate and sanitize an uploaded filename.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
            
        Raises:
            InvalidPathError: If filename is invalid
        """
        if not filename:
            raise InvalidPathError("Empty filename")
        
        # Sanitize first
        safe_name = PathSanitizer.sanitize_filename(
            filename,
            max_length=self._max_filename_length,
        )
        
        if not safe_name:
            raise InvalidPathError("Filename sanitized to empty string")
        
        # Check for hidden files
        if not self._allow_hidden and safe_name.startswith('.'):
            raise InvalidPathError("Hidden files not allowed")
        
        # Get extension
        _, ext = os.path.splitext(safe_name)
        ext_lower = ext.lower()
        
        # Check against dangerous extensions
        if ext_lower in self.DANGEROUS_EXTENSIONS:
            logger.warning(
                "dangerous_extension_blocked",
                filename=safe_name[:50],
                extension=ext_lower,
            )
            raise InvalidPathError(f"Dangerous file extension: {ext_lower}")
        
        # Check against allowed extensions
        if self._allowed_extensions is not None:
            if ext_lower not in self._allowed_extensions:
                raise InvalidPathError(
                    f"Extension not allowed: {ext_lower}"
                )
        
        return safe_name
    
    def validate_content_type(
        self,
        filename: str,
        content_type: str,
    ) -> bool:
        """Validate that content type matches extension.
        
        Args:
            filename: Filename with extension
            content_type: Reported content type
            
        Returns:
            True if content type is valid for extension
        """
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        
        expected_types = self.EXTENSION_MIME_MAP.get(ext_lower)
        if expected_types is None:
            # Unknown extension, can't validate
            return True
        
        return content_type in expected_types


# =============================================================================
# Directory Jail
# =============================================================================

class DirectoryJail:
    """Create a jailed directory context for file operations.
    
    Usage:
        jail = DirectoryJail("/app/uploads")
        
        with jail:
            # All path operations are validated
            jail.write_file("user.txt", content)
            jail.read_file("user.txt")
    """
    
    def __init__(self, base_dir: Union[str, Path]):
        """Initialize directory jail.
        
        Args:
            base_dir: Base directory to jail operations to
        """
        self._base_dir = Path(base_dir).resolve()
        self._validator = PathValidator(
            base_dir=self._base_dir,
            allow_symlinks=False,
            allow_absolute=False,
        )
    
    def __enter__(self) -> "DirectoryJail":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
    @property
    def base_dir(self) -> Path:
        """Get base directory."""
        return self._base_dir
    
    def resolve_path(self, path: str) -> Path:
        """Resolve path within jail.
        
        Args:
            path: Relative path
            
        Returns:
            Resolved absolute path
        """
        validated = self._validator.validate(path)
        return Path(validated)
    
    def exists(self, path: str) -> bool:
        """Check if path exists within jail."""
        try:
            resolved = self.resolve_path(path)
            return resolved.exists()
        except PathSecurityError:
            return False
    
    def read_file(self, path: str) -> bytes:
        """Read file within jail.
        
        Args:
            path: Relative path to file
            
        Returns:
            File contents
        """
        resolved = self.resolve_path(path)
        return resolved.read_bytes()
    
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read text file within jail."""
        resolved = self.resolve_path(path)
        return resolved.read_text(encoding=encoding)
    
    def write_file(
        self,
        path: str,
        content: bytes,
        create_parents: bool = False,
    ) -> Path:
        """Write file within jail.
        
        Args:
            path: Relative path to file
            content: Content to write
            create_parents: Whether to create parent directories
            
        Returns:
            Path to written file
        """
        resolved = self.resolve_path(path)
        
        if create_parents:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        
        resolved.write_bytes(content)
        return resolved
    
    def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_parents: bool = False,
    ) -> Path:
        """Write text file within jail."""
        resolved = self.resolve_path(path)
        
        if create_parents:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        
        resolved.write_text(content, encoding=encoding)
        return resolved
    
    def list_dir(self, path: str = ".") -> list[str]:
        """List directory within jail.
        
        Args:
            path: Relative path to directory
            
        Returns:
            List of filenames
        """
        resolved = self.resolve_path(path)
        if not resolved.is_dir():
            raise InvalidPathError("Not a directory")
        return [p.name for p in resolved.iterdir()]
    
    def delete(self, path: str) -> None:
        """Delete file within jail."""
        resolved = self.resolve_path(path)
        resolved.unlink()
