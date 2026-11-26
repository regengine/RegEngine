"""Outbound GLNs use structural inputs only."""

from types import SimpleNamespace

import pytest
from app import exchange_api
from shared.fsma_validation import calculate_gs1_check_digit


def shapes():
    base = "0" * 12
    return [None, "", " ", "x", "0", "x" * 13, base + str(calculate_gs1_check_digit(base))]


@pytest.mark.parametrize("raw", shapes())
def test_exchange_filters_all_glns(raw):
    from shared.fsma_validation import gln_for_export

    row = SimpleNamespace(
        **dict.fromkeys(
            (
                "id",
                "event_timestamp",
                "product_description",
                "quantity",
                "unit_of_measure",
                "source_event_id",
                "sha256_hash",
                "chain_hash",
                "source",
                "location_name",
                "traceability_lot_code",
            )
        )
    )
    row.location_gln = raw
    row.kdes = dict.fromkeys(("ship_from_gln", "ship_to_gln", "tlc_source_gln"), raw)
    record = exchange_api._build_records([row])[0]
    for key in ("ship_from", "ship_to", "tlc_source"):
        assert record[key]["gln"] == gln_for_export(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", shapes())
@pytest.mark.parametrize("fallback", [False, True])
async def test_retailer_filters_both_glns(monkeypatch, raw, fallback):
    from shared.external_connectors import retailers
    from shared.fsma_validation import gln_for_export

    emitted = []

    def filtered(value):
        result = gln_for_export(value)
        emitted.append(result)
        return result

    monkeypatch.setattr(retailers, "gln_for_export", filtered)
    event = SimpleNamespace(
        cte_type="shipping",
        quantity=float(True),
        unit_of_measure="x",
        source_event_id="x",
        timestamp="",
        kdes={"ship_from_gln": raw, "ship_to_gln": raw},
        location_gln=None if fallback else raw,
        traceability_lot_code="x",
        product_description="x",
    )
    connector = object.__new__(retailers.WalmartGDSNConnector)
    assert await connector.push_event(event)
    assert emitted == [gln_for_export(raw), gln_for_export(raw)]


@pytest.mark.parametrize("raw", shapes())
def test_exchange_additional_gln_filtered(raw):
    row = SimpleNamespace(
        **dict.fromkeys(
            (
                "id",
                "event_timestamp",
                "product_description",
                "quantity",
                "unit_of_measure",
                "source_event_id",
                "sha256_hash",
                "chain_hash",
                "source",
                "location_name",
                "traceability_lot_code",
                "location_gln",
            )
        )
    )
    row.kdes = {"receiving_location_gln": raw}
    from shared.fsma_validation import gln_for_export

    assert exchange_api._build_records([row])[0]["additional_kdes"]["receiving_location_gln"] == gln_for_export(raw)


@pytest.mark.parametrize("raw", shapes())
def test_plan_exports_filter_gln(raw):
    from shared.fsma_plan_builder import FirmInfo, FirmType, TraceabilityPlan, export_plan_markdown
    from shared.fsma_validation import gln_for_export

    firm = FirmInfo("", "", next(iter(FirmType)), gln=raw)
    plan = TraceabilityPlan("x", firm, "", "", "")
    assert firm.to_dict()["gln"] == gln_for_export(raw)
    assert f"- **GLN:** {gln_for_export(raw) or 'N/A'}\n" in export_plan_markdown(plan)
