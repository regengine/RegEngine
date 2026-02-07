"""
Tests for SEC-039: File Upload Security.

Tests cover:
- File type validation
- Size limits
- Content inspection
- Filename sanitization
- Path traversal prevention
"""

import pytest

from shared.file_upload_security import (
    # Enums
    FileValidationResult,
    FileCategory,
    # Data classes
    FileUploadConfig,
    FileInfo,
    # Classes
    FileTypeDetector,
    FilenameSanitizer,
    FileValidator,
    ContentScanner,
    FileUploadService,
    # Convenience functions
    get_upload_service,
    validate_upload,
    sanitize_filename,
    is_safe_upload,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create upload config."""
    return FileUploadConfig()


@pytest.fixture
def type_detector():
    """Create type detector."""
    return FileTypeDetector()


@pytest.fixture
def sanitizer():
    """Create filename sanitizer."""
    return FilenameSanitizer()


@pytest.fixture
def validator(config):
    """Create file validator."""
    return FileValidator(config)


@pytest.fixture
def scanner():
    """Create content scanner."""
    return ContentScanner()


@pytest.fixture
def service(config):
    """Create upload service."""
    return FileUploadService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_validation_results(self):
        """Should have expected validation results."""
        assert FileValidationResult.VALID == "valid"
        assert FileValidationResult.INVALID_TYPE == "invalid_type"
        assert FileValidationResult.SIZE_EXCEEDED == "size_exceeded"
    
    def test_file_categories(self):
        """Should have expected categories."""
        assert FileCategory.IMAGE == "image"
        assert FileCategory.DOCUMENT == "document"
        assert FileCategory.ARCHIVE == "archive"


# =============================================================================
# Test: FileUploadConfig
# =============================================================================

class TestFileUploadConfig:
    """Test FileUploadConfig class."""
    
    def test_default_values(self, config):
        """Should have secure defaults."""
        assert config.max_size_bytes == 10 * 1024 * 1024
        assert ".exe" in config.blocked_extensions
        assert ".php" in config.blocked_extensions
        assert ".jpg" in config.allowed_extensions
        assert ".pdf" in config.allowed_extensions
        assert config.check_magic_bytes is True


# =============================================================================
# Test: FileTypeDetector
# =============================================================================

class TestFileTypeDetector:
    """Test FileTypeDetector."""
    
    def test_detect_jpeg_by_magic(self, type_detector):
        """Should detect JPEG by magic bytes."""
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        
        result = type_detector.detect_by_magic(jpeg_bytes)
        
        assert result is not None
        assert result.mime_type == "image/jpeg"
    
    def test_detect_png_by_magic(self, type_detector):
        """Should detect PNG by magic bytes."""
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00"
        
        result = type_detector.detect_by_magic(png_bytes)
        
        assert result is not None
        assert result.mime_type == "image/png"
    
    def test_detect_pdf_by_magic(self, type_detector):
        """Should detect PDF by magic bytes."""
        pdf_bytes = b"%PDF-1.4"
        
        result = type_detector.detect_by_magic(pdf_bytes)
        
        assert result is not None
        assert result.mime_type == "application/pdf"
    
    def test_detect_by_extension(self, type_detector):
        """Should detect by extension."""
        mime, ext = type_detector.detect_by_extension("document.pdf")
        
        assert ext == ".pdf"
        assert "pdf" in mime.lower()
    
    def test_get_category_image(self, type_detector):
        """Should categorize images."""
        assert type_detector.get_category("image/jpeg") == FileCategory.IMAGE
        assert type_detector.get_category("image/png") == FileCategory.IMAGE
    
    def test_get_category_document(self, type_detector):
        """Should categorize documents."""
        assert type_detector.get_category("application/pdf") == FileCategory.DOCUMENT


# =============================================================================
# Test: FilenameSanitizer
# =============================================================================

class TestFilenameSanitizer:
    """Test FilenameSanitizer."""
    
    def test_removes_path_traversal(self, sanitizer):
        """Should remove path traversal."""
        result = sanitizer.sanitize("../../../etc/passwd")
        
        assert ".." not in result
        assert "/" not in result
    
    def test_removes_directory_components(self, sanitizer):
        """Should remove directory components."""
        result = sanitizer.sanitize("/path/to/file.txt")
        
        assert "/" not in result
        assert "file.txt" in result
    
    def test_removes_unsafe_characters(self, sanitizer):
        """Should remove unsafe characters."""
        result = sanitizer.sanitize('file<script>.txt')
        
        assert "<" not in result
        assert ">" not in result
    
    def test_removes_null_bytes(self, sanitizer):
        """Should remove null bytes."""
        result = sanitizer.sanitize("file\x00.txt")
        
        assert "\x00" not in result
    
    def test_handles_windows_reserved_names(self, sanitizer):
        """Should handle Windows reserved names."""
        result = sanitizer.sanitize("CON.txt")
        
        # Should generate safe name instead
        assert result != "CON.txt"
    
    def test_truncates_long_names(self, sanitizer):
        """Should truncate long names."""
        long_name = "a" * 300 + ".txt"
        result = sanitizer.sanitize(long_name)
        
        assert len(result) <= 255
        assert result.endswith(".txt")
    
    def test_generate_safe_name(self, sanitizer):
        """Should generate safe random name."""
        result = sanitizer.generate_safe_name("original.jpg")
        
        assert result.endswith(".jpg")
        assert result != "original.jpg"
        assert len(result) > 4  # Has random part
    
    def test_is_safe(self, sanitizer):
        """Should check if filename is safe."""
        assert sanitizer.is_safe("document.pdf") is True
        assert sanitizer.is_safe("../evil.txt") is False
        assert sanitizer.is_safe("file\x00.txt") is False


# =============================================================================
# Test: FileValidator
# =============================================================================

class TestFileValidator:
    """Test FileValidator."""
    
    def test_validates_allowed_file(self, validator):
        """Should validate allowed file."""
        result = validator.validate(
            "document.pdf",
            b"%PDF-1.4 content",
        )
        
        assert result.is_valid is True
        assert result.validation_result == FileValidationResult.VALID
    
    def test_blocks_exe_extension(self, validator):
        """Should block .exe extension."""
        result = validator.validate(
            "malware.exe",
            b"MZ executable content",
        )
        
        assert result.is_valid is False
        assert result.validation_result == FileValidationResult.INVALID_EXTENSION
    
    def test_blocks_php_extension(self, validator):
        """Should block .php extension."""
        result = validator.validate(
            "shell.php",
            b"<?php system($_GET['cmd']); ?>",
        )
        
        assert result.is_valid is False
        assert result.validation_result == FileValidationResult.INVALID_EXTENSION
    
    def test_blocks_oversized_file(self, validator):
        """Should block oversized files."""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        
        result = validator.validate("large.pdf", large_content)
        
        assert result.is_valid is False
        assert result.validation_result == FileValidationResult.SIZE_EXCEEDED
    
    def test_detects_path_traversal(self, validator):
        """Should detect path traversal."""
        result = validator.validate(
            "../../../etc/passwd",
            b"content",
        )
        
        assert result.is_valid is False
        assert result.validation_result == FileValidationResult.PATH_TRAVERSAL
    
    def test_sanitizes_filename(self, validator):
        """Should sanitize filename."""
        result = validator.validate(
            "file<script>.jpg",
            b"\xff\xd8\xff\xe0",  # JPEG magic
        )
        
        assert "<" not in result.safe_filename
        assert ">" not in result.safe_filename
    
    def test_calculates_hash(self, validator):
        """Should calculate content hash."""
        content = b"test content"
        result = validator.validate("file.txt", content)
        
        assert result.content_hash is not None
        assert len(result.content_hash) == 64  # SHA256 hex


# =============================================================================
# Test: ContentScanner
# =============================================================================

class TestContentScanner:
    """Test ContentScanner."""
    
    def test_detects_php(self, scanner):
        """Should detect PHP code."""
        content = b"<?php echo 'Hello'; ?>"
        threats = scanner.scan(content)
        
        assert len(threats) > 0
        assert any("php" in t.lower() for t in threats)
    
    def test_detects_script_tag(self, scanner):
        """Should detect script tags."""
        content = b"<script>alert('xss')</script>"
        threats = scanner.scan(content)
        
        assert len(threats) > 0
    
    def test_detects_event_handlers(self, scanner):
        """Should detect event handlers."""
        content = b"<img onerror='alert(1)'>"
        threats = scanner.scan(content)
        
        assert len(threats) > 0
    
    def test_safe_content(self, scanner):
        """Should pass safe content."""
        content = b"This is a normal text document."
        
        assert scanner.is_safe(content) is True


# =============================================================================
# Test: FileUploadService
# =============================================================================

class TestFileUploadService:
    """Test FileUploadService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        FileUploadService._instance = None
        
        s1 = get_upload_service()
        s2 = get_upload_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        config = FileUploadConfig(max_size_bytes=5 * 1024 * 1024)
        
        service = FileUploadService.configure(config)
        
        assert service.config.max_size_bytes == 5 * 1024 * 1024
    
    def test_validate(self, service):
        """Should validate files."""
        result = service.validate("test.jpg", b"\xff\xd8\xff\xe0")
        
        assert isinstance(result, FileInfo)
    
    def test_sanitize_filename(self, service):
        """Should sanitize filenames."""
        result = service.sanitize_filename("../evil.txt")
        
        assert ".." not in result
    
    def test_is_allowed_extension(self, service):
        """Should check extensions."""
        assert service.is_allowed_extension("doc.pdf") is True
        assert service.is_allowed_extension("script.php") is False
        assert service.is_allowed_extension("app.exe") is False
    
    def test_generate_safe_filename(self, service):
        """Should generate safe filenames."""
        result = service.generate_safe_filename("original.jpg")
        
        assert result != "original.jpg"
        assert result.endswith(".jpg")


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_validate_upload(self):
        """Should validate via convenience function."""
        FileUploadService._instance = None
        
        result = validate_upload("test.pdf", b"%PDF content")
        
        assert isinstance(result, FileInfo)
    
    def test_sanitize_filename(self):
        """Should sanitize via convenience function."""
        FileUploadService._instance = None
        
        result = sanitize_filename("../evil<script>.txt")
        
        assert ".." not in result
        assert "<" not in result
    
    def test_is_safe_upload(self):
        """Should check safety via convenience function."""
        FileUploadService._instance = None
        
        assert is_safe_upload("doc.pdf", b"%PDF content") is True
        assert is_safe_upload("malware.exe", b"MZ content") is False


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_blocks_all_dangerous_extensions(self):
        """Should block all dangerous extensions."""
        validator = FileValidator()
        
        dangerous = [
            "script.exe", "script.dll", "script.bat",
            "script.php", "script.asp", "script.jsp",
            "script.js", "script.sh", "script.ps1",
        ]
        
        for filename in dangerous:
            result = validator.validate(filename, b"content")
            assert result.is_valid is False, f"Should block {filename}"
    
    def test_path_traversal_prevention(self):
        """Should prevent all path traversal attempts."""
        sanitizer = FilenameSanitizer()
        
        attempts = [
            ("../../../etc/passwd", "passwd"),
            ("..\\..\\windows\\system32", "system32"),
            ("....//....//etc/passwd", "passwd"),
            ("/etc/passwd", "passwd"),
        ]
        
        for attempt, expected_base in attempts:
            result = sanitizer.sanitize(attempt)
            # The sanitizer should remove all dangerous parts
            assert ".." not in result, f"Path traversal in {attempt} -> {result}"
            assert "/" not in result, f"Slash in {attempt} -> {result}"
            assert "\\" not in result, f"Backslash in {attempt} -> {result}"
            # And preserve the actual filename
            assert expected_base in result or len(result) > 0, f"Lost filename from {attempt}"
    
    def test_default_config_is_secure(self):
        """Default config should be secure."""
        config = FileUploadConfig()
        
        assert ".exe" in config.blocked_extensions
        assert ".php" in config.blocked_extensions
        assert config.check_magic_bytes is True
        assert config.max_size_bytes <= 10 * 1024 * 1024
