"""Unit tests for disclaimer constants (app/disclaimers.py)."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from app.disclaimers import (
    DEMO_DATA_DISCLAIMER,
    SAMPLE_EXPORT_DISCLAIMER,
    SIMULATION_DISCLAIMER,
)


class TestDisclaimerConstants:
    """Tests for the three disclaimer constants."""

    def test_all_three_are_non_empty_strings(self):
        for name, val in [
            ("DEMO_DATA_DISCLAIMER", DEMO_DATA_DISCLAIMER),
            ("SIMULATION_DISCLAIMER", SIMULATION_DISCLAIMER),
            ("SAMPLE_EXPORT_DISCLAIMER", SAMPLE_EXPORT_DISCLAIMER),
        ]:
            assert isinstance(val, str), f"{name} is not a string"
            assert len(val) > 0, f"{name} is empty"

    def test_demo_disclaimer_contains_expected_keyword(self):
        assert "DEMO" in DEMO_DATA_DISCLAIMER.upper()

    def test_simulation_disclaimer_contains_expected_keyword(self):
        assert "SIMULATION" in SIMULATION_DISCLAIMER.upper()

    def test_sample_export_contains_expected_keyword(self):
        assert "sample" in SAMPLE_EXPORT_DISCLAIMER.lower()
