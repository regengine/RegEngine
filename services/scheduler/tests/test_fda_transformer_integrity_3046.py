"""FDA notices cannot fabricate traceability evidence (#3046)."""

from datetime import datetime, timezone

import pytest

from services.scheduler.app.fda_fsma_transformer import FSMAEventTransformer
from services.scheduler.app.models import EnforcementItem, SourceType


def item(**raw_data):
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="F-123",
        title="Recall notice",
        url="https://www.fda.gov/example",
        published_date=datetime(2026, 9, 4, tzinfo=timezone.utc),
        raw_data=raw_data,
    )


def test_empty_notice_never_invents_identifiers():
    event = FSMAEventTransformer().transform(item())
    assert event["lot"]["tlc"] is None
    assert event["facility"]["gln"] is None
    assert event["facility"]["facility_type"] is None
    assert event["facility"]["country"] is None
    assert event["lot"]["unit_of_measure"] is None
    assert event["lot"]["product_description"] is None
    assert event["cte_type"] is None
    assert event["is_traceability_evidence"] is False
    assert event["requires_review"] is True
    assert event["confidence"] == 0


@pytest.mark.parametrize("gln", ["0614141000004", "FDA1234567890", "123", 614141000005])  # pragma: allowlist secret
def test_invalid_source_gln_is_absent(gln):
    assert FSMAEventTransformer().transform(item(gln=gln))["facility"]["gln"] is None


def test_only_explicit_identifiers_survive():
    event = FSMAEventTransformer().transform(item(gln="0614141000005", traceability_lot_code="LOT-123"))
    assert event["lot"]["tlc"] == "LOT-123"
    assert event["facility"]["gln"] == "0614141000005"
    assert event["confidence"] == pytest.approx(2 / 6)


def test_dead_pipeline_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REGENGINE_ENABLE_EXPERIMENTAL_RECALL_EVENTS", raising=False)
    assert FSMAEventTransformer().transform_batch([item()]) == []
    monkeypatch.setenv("REGENGINE_ENABLE_EXPERIMENTAL_RECALL_EVENTS", "1")
    assert len(FSMAEventTransformer().transform_batch([item()])) == 1


@pytest.mark.parametrize(
    "classification,flag", [("Class I", "FDA_CLASS_I"), ("Class II", "FDA_CLASS_II"), ("Class III", "FDA_CLASS_III")]
)
def test_recall_classification_is_exact(classification, flag):
    flags = FSMAEventTransformer().transform(item(classification=classification))["fsma_metadata"]["risk_flags"]
    assert flag in flags
    assert len([f for f in flags if f.startswith("FDA_CLASS")]) == 1
