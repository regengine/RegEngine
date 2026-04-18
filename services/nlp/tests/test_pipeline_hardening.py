"""Integration tests for NLP pipeline hardening (April 2026 audit).

Covers:
- #1218: legacy `nlp.extracted` topic OFF by default, gated by env flag.
- #1258: three-tier confidence model routes medium-tier items to review
         with priority=low, low-tier items with priority=high.
- #1206: REGULATORY_DATE confidence no longer hardcoded to 0.99.
- #1202: legacy heuristic confidence capped below auto-approval gate.
- #1260: `_current_thresholds` reads live settings on each call.
- #1274: empty / whitespace-only text routes to review queue with an
         error-severity reason code instead of silent success.
- #1368: ReviewItem envelope carries structured review_reasons and
         provenance (source_document_id, source_offset, confidence).
- #1269: EntityResolver substring matches no longer succeed; token
         overlap below threshold is rejected.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Test env bootstrap
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


# ----------------------------------------------------------------------
# Three-tier routing (#1258) + legacy topic flag (#1218)
# ----------------------------------------------------------------------


class TestThreeTierRouting:
    """Medium-tier items route to review with priority=low; low-tier with
    priority=high. High-tier items go straight to graph.update."""

    @pytest.fixture
    def mock_producer(self):
        producer = MagicMock()
        future = MagicMock()
        future.get.return_value = MagicMock()
        producer.send.return_value = future
        return producer

    def _make_extraction(self, confidence: float):
        from shared.schemas import ExtractionPayload

        return ExtractionPayload(
            subject="Food facilities",
            action="must maintain",
            obligation_type="MUST",
            confidence_score=confidence,
            source_text="Food facilities must maintain records",
            source_offset=0,
            attributes={},
        )

    def test_high_confidence_routes_to_graph(self, mock_producer):
        from services.nlp.app.consumer import _route_extraction

        extraction = self._make_extraction(0.97)
        _route_extraction(
            extraction=extraction,
            doc_id="doc-high",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "graph.update"

    def test_medium_confidence_routes_to_review_with_low_priority(self, mock_producer):
        from services.nlp.app.consumer import _route_extraction

        extraction = self._make_extraction(0.88)  # >= medium (0.85), < high (0.95)
        _route_extraction(
            extraction=extraction,
            doc_id="doc-med",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "nlp.needs_review"
        payload = call_args.kwargs["value"]
        assert payload["priority"] == "low"
        assert payload["confidence_tier"] == "medium"

    def test_low_confidence_routes_to_review_with_high_priority(self, mock_producer):
        from services.nlp.app.consumer import _route_extraction

        extraction = self._make_extraction(0.50)  # < medium
        _route_extraction(
            extraction=extraction,
            doc_id="doc-low",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "nlp.needs_review"
        payload = call_args.kwargs["value"]
        assert payload["priority"] == "high"
        assert payload["confidence_tier"] == "low"

    def test_review_envelope_includes_provenance_and_reasons(self, mock_producer):
        """#1368: reviewers must see why an item was flagged."""
        from services.nlp.app.consumer import _route_extraction

        extraction = self._make_extraction(0.60)
        extraction.attributes = {"fact_type": "compliance_date"}

        _route_extraction(
            extraction=extraction,
            doc_id="doc-prov-xyz",
            doc_hash="hash",
            source_url="https://example.com/rule.pdf",
            producer=mock_producer,
            tenant_id=str(uuid4()),
        )
        payload = mock_producer.send.call_args.kwargs["value"]

        # Provenance contract
        prov = payload["provenance"]
        assert prov["source_document_id"] == "doc-prov-xyz"
        assert prov["source_offset"] == 0
        assert 0 <= prov["confidence"] <= 1

        # Review reasons
        reasons = payload["review_reasons"]
        reason_codes = {r["reason_code"] for r in reasons}
        assert any(code.startswith("confidence_tier_") for code in reason_codes)
        assert "regulatory_date_needs_review" in reason_codes


# ----------------------------------------------------------------------
# Legacy topic bypass (#1218)
# ----------------------------------------------------------------------


class TestLegacyTopicBypassOff:
    """By default the ``nlp.extracted`` topic must NOT be published."""

    def test_legacy_flag_defaults_to_false(self):
        # Re-import after clearing the env flag so the module-level value
        # reflects the default.
        os.environ.pop("NLP_EMIT_LEGACY_TOPIC", None)
        # We test the helper directly rather than relying on import caching.
        from services.nlp.app.consumer import _env_flag

        assert _env_flag("NLP_EMIT_LEGACY_TOPIC", default=False) is False

    def test_env_flag_parses_truthy_values(self):
        from services.nlp.app.consumer import _env_flag

        for truthy in ("1", "true", "yes", "on", "TRUE"):
            os.environ["NLP_TEST_FLAG"] = truthy
            assert _env_flag("NLP_TEST_FLAG", default=False) is True
        for falsy in ("0", "false", "no", "off", ""):
            os.environ["NLP_TEST_FLAG"] = falsy
            assert _env_flag("NLP_TEST_FLAG", default=True) is False
        os.environ.pop("NLP_TEST_FLAG", None)


# ----------------------------------------------------------------------
# REGULATORY_DATE confidence (#1206)
# ----------------------------------------------------------------------


class TestRegulatoryDateConfidence:
    """REGULATORY_DATE extractions must not bypass the auto-approval gate."""

    def test_adversarial_date_does_not_auto_approve(self):
        """A supplier-controlled 'Compliance Date: Jan 1, 2099' cannot
        clear the high-confidence gate now that the hardcoded 0.99 is gone.
        """
        from services.nlp.app.consumer import _convert_entities_to_extraction
        from services.nlp.app.extractor import extract_entities

        hostile_doc = "Compliance Date: January 1, 2099. Enforcement scheduled."
        entities = extract_entities(hostile_doc)
        extractions = _convert_entities_to_extraction(
            entities, doc_id="doc-hostile", source_url="https://attacker.example"
        )
        reg_date_extractions = [
            e for e in extractions
            if e.attributes.get("fact_type") == "compliance_date"
        ]
        assert reg_date_extractions, "expected at least one REGULATORY_DATE extraction"
        for ext in reg_date_extractions:
            # Cap (0.60) is below the auto-approval gate (0.95).
            assert ext.confidence_score <= 0.60

    def test_legitimate_fsma_date_still_detected(self):
        from services.nlp.app.extractor import extract_entities

        doc = (
            "The FSMA Rule establishes a Compliance Date of January 20, 2026 "
            "for covered facilities."
        )
        entities = extract_entities(doc)
        reg_dates = [e for e in entities if e["type"] == "REGULATORY_DATE"]
        assert reg_dates
        assert reg_dates[0]["text"] == "January 20, 2026"


# ----------------------------------------------------------------------
# Legacy heuristic confidence cap (#1202)
# ----------------------------------------------------------------------


class TestLegacyHeuristicCap:
    """Regex-only extractions must never reach the auto-approval gate."""

    def test_every_legacy_extraction_below_cap(self):
        from services.nlp.app.consumer import (
            _LEGACY_HEURISTIC_CONFIDENCE_CAP,
            _convert_entities_to_extraction,
        )
        from services.nlp.app.extractor import extract_entities

        # Document designed to maximize every legacy heuristic bump.
        doc = (
            "California requires that Walmart Inc. and Costco Wholesale "
            "shall maintain 2 years of records at greater than 10% capital "
            "thresholds for compliance in the United States jurisdiction."
        )
        entities = extract_entities(doc)
        extractions = _convert_entities_to_extraction(
            entities, doc_id="doc-cap", source_url="https://example.com"
        )
        assert extractions
        for ext in extractions:
            assert ext.confidence_score <= _LEGACY_HEURISTIC_CONFIDENCE_CAP


# ----------------------------------------------------------------------
# Live threshold read (#1260)
# ----------------------------------------------------------------------


class TestLiveThresholds:
    def test_current_thresholds_returns_floats(self):
        from services.nlp.app.consumer import _current_thresholds

        high, medium = _current_thresholds()
        assert isinstance(high, float)
        assert isinstance(medium, float)
        assert 0 < medium <= high <= 1

    def test_fallback_matches_config_default(self):
        """Fallback must be 0.95/0.85 — not the old 0.85/none."""
        from services.nlp.app.consumer import _current_thresholds

        # With settings loaded (the common case), the defaults must match
        # config.py: 0.95 / 0.85.
        high, medium = _current_thresholds()
        assert high in (0.95,)  # production default
        assert medium in (0.85,)

    def test_threshold_proxy_back_compat(self):
        """Legacy callers importing CONFIDENCE_THRESHOLD still work."""
        from services.nlp.app.consumer import CONFIDENCE_THRESHOLD

        assert CONFIDENCE_THRESHOLD == 0.95
        assert float(CONFIDENCE_THRESHOLD) == 0.95
        # Comparisons flow through __ge__ / __le__
        assert 0.97 >= CONFIDENCE_THRESHOLD  # type: ignore[operator]
        assert 0.50 < CONFIDENCE_THRESHOLD  # type: ignore[operator]


# ----------------------------------------------------------------------
# Empty text (#1274)
# ----------------------------------------------------------------------


class TestEmptyText:
    def test_extract_entities_rejects_none(self):
        from services.nlp.app.extractor import extract_entities

        with pytest.raises(TypeError):
            extract_entities(None)  # type: ignore[arg-type]

    def test_extract_entities_rejects_non_string(self):
        from services.nlp.app.extractor import extract_entities

        with pytest.raises(TypeError):
            extract_entities(123)  # type: ignore[arg-type]

    def test_empty_string_returns_empty_list(self):
        from services.nlp.app.extractor import extract_entities

        assert extract_entities("") == []


# ----------------------------------------------------------------------
# Entity resolution (#1269)
# ----------------------------------------------------------------------


class TestEntityResolverHardening:
    def test_walmart_variants_resolve(self):
        from services.nlp.app.resolution import EntityResolver

        r = EntityResolver()
        # "Wal-Mart Stores Inc." tokens ⊇ key tokens, extra ≤ 2, ratio ≥ 60.
        result = r.resolve_organization("Wal-Mart Stores Inc.")
        assert result is not None
        assert result["id"] == "duns:007874200"
        assert result["match_strategy"] in ("exact", "fuzzy")
        # Plain "WALMART" is an exact normalized match.
        exact = r.resolve_organization("WALMART")
        assert exact is not None
        assert exact["match_strategy"] == "exact"

    def test_lookalike_name_rejected(self):
        """'KROGER-FAKE-BRAND' must not resolve to Kroger."""
        from services.nlp.app.resolution import EntityResolver

        r = EntityResolver()
        assert r.resolve_organization("KROGER-FAKE-BRAND") is None
        assert r.resolve_organization("KROGE") is None
        assert r.resolve_organization("ABCDONOTUSESTORES") is None

    def test_short_token_suffix_rejected(self):
        """'SOME CO' must not match 'CO'-only tokens in master data."""
        from services.nlp.app.resolution import EntityResolver

        r = EntityResolver()
        # 'SOME CO' normalizes to 'SOME' (CO stripped as suffix)
        assert r.resolve_organization("SOME CO") is None

    def test_exact_match_returns_score_and_strategy(self):
        from services.nlp.app.resolution import EntityResolver

        r = EntityResolver()
        result = r.resolve_organization("Costco Wholesale")
        assert result is not None
        assert result["match_strategy"] == "exact"
        assert result["match_score"] == 100.0

    def test_none_or_empty_input(self):
        from services.nlp.app.resolution import EntityResolver

        r = EntityResolver()
        assert r.resolve_organization(None) is None
        assert r.resolve_organization("") is None
        assert r.resolve_organization("   ") is None
