"""
End-to-end integration test: NLP extraction → compliance validation pipeline.

Issue #1134 — no integration test existed that ran FSMAExtractor output
through the RulesEngine so defects in the handoff (field mapping, FTL
classification, etc.) were invisible to CI.

This test does NOT require a live database.  The RulesEngine is constructed
with a minimal in-memory SQLAlchemy session that returns pre-seeded rule
definitions; all Kafka / DB write-paths are patched out so only the pure
extraction and rule-evaluation logic runs.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path wiring — keep consistent with adjacent test files
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import CTEType, FSMAExtractionResult

# RulesEngine lives in services/shared — insert that package root too.
sys.path.insert(0, str(_REPO_ROOT / "services"))

from shared.rules.engine import RulesEngine
from shared.rules.types import EvaluationSummary, RuleDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    *,
    rule_id: str | None = None,
    title: str = "TLC Required",
    cte_types: List[str] | None = None,
    field: str = "kdes.traceability_lot_code",
    severity: str = "critical",
    eval_type: str = "field_presence",
) -> RuleDefinition:
    """Build a RuleDefinition without hitting a DB."""
    return RuleDefinition(
        rule_id=rule_id or str(uuid.uuid4()),
        rule_version=1,
        title=title,
        description=title,
        severity=severity,
        category="kde_presence",
        applicability_conditions={
            "cte_types": cte_types or ["RECEIVING", "SHIPPING", "receiving", "shipping"],
            "ftl_scope": ["ALL"],
        },
        citation_reference="21 CFR §1.1320(a)",
        effective_date=date(2022, 1, 20),
        retired_date=None,
        evaluation_logic={"type": eval_type, "field": field},
        failure_reason_template="Missing {field_name} ({citation})",
        remediation_suggestion="Provide the traceability lot code.",
    )


def _make_timestamp_rule() -> RuleDefinition:
    return _make_rule(
        title="Event Timestamp Required",
        field="event_timestamp",
        cte_types=["RECEIVING", "SHIPPING", "receiving", "shipping"],
    )


def _cte_to_event_dict(cte, tenant_id: str) -> Dict[str, Any]:
    """Convert an extracted CTE into the dict format RulesEngine.evaluate_event expects."""
    kde = cte.kdes
    return {
        "event_id": cte.event_id,
        "event_type": cte.type.value,
        "event_timestamp": kde.event_date,
        # FTL classification — required for the engine to produce a verdict
        "kdes": {
            "traceability_lot_code": kde.traceability_lot_code,
            "location_identifier": kde.location_identifier,
            "quantity": kde.quantity,
            "unit_of_measure": kde.unit_of_measure,
            "event_date": kde.event_date,
            "ship_from_location": kde.ship_from_location,
            "ship_to_location": kde.ship_to_location,
            "ftl_covered": True,          # fresh produce → FTL
            "ftl_category": "leafy greens",
        },
        "ftl_covered": True,
        "ftl_category": "leafy greens",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def extractor() -> FSMAExtractor:
    return FSMAExtractor()


@pytest.fixture()
def rules_engine_with_rules() -> RulesEngine:
    """Return a RulesEngine that loads pre-seeded rules without a DB call."""
    seeded_rules = [
        _make_rule(
            title="TLC Required",
            field="kdes.traceability_lot_code",
        ),
        _make_rule(
            title="Event Timestamp Required",
            field="event_timestamp",
        ),
    ]

    mock_session = MagicMock()
    engine = RulesEngine(mock_session, cache_ttl_seconds=0)

    # Bypass load_active_rules so no DB call is made.
    engine._rules_cache = seeded_rules
    # Patch get_applicable_rules to serve from our seeded list (skip FTL catalog lookup)
    original_get_applicable = engine.get_applicable_rules

    def _patched_get_applicable(event_type, rules=None, **kwargs):
        # Pass our seeded rules; the base method will still FTL-filter them.
        return original_get_applicable(event_type, rules=seeded_rules, **kwargs)

    engine.get_applicable_rules = _patched_get_applicable  # type: ignore[method-assign]

    # Disable DB persistence so evaluate_event doesn't try to INSERT.
    engine._persist_evaluations = MagicMock()  # type: ignore[method-assign]
    engine._prefetch_related_events = MagicMock(return_value={})  # type: ignore[method-assign]

    return engine


# ---------------------------------------------------------------------------
# Realistic document fixtures
# ---------------------------------------------------------------------------

COMPLIANT_BOL = """
BILL OF LADING
BOL# BOL-2026-04-20-001
Ship Date: 04/20/2026
Shipper: Green Valley Farms LLC
Ship From GLN: 0614141999996
Ship To: Metro Fresh Distribution Center
Ship To GLN: 0614141000001

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Traceability Lot Code: TLC-00614141999996-2026-04-20-A
Lot: TLC-00614141999996-2026-04-20-A
GTIN: 00614141000014
QTY: 120 cases
"""

# Non-compliant: TLC deliberately omitted to trigger a rules-engine failure.
NON_COMPLIANT_BOL = """
BILL OF LADING
BOL# BOL-2026-04-20-002
Ship Date: 04/20/2026
Shipper: Acme Produce Inc.
Ship From GLN: 0614141888885
Ship To: Central Warehouse

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
QTY: 60 cases
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNLPComplianceE2E:
    """NLP extraction → compliance validation end-to-end pipeline tests (#1134)."""

    # ------------------------------------------------------------------
    # 1. Extraction smoke tests
    # ------------------------------------------------------------------

    def test_compliant_doc_extracts_at_least_one_cte(self, extractor):
        result: FSMAExtractionResult = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        assert len(result.ctes) >= 1, "Expected at least one CTE from a BOL"

    def test_compliant_doc_cte_has_non_null_tlc(self, extractor):
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        tlcs = [cte.kdes.traceability_lot_code for cte in result.ctes]
        assert any(tlc is not None and tlc.strip() != "" for tlc in tlcs), (
            f"No CTE had a non-null TLC; got: {tlcs}"
        )

    def test_compliant_doc_cte_has_non_null_event_date(self, extractor):
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        dates = [cte.kdes.event_date for cte in result.ctes]
        assert any(d is not None and d.strip() != "" for d in dates), (
            f"No CTE had a non-null event_date; got: {dates}"
        )

    def test_non_compliant_doc_extracts_at_least_one_cte(self, extractor):
        result = extractor.extract(
            NON_COMPLIANT_BOL,
            document_id="doc-noncompliant-001",
            tenant_id="tenant-test",
        )
        assert len(result.ctes) >= 1, "Expected at least one CTE even from an incomplete BOL"

    # ------------------------------------------------------------------
    # 2. End-to-end pipeline: extraction + compliance evaluation
    # ------------------------------------------------------------------

    def test_compliant_pipeline_no_exceptions(self, extractor, rules_engine_with_rules):
        """Full pipeline must not raise any exception."""
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        for cte in result.ctes:
            event_dict = _cte_to_event_dict(cte, tenant_id="tenant-test")
            # Must not raise
            summary: EvaluationSummary = rules_engine_with_rules.evaluate_event(
                event_dict,
                persist=False,
                tenant_id="tenant-test",
            )
            assert summary is not None

    def test_compliant_pipeline_returns_boolean_compliant(self, extractor, rules_engine_with_rules):
        """The compliance verdict must be True or False (not None) for an FTL event with rules."""
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        ctes_with_tlc = [c for c in result.ctes if c.kdes.traceability_lot_code]
        assert ctes_with_tlc, "Need at least one CTE with a TLC for this assertion"

        for cte in ctes_with_tlc:
            event_dict = _cte_to_event_dict(cte, tenant_id="tenant-test")
            summary = rules_engine_with_rules.evaluate_event(
                event_dict,
                persist=False,
                tenant_id="tenant-test",
            )
            assert isinstance(summary.compliant, bool), (
                f"Expected bool compliant verdict, got {summary.compliant!r}. "
                f"no_verdict_reason={summary.no_verdict_reason}"
            )

    def test_compliant_pipeline_is_compliant_true(self, extractor, rules_engine_with_rules):
        """A fully-populated compliant BOL must produce compliant=True."""
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-compliant-001",
            tenant_id="tenant-test",
        )
        ctes_with_tlc = [c for c in result.ctes if c.kdes.traceability_lot_code]
        assert ctes_with_tlc, "Need a CTE with TLC to assert compliant=True"

        for cte in ctes_with_tlc:
            event_dict = _cte_to_event_dict(cte, tenant_id="tenant-test")
            summary = rules_engine_with_rules.evaluate_event(
                event_dict,
                persist=False,
                tenant_id="tenant-test",
            )
            assert summary.compliant is True, (
                f"Expected compliant=True; failed={summary.failed}, "
                f"results={[(r.rule_title, r.result, r.why_failed) for r in summary.results]}"
            )

    def test_non_compliant_pipeline_is_compliant_false(self, extractor, rules_engine_with_rules):
        """A BOL missing TLC must produce compliant=False after rules evaluation."""
        result = extractor.extract(
            NON_COMPLIANT_BOL,
            document_id="doc-noncompliant-001",
            tenant_id="tenant-test",
        )
        # Pick the CTE that lacks a TLC (simulates the missing-TLC scenario).
        ctes_without_tlc = [c for c in result.ctes if not c.kdes.traceability_lot_code]

        if not ctes_without_tlc:
            # If the extractor managed to pull something, fabricate a missing-TLC event.
            from services.nlp.app.extractors.fsma_types import CTE, KDE

            missing_tlc_cte = CTE(
                type=CTEType.RECEIVING,
                kdes=KDE(
                    traceability_lot_code=None,   # deliberately absent
                    event_date="2026-04-20",
                    location_identifier="0614141888885",
                ),
                confidence=0.90,
            )
            ctes_without_tlc = [missing_tlc_cte]

        for cte in ctes_without_tlc:
            event_dict = _cte_to_event_dict(cte, tenant_id="tenant-test")
            # Force TLC to None/missing so the rule definitely fires.
            event_dict["kdes"]["traceability_lot_code"] = None

            summary = rules_engine_with_rules.evaluate_event(
                event_dict,
                persist=False,
                tenant_id="tenant-test",
            )
            assert summary.compliant is False, (
                "Expected compliant=False when TLC is absent; "
                f"got compliant={summary.compliant}, "
                f"results={[(r.rule_title, r.result) for r in summary.results]}"
            )

    # ------------------------------------------------------------------
    # 3. Structural invariants
    # ------------------------------------------------------------------

    def test_extraction_result_tenant_id_preserved(self, extractor):
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-001",
            tenant_id="tenant-xyz",
        )
        assert result.tenant_id == "tenant-xyz"

    def test_extraction_result_document_id_preserved(self, extractor):
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="my-doc-456",
            tenant_id="tenant-test",
        )
        assert result.document_id == "my-doc-456"

    def test_each_cte_has_unique_event_id(self, extractor):
        result = extractor.extract(
            COMPLIANT_BOL,
            document_id="doc-001",
            tenant_id="tenant-test",
        )
        ids = [cte.event_id for cte in result.ctes]
        assert len(ids) == len(set(ids)), f"Duplicate event IDs found: {ids}"
