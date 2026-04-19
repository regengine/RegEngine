"""Coverage for app/alerts.py severity mapping.

Locks the corrected FDA recall classification -> severity mapping after the
substring-ordering bug fix: "Class I" is a substring of "Class II" and
"Class III", so the original most-general-first order silently misclassified
Class II/III recalls as "critical".

Issue: #1342
"""

from __future__ import annotations

import pytest

from app.alerts import _severity_for_classification


class TestSeverityForClassification:
    def test_class_i_is_critical(self):
        assert _severity_for_classification("Class I") == "critical"

    def test_class_ii_is_high(self):
        assert _severity_for_classification("Class II") == "high"

    def test_class_iii_is_warning(self):
        assert _severity_for_classification("Class III") == "warning"

    def test_empty_string_is_warning(self):
        assert _severity_for_classification("") == "warning"

    def test_unknown_classification_is_warning(self):
        assert _severity_for_classification("Unclassified") == "warning"

    @pytest.mark.parametrize(
        "classification,expected",
        [
            ("Class I Recall", "critical"),
            ("Class II Recall", "high"),
            ("Class III Recall", "warning"),
            ("FDA Class I enforcement", "critical"),
            ("FDA Class II enforcement", "high"),
            ("FDA Class III enforcement", "warning"),
        ],
    )
    def test_substring_phrases_map_to_correct_severity(
        self, classification: str, expected: str
    ):
        """Regression: before the fix, Class II/III phrases returned "critical"
        because "Class I" matched first."""
        assert _severity_for_classification(classification) == expected
