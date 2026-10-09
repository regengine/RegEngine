"""Ambiguous numeric dates and fuzzy entity matches must be observable.

The audit flagged both heuristics as disclosed-but-open: a numeric date that
reads two ways (for example "01/02/2024") was normalized silently, and a
fuzzy organization match that relies on tokens beyond the master key resolved
with no review signal. These tests pin the closures: ambiguous dates keep the
pinned month-first value but log a warning, and fuzzy-with-extras matches
carry ``review_recommended`` from the resolver through to the reviewer payload.
"""

from __future__ import annotations

from structlog.testing import capture_logs

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.resolution import EntityResolver

AMBIGUOUS_EVENT = "ambiguous_numeric_date_assumed_month_first"


def _ambiguous_events(logs) -> list:
    return [log for log in logs if log.get("event") == AMBIGUOUS_EVENT]


class TestAmbiguousDateDisclosure:
    def test_ambiguous_date_keeps_pinned_month_first_value(self):
        extractor = FSMAExtractor()
        assert extractor._normalize_date("11/05/2025") == "2025-11-05"
        assert extractor._normalize_date("01/02/2024") == "2024-01-02"

    def test_ambiguous_date_logs_warning(self):
        extractor = FSMAExtractor()
        with capture_logs() as logs:
            extractor._normalize_date("01/02/2024")
        assert _ambiguous_events(logs), "expected an auditable warning for a date that reads two ways"

    def test_unambiguous_dates_stay_silent(self):
        extractor = FSMAExtractor()
        cases = {
            "2024-03-01": "2024-03-01",  # ISO, one reading
            "13/01/2024": "2024-01-13",  # day-first is the only valid parse
            "01/13/2024": "2024-01-13",  # month-first is the only valid parse
            "05/05/2024": "2024-05-05",  # both readings agree
        }
        with capture_logs() as logs:
            for raw, expected in cases.items():
                assert extractor._normalize_date(raw) == expected
        assert _ambiguous_events(logs) == []

    def test_unparseable_date_returned_as_is_without_warning(self):
        extractor = FSMAExtractor()
        with capture_logs() as logs:
            assert extractor._normalize_date("not a date") == "not a date"
        assert _ambiguous_events(logs) == []


class TestFuzzyReviewFlag:
    def test_exact_match_needs_no_review(self):
        result = EntityResolver().resolve_organization("WALMART")
        assert result is not None
        assert result["match_strategy"] == "exact"
        assert result["review_recommended"] is False

    def test_legitimate_extension_resolves_but_flagged(self):
        result = EntityResolver().resolve_organization("Wal-Mart Stores Inc.")
        assert result is not None
        assert result["match_strategy"] == "fuzzy"
        assert result["review_recommended"] is True

    def test_hostile_extension_resolves_but_flagged(self):
        """Two-token keys cannot separate "Wal Mart Stores" from "Wal Mart
        Fake" (both score 66.7%), so the hostile form still resolves. The fix
        is that it now carries the same review flag instead of passing
        silently."""
        result = EntityResolver().resolve_organization("Wal Mart Fake")
        assert result is not None
        assert result["review_recommended"] is True

    def test_rejected_name_still_returns_none(self):
        assert EntityResolver().resolve_organization("KROGER-FAKE-BRAND") is None

    def test_flag_reaches_reviewer_payload(self):
        from services.nlp.app.consumer import _convert_entities_to_extraction

        obligation_text = "The retailer shall maintain traceability records."

        def resolved_flag(raw_name: str) -> bool:
            entities = [
                {
                    "type": "OBLIGATION",
                    "text": obligation_text,
                    "start": 0,
                    "end": len(obligation_text),
                },
                {
                    "type": "ORGANIZATION",
                    "text": raw_name,
                    "start": len(obligation_text) + 1,
                    "end": len(obligation_text) + 1 + len(raw_name),
                    "attrs": {"name": raw_name},
                },
            ]
            extractions = _convert_entities_to_extraction(
                entities,
                doc_id="doc-review-flag",
                source_url="https://example.gov/rule.pdf",
            )
            assert extractions
            resolved = extractions[0].attributes.get("resolved_entities") or []
            assert resolved, "expected the organization to be recorded"
            return resolved[0]["review_recommended"]

        assert resolved_flag("Wal-Mart Stores Inc.") is True
        assert resolved_flag("WALMART") is False
