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
        result = infer_obligation_type("Small farms shall not be required to maintain full traceability records.")
        assert result["obligation"] == "PROHIBITED"
        assert result["negation_detected"] is True


class TestInferObligationTypeConditional:
    """Hedge phrases alongside mandatory keywords → CONDITIONAL with WARNING."""

    def test_required_unless_exempt_is_conditional(self, caplog):
        with caplog.at_level(logging.WARNING, logger="services.nlp.app.extractor"):
            result = infer_obligation_type("All handlers are required to file unless exempt under subsection (b).")
        assert result["obligation"] == "CONDITIONAL"
        assert result["negation_detected"] is False
        assert any("CONDITIONAL" in r.message for r in caplog.records)

    def test_must_unless_is_conditional(self, caplog):
        with caplog.at_level(logging.WARNING, logger="services.nlp.app.extractor"):
            result = infer_obligation_type("The operator must comply unless provided that an exemption applies.")
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
            e for e in obl_ents if e["attrs"].get("negation_detected") and e["attrs"].get("obligation") == "PROHIBITED"
        ]
        assert prohibited, f"Expected PROHIBITED entity; got {[e['attrs'] for e in obl_ents]}"


# ----------------------------------------------------------------------
# #2942 — the canonical ObligationType the conversion layer persists
# ----------------------------------------------------------------------
#
# ``_convert_entities_to_extraction`` used to re-derive modality locally with
# a backward-only negation window, so "shall not" never registered as negated
# and every prohibition was persisted as ``ObligationType.MUST`` — the
# inversion of the rule. These cases pin BOTH directions: prohibitions must
# become MUST_NOT, and the near-miss phrasings that a naive negation window
# misfires on must NOT become MUST_NOT.

# (text, expected ObligationType, regex_extractor_sees_a_modal)
#
# ``regex_extractor_sees_a_modal`` records whether extractor.OBLIGATION_PATTERN
# (shall|must|required to|has to) fires for the sentence. When it does, the
# case is exercised through the real ``extract_entities`` → conversion path
# (entity attrs present). Every case is *also* exercised through a hand-built
# entity with no attrs, which is the path other producers and the existing
# consumer tests use.
_OBLIGATION_PHRASING_TABLE = [
    # --- Prohibitions: must be MUST_NOT, never MUST -----------------------
    ("The handler shall not exceed temperature limits.", "MUST_NOT", True),
    ("The supplier shall not bypass the traceability system.", "MUST_NOT", True),
    ("Facilities must not store product without labeling.", "MUST_NOT", True),
    ("A broker may not act as both buyer and seller.", "MUST_NOT", False),
    ("No person shall introduce adulterated food into interstate commerce.", "MUST_NOT", True),
    ("A covered entity is prohibited from altering traceability records.", "MUST_NOT", False),
    # --- Positive mandates: still MUST ------------------------------------
    ("The processor must retain records for two years.", "MUST", True),
    ("The supplier shall submit records monthly.", "MUST", True),
    (
        "No later than January 1, 2027, each covered entity shall maintain records.",
        "MUST",
        True,
    ),
    ("No fewer than two records shall be retained for each shipment.", "MUST", True),
    # --- Exemptions: the duty is lifted, so neither MUST nor MUST_NOT -----
    # "required to" is in OBLIGATION_PATTERN, so the regex extractor does see this one.
    ("Small farms are not required to file.", "MAY", True),
    (
        "Small farms shall not be required to maintain full traceability records.",
        "MAY",
        True,
    ),
    ("No person shall be required to submit duplicate records.", "MAY", True),
    ("Retailers are exempt from this record requirement.", "MAY", False),
    ("This rule does not require annual audits.", "MAY", False),
    ("There is no obligation to disclose origin.", "MAY", False),
    # --- Permissions and hedges -------------------------------------------
    ("The applicant may submit supporting evidence.", "MAY", False),
    (
        "All handlers are required to file unless exempt under subsection (b).",
        "SHOULD",
        True,
    ),
    # --- Savings clause: preserves permission, must NOT read as a ban ------
    (
        "Nothing in this section shall be construed to prohibit the sale of raw milk.",
        None,  # only the negative invariant is asserted for this one
        True,
    ),
]


def _convert(entities):
    from services.nlp.app.consumer import _convert_entities_to_extraction

    return _convert_entities_to_extraction(
        entities, doc_id="doc-2942", source_url="https://example.gov/rule.pdf"
    )


def _handbuilt_obligation(text):
    """An OBLIGATION entity with no ``attrs`` — the shape hand-built by other
    producers and by the existing consumer tests."""
    return [{"type": "OBLIGATION", "text": text, "start": 0, "end": len(text)}]


class TestConversionObligationTypeTable:
    """#2942 — obligation_type on the persisted ExtractionPayload."""

    @pytest.mark.parametrize("text,expected,_regex_sees", _OBLIGATION_PHRASING_TABLE)
    def test_handbuilt_entity_maps_to_expected_type(self, text, expected, _regex_sees):
        extractions = _convert(_handbuilt_obligation(text))
        assert extractions, f"expected one extraction for {text!r}"
        actual = extractions[0].obligation_type.value
        if expected is None:
            assert actual != "MUST_NOT", (
                f"{text!r} is a savings clause, not a prohibition; got {actual}"
            )
        else:
            assert actual == expected, f"{text!r} → {actual}, expected {expected}"

    @pytest.mark.parametrize("text,expected,regex_sees", _OBLIGATION_PHRASING_TABLE)
    def test_extracted_entity_maps_to_expected_type(self, text, expected, regex_sees):
        from services.nlp.app.extractor import extract_entities

        entities = extract_entities(text)
        obligations = [e for e in entities if e["type"] == "OBLIGATION"]
        if not regex_sees:
            assert not obligations, (
                f"table says OBLIGATION_PATTERN does not fire for {text!r}"
            )
            return
        assert obligations, f"expected an OBLIGATION entity for {text!r}"
        extractions = _convert(entities)
        obligation_extractions = [
            e for e in extractions if e.attributes.get("fact_type") != "compliance_date"
        ]
        assert obligation_extractions
        actual = obligation_extractions[0].obligation_type.value
        if expected is None:
            assert actual != "MUST_NOT", (
                f"{text!r} is a savings clause, not a prohibition; got {actual}"
            )
        else:
            assert actual == expected, f"{text!r} → {actual}, expected {expected}"

    def test_prohibitions_are_never_persisted_as_must(self):
        """The exact inversion #2942 describes: a ban stored as a mandate."""
        for text, expected, _ in _OBLIGATION_PHRASING_TABLE:
            if expected != "MUST_NOT":
                continue
            actual = _convert(_handbuilt_obligation(text))[0].obligation_type.value
            assert actual != "MUST", f"{text!r} persisted as a MANDATE"

    def test_must_not_is_actually_emitted(self):
        """ObligationType.MUST_NOT exists in the canonical schema; before
        #2942 nothing in the service ever produced it."""
        from shared.schemas import ObligationType

        emitted = {
            _convert(_handbuilt_obligation(text))[0].obligation_type
            for text, expected, _ in _OBLIGATION_PHRASING_TABLE
            if expected == "MUST_NOT"
        }
        assert ObligationType.MUST_NOT in emitted


class TestConversionAgreesWithInferObligationType:
    """#2942 acceptance: the conversion layer must not re-derive modality.

    Every sentence already covered by the #1299 suite above must map through
    ``infer_obligation_type``'s verdict rather than a second implementation.
    """

    _INFER_CASES = [
        "The supplier shall submit records monthly.",
        "The operator must maintain temperature logs.",
        "All entities are required to register.",
        "The applicant may submit supporting evidence.",
        "The handler shall not exceed temperature limits.",
        "Facilities must not store product without labeling.",
        "A broker may not act as both buyer and seller.",
        "Small farms are not required to file.",
        "There is no obligation to disclose origin.",
        "Retailers are exempt from this record requirement.",
        "This rule does not require annual audits.",
        "Small farms shall not be required to maintain full traceability records.",
        "All handlers are required to file unless exempt under subsection (b).",
        "The operator must comply unless provided that an exemption applies.",
        "The processor must retain records for two years.",
        "The supplier shall not bypass the traceability system.",
    ]

    # The one legal mapping from the extractor's modality vocabulary onto the
    # canonical enum. PROHIBITED splits: a ban is MUST_NOT, a lifted duty is a
    # permission (MAY) — turning an exemption into a ban is the same class of
    # inversion in the opposite direction.
    _LEGAL = {
        ("MANDATORY", None): "MUST",
        ("PERMITTED", None): "MAY",
        ("CONDITIONAL", None): "SHOULD",
        ("PROHIBITED", "prohibition"): "MUST_NOT",
        ("PROHIBITED", "exemption"): "MAY",
    }

    @pytest.mark.parametrize("text", _INFER_CASES)
    def test_conversion_agrees_with_infer(self, text):
        verdict = infer_obligation_type(text)
        key = (verdict["obligation"], verdict.get("negation_scope"))
        assert key in self._LEGAL, f"unmapped verdict {key} for {text!r}"
        actual = _convert(_handbuilt_obligation(text))[0].obligation_type.value
        assert actual == self._LEGAL[key], (
            f"{text!r}: infer_obligation_type says {key}, conversion says {actual}"
        )

    @pytest.mark.parametrize("text", _INFER_CASES)
    def test_negated_text_is_never_mandatory(self, text):
        """No sentence the extractor flags as negated may persist as MUST."""
        verdict = infer_obligation_type(text)
        if not verdict["negation_detected"]:
            return
        actual = _convert(_handbuilt_obligation(text))[0].obligation_type.value
        assert actual != "MUST", f"{text!r} is negated but persisted as MUST"


class TestNegationProvenanceReachesReviewer:
    """#2942 proposal 3 — a negated modality is visible in the review item."""

    def test_review_reasons_flag_negated_obligation(self):
        from services.nlp.app.consumer import _build_review_reasons

        extraction = _convert(
            _handbuilt_obligation("The handler shall not exceed temperature limits.")
        )[0]
        assert extraction.attributes.get("negation_detected") is True
        reasons = _build_review_reasons(extraction, "low")
        assert any(r["reason_code"] == "negated_obligation" for r in reasons), reasons

    def test_review_reasons_quiet_for_plain_mandate(self):
        from services.nlp.app.consumer import _build_review_reasons

        extraction = _convert(
            _handbuilt_obligation("The processor must retain records for two years.")
        )[0]
        reasons = _build_review_reasons(extraction, "low")
        assert not any(r["reason_code"] == "negated_obligation" for r in reasons)
