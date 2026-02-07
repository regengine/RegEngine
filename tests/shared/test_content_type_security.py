"""
SEC-015: Tests for Content-Type Validation and Request Body Security.
"""

import json
import pytest


class TestContentTypeExceptions:
    """Test content-type exceptions."""

    def test_invalid_content_type_error(self):
        """Should create invalid content type error."""
        from shared.content_type_security import InvalidContentTypeError

        error = InvalidContentTypeError(
            "Invalid type",
            provided_type="text/invalid",
            expected_types=["application/json"],
        )

        assert "Invalid" in str(error)
        assert error.provided_type == "text/invalid"
        assert "application/json" in error.expected_types

    def test_content_size_limit_error(self):
        """Should create content size limit error."""
        from shared.content_type_security import ContentSizeLimitError

        error = ContentSizeLimitError(
            "Too large",
            size=20000,
            limit=10000,
        )

        assert error.size == 20000
        assert error.limit == 10000

    def test_malformed_content_error(self):
        """Should create malformed content error."""
        from shared.content_type_security import MalformedContentError

        error = MalformedContentError("Invalid JSON")

        assert "Invalid" in str(error)

    def test_content_sniffing_error(self):
        """Should create content sniffing error."""
        from shared.content_type_security import ContentSniffingError

        error = ContentSniffingError("MIME type mismatch")

        assert "mismatch" in str(error)


class TestCommonContentTypes:
    """Test common content type constants."""

    def test_json_type_defined(self):
        """Should have JSON type."""
        from shared.content_type_security import CommonContentTypes

        assert CommonContentTypes.JSON == "application/json"

    def test_api_types_defined(self):
        """Should have API types set."""
        from shared.content_type_security import CommonContentTypes

        assert CommonContentTypes.JSON in CommonContentTypes.API_TYPES
        assert CommonContentTypes.FORM_URLENCODED in CommonContentTypes.API_TYPES

    def test_safe_upload_types_defined(self):
        """Should have safe upload types."""
        from shared.content_type_security import CommonContentTypes

        assert CommonContentTypes.IMAGE_JPEG in CommonContentTypes.SAFE_UPLOAD_TYPES
        assert CommonContentTypes.PDF in CommonContentTypes.SAFE_UPLOAD_TYPES

    def test_dangerous_types_defined(self):
        """Should have dangerous types blocked."""
        from shared.content_type_security import CommonContentTypes

        assert CommonContentTypes.JAVASCRIPT in CommonContentTypes.DANGEROUS_TYPES


class TestContentTypeParser:
    """Test Content-Type parsing."""

    def test_parse_simple_type(self):
        """Should parse simple content type."""
        from shared.content_type_security import ContentTypeParser

        result = ContentTypeParser.parse("application/json")

        assert result is not None
        assert result.media_type == "application/json"
        assert result.main_type == "application"
        assert result.sub_type == "json"

    def test_parse_with_charset(self):
        """Should parse content type with charset."""
        from shared.content_type_security import ContentTypeParser

        result = ContentTypeParser.parse("text/html; charset=utf-8")

        assert result is not None
        assert result.charset == "utf-8"

    def test_parse_with_boundary(self):
        """Should parse multipart with boundary."""
        from shared.content_type_security import ContentTypeParser

        result = ContentTypeParser.parse(
            "multipart/form-data; boundary=----WebKitFormBoundary"
        )

        assert result is not None
        assert result.boundary == "----WebKitFormBoundary"

    def test_parse_multiple_params(self):
        """Should parse multiple parameters."""
        from shared.content_type_security import ContentTypeParser

        result = ContentTypeParser.parse(
            'text/plain; charset=utf-8; format="flowed"'
        )

        assert result is not None
        assert result.charset == "utf-8"
        assert result.parameters.get("format") == "flowed"

    def test_parse_invalid_returns_none(self):
        """Should return None for invalid types."""
        from shared.content_type_security import ContentTypeParser

        assert ContentTypeParser.parse("") is None
        assert ContentTypeParser.parse("invalid") is None
        assert ContentTypeParser.parse("missing/") is None

    def test_normalize_type(self):
        """Should normalize content type."""
        from shared.content_type_security import ContentTypeParser

        result = ContentTypeParser.normalize("Application/JSON; charset=UTF-8")

        assert result == "application/json"

    def test_parsed_matches(self):
        """Should match compatible types."""
        from shared.content_type_security import ContentTypeParser

        parsed = ContentTypeParser.parse("image/jpeg")

        assert parsed.matches("image/jpeg") is True
        assert parsed.matches("image/*") is True
        assert parsed.matches("*/*") is True
        assert parsed.matches("text/plain") is False


class TestContentTypeValidator:
    """Test Content-Type validation."""

    def test_validate_valid_type(self):
        """Should accept valid content type."""
        from shared.content_type_security import (
            ContentTypeValidator,
            CommonContentTypes,
        )

        validator = ContentTypeValidator(
            allowed_types=CommonContentTypes.API_TYPES
        )

        result = validator.validate("application/json")

        assert result.media_type == "application/json"

    def test_reject_blocked_type(self):
        """Should reject blocked content type."""
        from shared.content_type_security import (
            ContentTypeValidator,
            InvalidContentTypeError,
        )

        validator = ContentTypeValidator()

        with pytest.raises(InvalidContentTypeError, match="not allowed"):
            validator.validate("application/javascript")

    def test_reject_not_in_allowed(self):
        """Should reject types not in allowed list."""
        from shared.content_type_security import (
            ContentTypeValidator,
            InvalidContentTypeError,
        )

        validator = ContentTypeValidator(
            allowed_types={"application/json"}
        )

        with pytest.raises(InvalidContentTypeError, match="not in allowed"):
            validator.validate("text/plain")

    def test_validate_with_expected_types(self):
        """Should validate against expected types."""
        from shared.content_type_security import (
            ContentTypeValidator,
            InvalidContentTypeError,
        )

        validator = ContentTypeValidator()

        # Should pass
        result = validator.validate(
            "application/json",
            expected_types=["application/json", "text/plain"]
        )
        assert result.media_type == "application/json"

        # Should fail
        with pytest.raises(InvalidContentTypeError, match="Unexpected"):
            validator.validate(
                "application/xml",
                expected_types=["application/json"]
            )

    def test_reject_invalid_format(self):
        """Should reject invalid format."""
        from shared.content_type_security import (
            ContentTypeValidator,
            InvalidContentTypeError,
        )

        validator = ContentTypeValidator()

        with pytest.raises(InvalidContentTypeError, match="Invalid"):
            validator.validate("not-valid")

    def test_is_json(self):
        """Should detect JSON type."""
        from shared.content_type_security import ContentTypeValidator

        validator = ContentTypeValidator()

        assert validator.is_json("application/json") is True
        assert validator.is_json("application/json; charset=utf-8") is True
        assert validator.is_json("text/plain") is False

    def test_is_form(self):
        """Should detect form types."""
        from shared.content_type_security import ContentTypeValidator

        validator = ContentTypeValidator()

        assert validator.is_form("application/x-www-form-urlencoded") is True
        assert validator.is_form("multipart/form-data") is True
        assert validator.is_form("application/json") is False

    def test_is_multipart(self):
        """Should detect multipart types."""
        from shared.content_type_security import ContentTypeValidator

        validator = ContentTypeValidator()

        assert validator.is_multipart("multipart/form-data") is True
        assert validator.is_multipart("multipart/mixed") is True
        assert validator.is_multipart("application/json") is False

    def test_get_boundary(self):
        """Should extract boundary parameter."""
        from shared.content_type_security import ContentTypeValidator

        validator = ContentTypeValidator()

        boundary = validator.get_boundary(
            "multipart/form-data; boundary=myboundary123"
        )

        assert boundary == "myboundary123"


class TestContentBodyValidator:
    """Test request body validation."""

    def test_validate_size_under_limit(self):
        """Should accept content under limit."""
        from shared.content_type_security import ContentBodyValidator

        validator = ContentBodyValidator(max_size=1000)

        # Should not raise
        validator.validate_size(b"x" * 500)

    def test_validate_size_over_limit(self):
        """Should reject content over limit."""
        from shared.content_type_security import (
            ContentBodyValidator,
            ContentSizeLimitError,
        )

        validator = ContentBodyValidator(max_size=100)

        with pytest.raises(ContentSizeLimitError):
            validator.validate_size(b"x" * 200)

    def test_validate_json_valid(self):
        """Should accept valid JSON."""
        from shared.content_type_security import ContentBodyValidator

        validator = ContentBodyValidator()

        data = validator.validate_json('{"key": "value"}')

        assert data == {"key": "value"}

    def test_validate_json_bytes(self):
        """Should accept JSON as bytes."""
        from shared.content_type_security import ContentBodyValidator

        validator = ContentBodyValidator()

        data = validator.validate_json(b'{"key": "value"}')

        assert data == {"key": "value"}

    def test_validate_json_invalid(self):
        """Should reject invalid JSON."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator()

        with pytest.raises(MalformedContentError, match="Invalid JSON"):
            validator.validate_json("not json")

    def test_validate_json_too_deep(self):
        """Should reject deeply nested JSON."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator(max_json_depth=3)

        # Create deeply nested JSON
        deep = {"a": {"b": {"c": {"d": "value"}}}}

        with pytest.raises(MalformedContentError, match="depth"):
            validator.validate_json(json.dumps(deep))

    def test_validate_json_too_many_keys(self):
        """Should reject JSON with too many keys."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator(max_json_keys=10)

        # Create JSON with many keys
        many_keys = {f"key{i}": i for i in range(20)}

        with pytest.raises(MalformedContentError, match="key count"):
            validator.validate_json(json.dumps(many_keys))

    def test_validate_xml_valid(self):
        """Should accept basic valid XML."""
        from shared.content_type_security import ContentBodyValidator

        validator = ContentBodyValidator()

        # Should not raise
        validator.validate_xml("<root><child>value</child></root>")

    def test_validate_xml_with_declaration(self):
        """Should accept XML with declaration."""
        from shared.content_type_security import ContentBodyValidator

        validator = ContentBodyValidator()

        # Should not raise
        validator.validate_xml('<?xml version="1.0"?><root/>')

    def test_validate_xml_empty(self):
        """Should reject empty XML."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator()

        with pytest.raises(MalformedContentError, match="Empty"):
            validator.validate_xml("")

    def test_validate_xml_xxe_doctype(self):
        """Should reject XXE DOCTYPE attacks."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator()

        xxe = '''<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
                 <root>&xxe;</root>'''

        with pytest.raises(MalformedContentError, match="dangerous"):
            validator.validate_xml(xxe)

    def test_validate_xml_xxe_entity(self):
        """Should reject XXE ENTITY attacks."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator()

        xxe = '''<!ENTITY xxe SYSTEM "file:///etc/passwd">
                 <root>&xxe;</root>'''

        with pytest.raises(MalformedContentError, match="dangerous"):
            validator.validate_xml(xxe)


class TestMimeSniffingDetector:
    """Test MIME type sniffing detection."""

    def test_detect_png(self):
        """Should detect PNG from magic bytes."""
        from shared.content_type_security import MimeSniffingDetector

        png_magic = b'\x89PNG\r\n\x1a\n' + b'rest of file'

        result = MimeSniffingDetector.detect_type(png_magic)

        assert result == "image/png"

    def test_detect_jpeg(self):
        """Should detect JPEG from magic bytes."""
        from shared.content_type_security import MimeSniffingDetector

        jpeg_magic = b'\xff\xd8\xff' + b'rest of file'

        result = MimeSniffingDetector.detect_type(jpeg_magic)

        assert result == "image/jpeg"

    def test_detect_gif(self):
        """Should detect GIF from magic bytes."""
        from shared.content_type_security import MimeSniffingDetector

        gif_magic = b'GIF89a' + b'rest of file'

        result = MimeSniffingDetector.detect_type(gif_magic)

        assert result == "image/gif"

    def test_detect_pdf(self):
        """Should detect PDF from magic bytes."""
        from shared.content_type_security import MimeSniffingDetector

        pdf_magic = b'%PDF-1.4 rest of file'

        result = MimeSniffingDetector.detect_type(pdf_magic)

        assert result == "application/pdf"

    def test_detect_html(self):
        """Should detect HTML content."""
        from shared.content_type_security import MimeSniffingDetector

        html = b'<html><body>test</body></html>'

        result = MimeSniffingDetector.detect_type(html)

        assert result == "text/html"

    def test_detect_unknown(self):
        """Should return None for unknown type."""
        from shared.content_type_security import MimeSniffingDetector

        unknown = b'random binary content here'

        result = MimeSniffingDetector.detect_type(unknown)

        assert result is None

    def test_validate_match_success(self):
        """Should pass when content matches declared type."""
        from shared.content_type_security import MimeSniffingDetector

        png_content = b'\x89PNG\r\n\x1a\n' + b'rest of file'

        result = MimeSniffingDetector.validate_match(
            png_content,
            "image/png",
            strict=True,
        )

        assert result is True

    def test_validate_match_failure(self):
        """Should fail when content doesn't match declared type."""
        from shared.content_type_security import (
            MimeSniffingDetector,
            ContentSniffingError,
        )

        # PNG magic bytes declared as text/plain (different main type)
        png_content = b'\x89PNG\r\n\x1a\n' + b'rest of file'

        with pytest.raises(ContentSniffingError, match="mismatch"):
            MimeSniffingDetector.validate_match(
                png_content,
                "text/plain",  # Different main type than image/*
                strict=True,
            )

    def test_validate_match_same_main_type(self):
        """Should pass for same main type (e.g., both image/*)."""
        from shared.content_type_security import MimeSniffingDetector

        png_content = b'\x89PNG\r\n\x1a\n' + b'rest of file'

        # Detected as image/png, declared as image/gif
        # Same main type should pass
        result = MimeSniffingDetector.validate_match(
            png_content,
            "image/gif",
            strict=True,
        )

        assert result is True

    def test_is_potentially_executable(self):
        """Should detect potentially executable content."""
        from shared.content_type_security import MimeSniffingDetector

        html_script = b'<html><script>alert("xss")</script></html>'

        assert MimeSniffingDetector.is_potentially_executable(html_script) is True

    def test_is_not_executable(self):
        """Should not flag non-executable content."""
        from shared.content_type_security import MimeSniffingDetector

        plain_text = b'This is just plain text content'

        assert MimeSniffingDetector.is_potentially_executable(plain_text) is False


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_validate_json_request(self):
        """Should validate JSON request."""
        from shared.content_type_security import validate_json_request

        data = validate_json_request(
            "application/json",
            '{"key": "value"}',
        )

        assert data == {"key": "value"}

    def test_validate_json_request_wrong_type(self):
        """Should reject non-JSON content type."""
        from shared.content_type_security import (
            validate_json_request,
            InvalidContentTypeError,
        )

        with pytest.raises(InvalidContentTypeError):
            validate_json_request(
                "text/plain",
                '{"key": "value"}',
            )

    def test_validate_form_request(self):
        """Should validate form request."""
        from shared.content_type_security import validate_form_request

        result = validate_form_request(
            "application/x-www-form-urlencoded",
            body_size=100,
        )

        assert result.media_type == "application/x-www-form-urlencoded"

    def test_validate_form_request_multipart(self):
        """Should validate multipart form request."""
        from shared.content_type_security import validate_form_request

        result = validate_form_request(
            "multipart/form-data; boundary=----WebKitFormBoundary",
            body_size=100,
        )

        assert result.media_type == "multipart/form-data"

    def test_validate_file_upload(self):
        """Should validate file upload."""
        from shared.content_type_security import validate_file_upload

        jpeg_content = b'\xff\xd8\xff' + b'x' * 100

        result = validate_file_upload(
            "image/jpeg",
            jpeg_content,
        )

        assert result.media_type == "image/jpeg"

    def test_validate_file_upload_too_large(self):
        """Should reject too large upload."""
        from shared.content_type_security import (
            validate_file_upload,
            ContentSizeLimitError,
        )

        with pytest.raises(ContentSizeLimitError):
            validate_file_upload(
                "image/jpeg",
                b'x' * 1000000,
                max_size=1000,
            )

    def test_validate_file_upload_executable(self):
        """Should reject potentially executable upload."""
        from shared.content_type_security import (
            validate_file_upload,
            ContentSniffingError,
        )

        html_content = b'<html><script>alert("xss")</script></html>'

        with pytest.raises(ContentSniffingError, match="executable"):
            validate_file_upload(
                "text/plain",
                html_content,
            )


class TestSecurityHeaders:
    """Test security header generation."""

    def test_get_content_type_security_headers(self):
        """Should return security headers."""
        from shared.content_type_security import get_content_type_security_headers

        headers = get_content_type_security_headers()

        assert "X-Content-Type-Options" in headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in headers


class TestAPIValidator:
    """Test API validator factory."""

    def test_create_api_validator(self):
        """Should create API validator."""
        from shared.content_type_security import (
            create_api_validator,
            CommonContentTypes,
        )

        validator = create_api_validator()

        # Should accept JSON
        result = validator.validate("application/json")
        assert result.media_type == "application/json"

    def test_create_upload_validator(self):
        """Should create upload validator."""
        from shared.content_type_security import create_upload_validator

        validator = create_upload_validator()

        # Should accept JPEG
        result = validator.validate("image/jpeg")
        assert result.media_type == "image/jpeg"


class TestContentValidationConfig:
    """Test validation configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from shared.content_type_security import ContentValidationConfig

        config = ContentValidationConfig()

        assert config.max_size == 10 * 1024 * 1024
        assert config.require_content_type is True
        assert config.validate_json_structure is True


class TestRealWorldScenarios:
    """Test real-world attack scenarios."""

    def test_content_type_confusion_attack(self):
        """Should prevent content-type confusion."""
        from shared.content_type_security import (
            MimeSniffingDetector,
            ContentSniffingError,
        )

        # Attacker uploads JS disguised as image
        js_content = b'<script>alert("xss")</script>'

        with pytest.raises(ContentSniffingError):
            MimeSniffingDetector.validate_match(
                js_content,
                "image/jpeg",
                strict=True,
            )

    def test_xxe_via_content_type(self):
        """Should block XXE attacks."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator()

        xxe_payload = '''<?xml version="1.0"?>
        <!DOCTYPE foo [
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <root>&xxe;</root>'''

        with pytest.raises(MalformedContentError):
            validator.validate_xml(xxe_payload)

    def test_json_bomb(self):
        """Should limit JSON nesting to prevent bombs."""
        from shared.content_type_security import (
            ContentBodyValidator,
            MalformedContentError,
        )

        validator = ContentBodyValidator(max_json_depth=5)

        # Create deeply nested structure
        bomb = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}

        with pytest.raises(MalformedContentError, match="depth"):
            validator.validate_json(json.dumps(bomb))

    def test_polyglot_file(self):
        """Should detect polyglot files (multiple valid types)."""
        from shared.content_type_security import MimeSniffingDetector

        # GIF with embedded HTML/JS
        polyglot = b'GIF89a<script>alert("xss")</script>'

        # Should detect executable content even though it starts as GIF
        assert MimeSniffingDetector.is_potentially_executable(polyglot) is True
