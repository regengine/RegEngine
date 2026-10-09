"""Focused coverage for services/nlp/app/consumer/conversion.py.

Covers the legacy entity conversion, the LLM-results bridge, and the
regulatory-date scorer, including edge and error cases. No network access,
no external services.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.schemas import ObligationType

from services.nlp.app.consumer.constants import (
    _LEGACY_HEURISTIC_CONFIDENCE_CAP,
    _LLM_EXTRACTION_CONFIDENCE_CAP,
)
from services.nlp.app.consumer.conversion import (
    _convert_entities_to_extraction,
    _convert_llm_results_to_extractions,
    _obligation_type_for,
    _score_regulatory_date,
)

DOC = "doc-1"
URL = "https://example.gov/rule.pdf"


def _obl(text, start=0, attrs=None):
    ent = {"type": "OBLIGATION", "text": text, "start": start, "end": start + len(text)}
    if attrs is not None:
        ent["attrs"] = attrs
    return ent


class TestConvertEntitiesToExtraction:
    def test_empty_entities_returns_empty(self):
        assert _convert_entities_to_extraction([], DOC, URL) == []

    def test_plain_mandate_is_must_and_capped(self):
        out = _convert_entities_to_extraction([_obl("The processor must retain records for two years.")], DOC, URL)
        assert len(out) == 1
        item = out[0]
        assert item.obligation_type == ObligationType.MUST
        assert item.confidence_score <= _LEGACY_HEURISTIC_CONFIDENCE_CAP
        assert item.attributes["document_id"] == DOC
        assert item.attributes["source_url"] == URL
        assert item.attributes["extractor"] == "legacy_regex_v1"

    def test_prohibition_is_must_not(self):
        out = _convert_entities_to_extraction([_obl("The handler shall not exceed temperature limits.")], DOC, URL)
        assert out[0].obligation_type == ObligationType.MUST_NOT

    def test_nearby_threshold_and_jurisdiction_attach(self):
        entities = [
            _obl("Facilities must maintain 10 percent reserve.", start=100),
            {
                "type": "THRESHOLD",
                "text": "10 percent",
                "start": 150,
                "attrs": {"value": 10, "unit_normalized": "percent"},
            },
            {
                "type": "JURISDICTION",
                "text": "California",
                "start": 200,
                "attrs": {"name": "California"},
            },
        ]
        out = _convert_entities_to_extraction(entities, DOC, URL)
        assert len(out) == 1
        assert len(out[0].thresholds) == 1
        assert out[0].thresholds[0].value == 10
        assert out[0].jurisdiction == "California"

    def test_distant_threshold_does_not_attach(self):
        entities = [
            _obl("Banks must maintain capital.", start=0),
            {
                "type": "THRESHOLD",
                "text": "99 percent",
                "start": 5000,
                "attrs": {"value": 99, "unit_normalized": "percent"},
            },
        ]
        out = _convert_entities_to_extraction(entities, DOC, URL)
        assert out[0].thresholds == []

    def test_regulatory_date_becomes_compliance_fact(self):
        entities = [
            {
                "type": "REGULATORY_DATE",
                "text": "January 20, 2026",
                "start": 10,
                "attrs": {"value": "January 20, 2026", "context_distance": 5},
            }
        ]
        out = _convert_entities_to_extraction(entities, DOC, URL)
        assert len(out) == 1
        assert out[0].attributes["fact_type"] == "compliance_date"
        assert out[0].obligation_type == ObligationType.MUST
        assert out[0].confidence_score <= _LEGACY_HEURISTIC_CONFIDENCE_CAP


class TestObligationTypeFor:
    def test_unmapped_verdict_falls_back_to_should(self):
        assert _obligation_type_for({"obligation": "BOGUS"}) == ObligationType.SHOULD

    def test_none_verdict_falls_back_to_should(self):
        assert _obligation_type_for({}) == ObligationType.SHOULD


class TestScoreRegulatoryDate:
    def test_garbage_date_scores_low(self):
        assert _score_regulatory_date("not a date", {}) == 0.30

    def test_none_date_scores_low(self):
        assert _score_regulatory_date(None, {}) == 0.30

    def test_good_date_never_exceeds_cap(self):
        score = _score_regulatory_date("January 20, 2026", {"context_distance": 5})
        assert score <= _LEGACY_HEURISTIC_CONFIDENCE_CAP
        assert score > 0.30


class TestConvertLlmResults:
    def test_requirement_maps_and_caps_confidence(self):
        out = _convert_llm_results_to_extractions(
            [
                {
                    "provision_text": "Farms must keep records for two years.",
                    "obligation_type": "REQUIREMENT",
                    "confidence": 0.99,
                }
            ],
            DOC,
            URL,
        )
        assert len(out) == 1
        assert out[0].obligation_type == ObligationType.MUST
        assert out[0].confidence_score <= _LLM_EXTRACTION_CONFIDENCE_CAP
        assert out[0].attributes["llm_reported_confidence"] == 0.99

    def test_prohibition_maps_to_must_not(self):
        out = _convert_llm_results_to_extractions(
            [
                {
                    "provision_text": "Do not alter traceability records.",
                    "obligation_type": "PROHIBITION",
                    "confidence": 0.5,
                }
            ],
            DOC,
            URL,
        )
        assert out[0].obligation_type == ObligationType.MUST_NOT
        assert out[0].action == "must not"

    def test_empty_provision_text_is_dropped(self):
        out = _convert_llm_results_to_extractions(
            [{"provision_text": "   ", "obligation_type": "REQUIREMENT"}],
            DOC,
            URL,
        )
        assert out == []

    def test_unmapped_type_falls_back_to_should_and_flags(self):
        out = _convert_llm_results_to_extractions(
            [
                {
                    "provision_text": "Something unclear applies here.",
                    "obligation_type": "MYSTERY",
                    "confidence": 0.4,
                }
            ],
            DOC,
            URL,
        )
        assert out[0].obligation_type == ObligationType.SHOULD
        assert out[0].attributes["llm_obligation_type_unmapped"] is True

    def test_bad_confidence_and_span_default_safely(self):
        out = _convert_llm_results_to_extractions(
            [
                {
                    "provision_text": "Farms must keep records.",
                    "obligation_type": "REQUIREMENT",
                    "confidence": "nonsense",
                }
            ],
            DOC,
            URL,
        )
        assert out[0].confidence_score == 0.0
        assert out[0].source_offset == 0
