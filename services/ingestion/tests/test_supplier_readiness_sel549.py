"""SEL-549: second shipping format (EDI 856 ASN) maps into shipping KDEs.

Preflight only. Synthetic fixtures under tests/fixtures/ only.
Modeled on /workspace/regengine-audit/supplier-readiness-{pass,fail}-case.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.edi_ingestion.extractors import _extract_856_fields
from app.edi_ingestion.parser import _parse_x12_segments
from app.supplier_readiness import (
    ALBERTSONS_BUYER_FIELDS,
    dry_run_shipping_csv,
    map_asn856_to_shipping_kdes,
    score_shipping_readiness,
)
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType

FIXTURES = Path(__file__).parent / "fixtures"
EDI_DIR = FIXTURES / "edi_corpus"
ASN_EDI = EDI_DIR / "asn_856.edi"
ASN_EXPECTED = EDI_DIR / "asn_856.expected.json"
PASS_CSV = FIXTURES / "shipping_pass_partner.csv"
MESSY_CSV = FIXTURES / "shipping_messy_partner.csv"

SHIPPING_KDES = list(REQUIRED_KDES_BY_CTE[WebhookCTEType.SHIPPING])


def test_asn_856_fixture_matches_expected_lot_null():
    """Fixture truth: line_items[0].lot_number is null (fail-case §3)."""
    expected = json.loads(ASN_EXPECTED.read_text(encoding="utf-8"))
    assert expected["line_items"][0]["lot_number"] is None
    assert expected["ship_from_name"] == "Valley Fresh Farms"
    assert expected["reference_document_number"] == "BOL-9001"
    assert "tlc_source_reference" not in expected
    assert "gtin" not in expected
    assert "sscc" not in expected
    assert "po_number" not in expected


def test_asn_856_maps_into_shipping_kde_set_and_reports_gap():
    """Second format (856) → same shipping KDE keys; status=gap per fail case."""
    raw = ASN_EDI.read_text(encoding="utf-8")
    segments = _parse_x12_segments(raw)
    extracted = _extract_856_fields(segments)
    expected = json.loads(ASN_EXPECTED.read_text(encoding="utf-8"))
    assert extracted == expected

    result = map_asn856_to_shipping_kdes(
        extracted, segments, source="edi_corpus/asn_856.edi"
    )

    # Same KDE set as CSV / webhook shipping contract
    for key in SHIPPING_KDES:
        assert key in result.kdes

    assert result.status == "gap"
    assert result.label == "SYNTHETIC"
    assert result.issue == "SEL-549"

    # Fail-case §3 / Lead: lot null → TLC missing; TLC source, GTIN, SSCC, PO missing
    assert result.kdes["traceability_lot_code"] is None
    assert "traceability_lot_code" in result.missing_repo_kdes
    assert "tlc_source_reference" in result.missing_repo_kdes
    assert "gtin" in result.missing_buyer_fields
    assert "sscc" in result.missing_buyer_fields
    assert "po_number" in result.missing_buyer_fields

    # Present fields still mapped (not dropped)
    assert result.kdes["product_description"] == "ROMAINE-12CT"
    assert result.kdes["quantity"] == 200.0
    assert result.kdes["unit_of_measure"] == "cases"  # CA → cases
    assert result.kdes["ship_date"] == "2026-03-10"
    assert result.kdes["ship_from_location"] == "Valley Fresh Farms"
    assert result.kdes["ship_to_location"] == "Metro Distribution Center"
    assert result.kdes["reference_document"] == "BOL-9001"


def test_asn_856_unknown_segment_flagged_not_dropped():
    """Unknown EDI segment ids are flagged; known content still scores."""
    raw = ASN_EDI.read_text(encoding="utf-8")
    # Inject a synthetic unknown segment before SE
    mutated = raw.replace("~SE*", "~ZZZ*KEEP-ME*1~SE*")
    segments = _parse_x12_segments(mutated)
    extracted = _extract_856_fields(segments)
    result = map_asn856_to_shipping_kdes(extracted, segments, source="mutated-asn")

    assert any(f.reason == "unrecognized_segment" and f.field == "ZZZ" for f in result.flags)
    assert result.kdes["product_description"] == "ROMAINE-12CT"
    assert result.status == "gap"


def test_pass_case_shipping_csv_scores_pass():
    """Pass-case synthetic shipping CSV: every repo KDE + Albertsons buyer field."""
    text = PASS_CSV.read_text(encoding="utf-8")
    dry = dry_run_shipping_csv(text, source="shipping_pass_partner.csv")
    assert dry["row_count"] == 1
    assert dry["status_counts"]["pass"] == 1
    result = dry["results"][0]
    assert result.status == "pass"
    assert result.missing_repo_kdes == []
    assert result.missing_buyer_fields == []
    for key in SHIPPING_KDES:
        assert result.kdes.get(key) not in (None, "")
    for key in ALBERTSONS_BUYER_FIELDS:
        assert result.buyer.get(key) not in (None, "")


def test_fail_case_missing_repo_kde_is_gap():
    """Fail-case §2.1: empty TLC → gap (missing_kde), not pass."""
    scored = score_shipping_readiness(
        {
            "traceability_lot_code": None,
            "product_description": "Organic Romaine Hearts",
            "quantity": 200,
            "unit_of_measure": "cases",
            "ship_date": "2026-03-10",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "Metro Distribution Center",
            "reference_document": "BOL-9001",
            "tlc_source_reference": "PACK-1",
        },
        {"gtin": "1", "po_number": "PO-1", "sscc": "SSCC-1", "product_date": "2026-03-17"},
    )
    assert scored.status == "gap"
    assert scored.missing_repo_kdes == ["traceability_lot_code"]


def test_fail_case_malformed_quantity_is_failure():
    """Fail-case §2.3: non-numeric quantity → failure."""
    scored = score_shipping_readiness(
        {
            "traceability_lot_code": "LOT-A",
            "product_description": "Romaine",
            "quantity": "not-a-number",
            "unit_of_measure": "cases",
            "ship_date": "2026-03-10",
            "ship_from_location": "A",
            "ship_to_location": "B",
            "reference_document": "BOL-1",
            "tlc_source_reference": "PACK-1",
        },
        {"gtin": "1", "po_number": "PO-1", "sscc": "SSCC-1", "product_date": "2026-03-17"},
    )
    assert scored.status == "failure"
    assert any(f["kind"] == "malformed_quantity" for f in scored.failures)


def test_unknown_csv_columns_flagged_and_kept():
    """Fail-case §2.8: unknown columns flagged, values kept on kdes."""
    text = PASS_CSV.read_text(encoding="utf-8")
    # Add an unknown column to the pass fixture
    lines = text.strip().splitlines()
    header = lines[0] + ",partner_bin"
    body = lines[1] + ",BIN-99"
    dry = dry_run_shipping_csv(header + "\n" + body + "\n", source="pass-with-unknown")
    result = dry["results"][0]
    assert any(f.reason == "unrecognized_column" and f.field == "partner_bin" for f in result.flags)
    assert result.kdes.get("partner_bin") == "BIN-99"
    assert result.status == "pass"  # extras do not block pass when KDEs complete


def test_messy_csv_dry_run_flag_counts_by_reason():
    """Dry run over synthetic messy shipping CSV; counts by reason for PR body."""
    text = MESSY_CSV.read_text(encoding="utf-8")
    dry = dry_run_shipping_csv(text, source="shipping_messy_partner.csv")

    assert dry["label"] == "SYNTHETIC"
    assert dry["issue"] == "SEL-549"
    assert dry["row_count"] == 7

    counts = dry["flagged_counts_by_reason"]
    # Header-level unknown columns (same spirit as #3682): once each
    assert counts.get("unrecognized_column") == 3  # partner_bin, mystery_code, extra_pallet_tag
    assert counts.get("malformed_quantity") == 1
    assert counts.get("unrecognized_value") == 1  # bad UOM "blargs"
    assert counts.get("malformed_date") == 1  # 2026-03-99
    assert counts.get("unknown_cte_type") == 1

    assert dry["status_counts"]["gap"] >= 1
    assert dry["status_counts"]["failure"] >= 2  # bad qty + wrong CTE (+ invalid UOM)
    statuses = [r.status for r in dry["results"]]
    assert "gap" in statuses
    assert "failure" in statuses
    # Wrong CTE row is a failure (fail-case §2.7), not a silent gap
    wrong = [r for r in dry["results"] if any(f.reason == "unknown_cte_type" for f in r.flags)]
    assert len(wrong) == 1 and wrong[0].status == "failure"
