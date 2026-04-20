"""Tests for negation-aware obligation_type inference (#1299).

Covers infer_obligation_type() in services/nlp/app/extractor.py and
the downstream mapping in the legacy consumer pipeline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractor import extract_entities, infer_obligation_type


class TestInferObligationTypePositiveModals:
    """Positive modal keywords without negation."""

    def test_shall_alone_is_mandatory(self):
        result = infer_obligation_type("The supplier shall submit records monthly.")
        assert result["obligation"] == "MANDATORY"
        assert result["negation_detected"] is False

    def test_must_alone_is_mandatory(self):
        result = infer_obligation_type("The operator must maintain temperature logs.")
        assert result["obligation"] == "MANDATORY"
        assert result["negation_detected"] is False

    def test_required_alone_is_mandatory(self):
        result = infer_obligation_type("All entities are required to register.")
        assert result["obligation"] == "MANDATORY"
        assert result["negation_detected"] is False

    def test_may_alone_is_permitted(self):
        result = infer_obligation_type("The applicant may submit supporting evidence.")
        assert result["obligation"] == "PERMITTED"
        assert result["negation_detected"] is False


class TestInferObligationTypeNegatedModals:
    """Negated modal keywords should produce PROHIBITED."""

    def test_shall_not_is_prohibited(self):
        result = infer_obligation_type("The handler shall not exceed temperature limits.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_must_not_is_prohibited(self):
        result = infer_obligation_type("Facilities must not store product without labeling.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_may_not_is_prohibited(self):
        result = infer_obligation_type("A broker may not act as both buyer and seller.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_not_required_is_prohibited(self):
        result = infer_obligation_type("Small farms are not required to file.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_no_obligation_is_prohibited(self):
        result = infer_obligation_type("There is no obligation to disclose origin.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_exempt_from_is_prohibited(self):
        result = infer_obligation_type("Retailers are exempt from this record requirement.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True

    def test_does_not_require_is_prohibited(self):
        result = infer_obligation_type("This rule does not require annual audits.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True


class TestInferObligationTypeDoubleHedge:
    """Double-hedge constructions should still resolve to PROHIBITED."""

    def test_shall_not_be_required_to_is_prohibited(self):
        """'shall not be required to' — double hedge, still PROHIBITED."""
        result = infer_obligation_type(
            "Small farms shall not be required to maintain full traceability records."
        )
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True


class TestInferObligationTypeConditional:
    """Hedge phrases alongside mandatory keywords → CONDITIONAL with WARNING."""

    def test_required_unless_exempt_is_conditional(self, caplog):
        with caplog.at_level(logging.WARNING, logger="services.nlp.app.extractor"):
            result = infer_obligation_type(
                "All handlers are required to file unless exempt under subsection (b)."
            )
        assert result["obligation"] == "CONDITIONAL"
        assert result["negation_detected"] is False
        assert any("CONDITIONAL" in r.message for r in caplog.records)

    def test_must_unless_is_conditional(self, caplog):
        with caplog.at_level(logging.WARNING, logger="services.nlp.app.extractor"):
            result = infer_obligation_type(
                "The operator must comply unless provided that an exemption applies."
            )
        assert result["obligation"] == "CONDITIONAL"


class TestExtractEntitiesNegationAttrs:
    """OBLIGATION entities produced by extract_entities() carry negation metadata."""

    def test_positive_obligation_attrs(self):
        text = "The processor must retain records for two years."
        ents = extract_entities(text)
        obl_ents = [e for e in ents if e["type"] == "OBLIGATION"]
        assert obl_ents, "Expected at least one OBLIGATION entity"
        for e in obl_ents:
            assert "obligation" in e["attrs"]
            assert "negation_detected" in e["attrs"]
        assert obl_ents[0]["attrs"]["obligation"] == "MANDATORY"
        assert obl_ents[0]["attrs"]["negation_detected"] is False

    def test_negated_obligation_attrs(self):
        text = "The supplier shall not bypass the traceability system."
        ents = extract_entities(text)
        obl_ents = [e for e in ents if e["type"] == "OBLIGATION"]
        assert obl_ents, "Expected at least one OBLIGATION entity"
        # At least one entity should detect negation and be PROHIBITED.
        prohibited = [
            e for e in obl_ents
            if e["attrs"].get("negation_detected") and e["attrs"].get("obligation") == "PROHIBITED"
        ]
        assert prohibited, f"Expected PROHIBITED entity; got {[e['attrs'] for e in obl_ents]}"
