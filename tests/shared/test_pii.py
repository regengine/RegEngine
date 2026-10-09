"""Tests for PII masking utilities."""

from shared.pii import mask_email, redact_pii


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


class TestRedactPiiVendorBoundIdentifiers:
    """Structured identifiers must not reach the vendor in sample values.

    FSMA CSVs routinely carry GLNs, DUNS numbers and EINs; when the
    operator enables Jev sample values these cell values leave the
    process, so the redactor has to cover them.
    """

    def test_bare_gln_redacted(self):
        assert redact_pii("site 1234567890123") == "site [ID_REDACTED]"

    def test_bare_duns_redacted(self):
        assert redact_pii("duns 123456789") == "duns [ID_REDACTED]"

    def test_ein_redacted(self):
        assert redact_pii("ein 12-3456787") == "ein [EIN_REDACTED]"

    def test_spaced_card_number_redacted(self):
        result = redact_pii("card 4111 1111 1111 1111")
        assert "4111" not in result
        assert "[ID_REDACTED]" in result

    def test_short_values_untouched(self):
        assert redact_pii("qty 24") == "qty 24"
        assert redact_pii("2026-10-09") == "2026-10-09"

    def test_existing_patterns_still_hold(self):
        assert redact_pii("ssn 123-45-6789") == "ssn [SSN_REDACTED]"
        assert redact_pii("call 555-123-4567") == "call [PHONE_REDACTED]"
        assert redact_pii("mail jane.doe@example.com") == "mail [EMAIL_REDACTED]"
