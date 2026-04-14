"""Tests for the base NLP extractor (services/nlp/app/extractor.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractor import extract_entities, extract_fsma_facts


class TestExtractFsmaFacts:
    """Regression tests for FSMA compliance date extraction."""

    @pytest.mark.parametrize(
        "month",
        [
            "January", "February", "March", "April",
            "May", "June", "July", "August",
            "September", "October", "November", "December",
        ],
    )
    def test_fsma_facts_all_months(self, month):
        """Every calendar month must be matched when compliance context is present."""
        text = f"The compliance date is {month} 15, 2026 per FDA enforcement guidance."
        facts = extract_fsma_facts(text)
        assert any(
            f["type"] == "REGULATORY_DATE" for f in facts
        ), f"REGULATORY_DATE not extracted for {month}"

    def test_fsma_facts_january_and_july_still_work(self):
        """Original January/July dates must continue to match."""
        for date_str in ["January 20, 2026", "July 20, 2028"]:
            text = f"The compliance date is {date_str} per enforcement rule."
            facts = extract_fsma_facts(text)
            assert any(f["type"] == "REGULATORY_DATE" for f in facts)

    def test_fsma_facts_no_match_without_context(self):
        """Dates without compliance/enforcement context should not match."""
        text = "The picnic is on October 15, 2026 at the park."
        facts = extract_fsma_facts(text)
        assert not any(f["type"] == "REGULATORY_DATE" for f in facts)

    def test_fsma_facts_attrs(self):
        """Extracted REGULATORY_DATE should carry expected attrs."""
        text = "Enforcement begins March 1, 2027 as the compliance date."
        facts = extract_fsma_facts(text)
        date_facts = [f for f in facts if f["type"] == "REGULATORY_DATE"]
        assert len(date_facts) == 1
        assert date_facts[0]["text"] == "March 1, 2027"
        assert date_facts[0]["attrs"]["key"] == "Compliance Date"

    def test_extract_entities_includes_fsma_dates(self):
        """extract_entities() should surface REGULATORY_DATE via extract_fsma_facts."""
        text = "FDA enforcement effective October 1, 2026 compliance date."
        ents = extract_entities(text)
        assert any(e["type"] == "REGULATORY_DATE" for e in ents)
