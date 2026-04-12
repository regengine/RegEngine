"""Tests for PII masking utilities."""

from shared.pii import mask_email


class TestMaskEmail:
    def test_normal_email(self):
        assert mask_email("jane.doe@example.com") == "j***@example.com"

    def test_short_local_part(self):
        assert mask_email("a@b.com") == "a***@b.com"

    def test_none(self):
        assert mask_email(None) == "<no-email>"

    def test_empty_string(self):
        assert mask_email("") == "<no-email>"

    def test_no_at_sign(self):
        assert mask_email("not-an-email") == "***"

    def test_preserves_domain(self):
        assert mask_email("user@regengine.co") == "u***@regengine.co"

    def test_empty_local_part(self):
        assert mask_email("@example.com") == "***@example.com"

    def test_non_string_input(self):
        assert mask_email(12345) == "<no-email>"

    def test_multiple_at_signs(self):
        # rsplit on last @ — "weird@name"@domain
        assert mask_email("weird@name@domain.com") == "w***@domain.com"

    def test_long_email(self):
        result = mask_email("verylonglocalpart@verylongdomain.example.com")
        assert result == "v***@verylongdomain.example.com"
