"""Data-free checks for the model's GLN field validator."""

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

from app import webhook_models as models  # noqa: E402


def _format_probe() -> str:
    """All-zero GS1 check-digit probe; this does not identify a location."""
    body = "0" * 12
    return body + str(models.calculate_gs1_check_digit(body))


class TestValidateGlnFormat:
    def test_valid_gln_returned_in_cleaned_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        probe = _format_probe()
        assert models.IngestEvent.validate_gln_format(probe[:1] + "-" + probe[1:]) == probe

    def test_wrong_length_raises_in_strict_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        with pytest.raises(ValueError, match="GLN must be exactly 13 digits"):
            models.IngestEvent.validate_gln_format("0")

    def test_bad_check_digit_raises_in_strict_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        probe = _format_probe()
        wrong_digit = str((int(probe[-1]) + 1) % 10)
        with pytest.raises(ValueError, match="check digit invalid"):
            models.IngestEvent.validate_gln_format(probe[:-1] + wrong_digit)

    def test_permissive_mode_accepts_invalid_gln(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "false")
        caplog.set_level("WARNING", logger="gln-validation")
        probe = _format_probe()
        invalid = probe[:-1] + str((int(probe[-1]) + 1) % 10)
        assert models.IngestEvent.validate_gln_format(invalid) == invalid
        assert any("invalid_gln" in record.message for record in caplog.records)
        assert invalid not in caplog.text

    def test_permissive_mode_wrong_length_returns_raw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "false")
        assert models.IngestEvent.validate_gln_format("0") == "0"

    def test_whitespace_only_gln_short_circuits(self) -> None:
        assert models.IngestEvent.validate_gln_format("   ") == "   "


def test_unknown_unit_warning_omits_uploaded_value(caplog: pytest.LogCaptureFixture) -> None:
    marker = "synthetic-private-unit"
    caplog.set_level("WARNING", logger="uom-validation")
    assert models.IngestEvent.validate_unit_of_measure(marker) == marker
    assert "unknown_unit" in caplog.text
    assert marker not in caplog.text
