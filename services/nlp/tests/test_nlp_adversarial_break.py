"""Adversarial break-it tests for services/nlp (Oct 2026 break-it pass).

Each test below pins a real break found by feeding hostile inputs at local
test setups only: a superlinear regex, a non-finite threshold value, and
confusing AttributeErrors on None / non-string input.
"""

import math
import time

import pytest

from services.nlp.app.classification import SignalClassifier
from services.nlp.app.extractor import extract_entities, infer_obligation_type
from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.query_planner import parse_query

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class TestOrgPatternComplexity:
    def test_long_word_run_without_suffix_completes_fast(self):
        # The org pattern is matched case-insensitively, so any long run of
        # plain words with no corporate suffix used to send failure
        # backtracking superlinear (4000 words took over 9 s; 20000 words
        # projected to minutes, stalling the extraction worker).
        text = "word " * 6000 + "!"
        started = time.perf_counter()
        ents = extract_entities(text)
        assert time.perf_counter() - started < 10
        assert isinstance(ents, list)

    def test_legitimate_org_names_still_extracted(self):
        text = "Tyson Foods, Inc. shipped 50 cases. Ralphs Grocery Company received them."
        orgs = [e for e in extract_entities(text) if e["type"] == "ORGANIZATION"]
        names = [e["text"] for e in orgs]
        assert any("Tyson Foods" in n for n in names)
        assert any("Ralphs Grocery Company" in n for n in names)


class TestThresholdFinite:
    def test_huge_digit_run_does_not_emit_inf(self):
        ents = extract_entities("Limit is " + "9" * 2000 + " percent.")
        thresholds = [e for e in ents if e["type"] == "THRESHOLD"]
        for entity in thresholds:
            assert math.isfinite(entity["attrs"]["value"])


class TestInputTypeGuards:
    def test_classify_signal_rejects_non_string(self):
        classifier = SignalClassifier()
        with pytest.raises(TypeError):
            classifier.classify_signal(None)
        with pytest.raises(TypeError):
            classifier.classify_signal(123)

    def test_classify_signal_empty_document_is_uncategorized(self):
        assert SignalClassifier().classify_signal("") == ("UNCATEGORIZED", "LOW", 0.0)

    def test_infer_obligation_type_rejects_non_string(self):
        with pytest.raises(TypeError):
            infer_obligation_type(None)
        with pytest.raises(TypeError):
            infer_obligation_type(123)

    def test_parse_query_rejects_non_string(self):
        with pytest.raises(TypeError):
            parse_query(None)
        with pytest.raises(TypeError):
            parse_query(123)

    def test_fsma_extract_rejects_non_string(self):
        extractor = FSMAExtractor()
        with pytest.raises(TypeError):
            extractor.extract(None, "d1", tenant_id=TENANT)
        with pytest.raises(TypeError):
            extractor.extract(123, "d1", tenant_id=TENANT)

    def test_fsma_extract_empty_document_is_reviewable_unknown(self):
        result = FSMAExtractor().extract("", "d1", tenant_id=TENANT)
        assert result.review_required is True
        assert result.ctes == []
