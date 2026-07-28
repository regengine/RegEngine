"""FTL hint propagation at normalization time (#1346).

Before the fix: no ingest path wrote ``ftl_covered``/``ftl_category``
into kdes unless the caller supplied them explicitly, so every event
evaluated to ``no_verdict_reason="ftl_classification_missing"`` and
``RULES_ENGINE_ENFORCE=cte_only`` was a silent no-op (verified against
prod 2026-07-28: 17/17 events with zero FTL signals).

After the fix: ``TraceabilityEvent.prepare_for_persistence`` derives a
positive-only hint from the product text via
``shared.rules.ftl.infer_ftl_category_from_text`` before hashing, so
the sha256/idempotency_key cover the enriched kdes and the rules engine
receives a classification on every normalizer path (webhook, EPCIS,
CSV).

Pure-Python; no DB.
"""

from __future__ import annotations

from uuid import uuid4

from shared.canonical_event import (
    CTEType,
    IngestionSource,
    TraceabilityEvent,
    normalize_csv_row,
)
from shared.rules.ftl import (
    event_has_ftl_hint,
    infer_ftl_category_from_text,
    is_ftl_food,
)


def _make_event(product_reference: str, kdes: dict | None = None) -> TraceabilityEvent:
    return TraceabilityEvent(
        tenant_id=uuid4(),
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp="2026-07-28T12:00:00+00:00",
        product_reference=product_reference,
        lot_reference="LOT-1",
        traceability_lot_code="TLC-1",
        quantity=1.0,
        unit_of_measure="case",
        kdes=dict(kdes or {}),
        raw_payload={"product_description": product_reference},
    )


# ---------------------------------------------------------------------------
# infer_ftl_category_from_text
# ---------------------------------------------------------------------------


def test_infer_matches_known_keywords():
    assert infer_ftl_category_from_text("Romaine Hearts 24ct") == "Leafy Greens"
    assert infer_ftl_category_from_text("Fresh Atlantic Salmon Fillet") == "Finfish"
    assert infer_ftl_category_from_text("VINE TOMATOES") == "Fresh Tomatoes"


def test_infer_multiword_precedes_substring():
    # "smoked salmon" must win over the broader "salmon" entry.
    assert infer_ftl_category_from_text("Cold Smoked Salmon") == "Smoked Finfish"


def test_infer_miss_returns_none_not_false():
    assert infer_ftl_category_from_text("Canned Chicken Soup") is None
    assert infer_ftl_category_from_text(None) is None
    assert infer_ftl_category_from_text("") is None
    assert infer_ftl_category_from_text(123) is None


# ---------------------------------------------------------------------------
# prepare_for_persistence enrichment
# ---------------------------------------------------------------------------


def test_prepare_adds_hint_from_product_reference():
    ev = _make_event("Romaine Hearts").prepare_for_persistence()
    assert ev.kdes["ftl_category"] == "Leafy Greens"
    assert ev.kdes["ftl_covered"] is True
    # The rules-engine helpers must now classify the event.
    event_data = {"kdes": ev.kdes}
    assert event_has_ftl_hint(event_data)
    assert is_ftl_food(event_data) is True


def test_prepare_falls_back_to_kdes_product_description():
    ev = _make_event("", kdes={"product_description": "Baby Spinach 1lb"})
    ev.prepare_for_persistence()
    assert ev.kdes["ftl_category"] == "Leafy Greens"


def test_prepare_never_overrides_explicit_false():
    ev = _make_event("Romaine Hearts", kdes={"ftl_covered": False})
    ev.prepare_for_persistence()
    assert ev.kdes["ftl_covered"] is False
    assert "ftl_category" not in ev.kdes
    assert is_ftl_food({"kdes": ev.kdes}) is False


def test_prepare_never_overrides_explicit_category():
    ev = _make_event("Romaine Hearts", kdes={"ftl_category": "Herbs"})
    ev.prepare_for_persistence()
    assert ev.kdes["ftl_category"] == "Herbs"
    assert "ftl_covered" not in ev.kdes


def test_prepare_keyword_miss_adds_nothing():
    ev = _make_event("Canned Chicken Soup").prepare_for_persistence()
    assert "ftl_covered" not in ev.kdes
    assert "ftl_category" not in ev.kdes
    # Missing hint stays "cannot classify" for the rules engine.
    assert is_ftl_food({"kdes": ev.kdes}) is None


def test_hash_covers_enriched_kdes_and_is_stable():
    ev = _make_event("Romaine Hearts").prepare_for_persistence()
    first_hash = ev.sha256_hash
    first_key = ev.idempotency_key
    assert ev.normalized_payload["kdes"]["ftl_category"] == "Leafy Greens"
    # Re-preparing must be idempotent: hint already present, same hash.
    ev.prepare_for_persistence()
    assert ev.sha256_hash == first_hash
    assert ev.idempotency_key == first_key
    # And the hash must differ from the un-enriched form of the event.
    bare = _make_event("Canned Chicken Soup").prepare_for_persistence()
    assert bare.sha256_hash != first_hash


# ---------------------------------------------------------------------------
# Normalizer integration (CSV path — the one prod demo data came through)
# ---------------------------------------------------------------------------


def test_normalize_csv_row_propagates_hint():
    row = {
        "Event Type": "receiving",
        "Product": "Romaine Hearts 24ct",
        "TLC": "LOT-ROM-2026-001",
        "Qty": "10",
    }
    mapping = {
        "Event Type": "event_type",
        "Product": "product_description",
        "TLC": "traceability_lot_code",
        "Qty": "quantity",
    }
    ev = normalize_csv_row(row, str(uuid4()), mapping)
    assert ev.kdes["ftl_category"] == "Leafy Greens"
    assert ev.kdes["ftl_covered"] is True


def test_normalize_csv_row_unmapped_description_still_classifies():
    # product_description arrives as an unmapped column -> lands in kdes;
    # enrichment must pick it up from there.
    row = {
        "Event Type": "shipping",
        "product_description": "Fresh Atlantic Salmon",
        "TLC": "LOT-SAL-2026-001",
        "Qty": "5",
    }
    mapping = {
        "Event Type": "event_type",
        "TLC": "traceability_lot_code",
        "Qty": "quantity",
    }
    ev = normalize_csv_row(row, str(uuid4()), mapping)
    assert ev.kdes["ftl_category"] == "Finfish"
    assert ev.kdes["ftl_covered"] is True
