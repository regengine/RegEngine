"""Synthetic CSV gap-report acceptance guards; no partner data."""

import csv
import io
from types import SimpleNamespace

import pytest
from app import csv_templates as ct
from app.supplier_readiness.shipping import score_shipping_readiness


def _row(**updates):
    return {
        "cte_type": "shipping",
        "traceability_lot_code": "SYNTH-001",
        "product_description": "Synthetic greens",
        "quantity": "12",
        "unit_of_measure": "cases",
        "location_name": "Synthetic warehouse",
        "location_gln": "",
        "ship_date": "2026-06-01",
        "receive_date": "2026-06-02",
        "ship_to_location": "Synthetic receiver",
        "ship_from_location": "Synthetic sender",
        "receiving_location": "Synthetic receiver",
        "immediate_previous_source": "Synthetic sender",
        "reference_document": "SYNTH-DOC-001",
        "tlc_source_reference": "Synthetic farm",
        **updates,
    }


def _csv(*rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(_row()), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if row is None:
            out.write("\n")
        else:
            writer.writerow(row)
    return out.getvalue()


def _parse(text):
    log, numbers, notes = [], [], {}
    events, errors, warnings = ct.parse_csv_rows(text, row_log=log, event_source_rows=numbers, row_notes=notes)
    ct.finalize_row_dispositions_from_ingest(
        log, numbers, [SimpleNamespace(status="accepted", errors=[]) for _ in events], row_notes=notes
    )
    return events, errors, warnings, log


def test_blank_bad_gln_valid_and_receiving_broken_link(monkeypatch):
    monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
    text = _csv(
        None, _row(location_gln="3456789012341"), _row(cte_type="receiving"), _row(traceability_lot_code="SYNTH-002")
    )
    events, errors, warnings, log = _parse(text)
    assert len(events) == 2
    bad = next(e for e in log if e.reason == "invalid_gln")
    assert (bad.row_number, bad.field) == (3, "location_gln")
    assert "GLN check digit invalid: expected 0, got 1" in bad.detail
    assert next(e for e in log if e.reason == "blank_physical_line").row_number == 2
    assert {e.row_number for e in log if e.disposition == "accepted"} == {4, 5}
    assert any("Row 4: broken shipment link: shipping row(s) 3" in w for w in warnings)
    assert not any("could not be parsed" in e for e in errors)
    assert "Synthetic greens" not in str(log) + str(errors)


def test_multiline_cell_keeps_physical_rows():
    text = _csv(
        _row(product_description="Synthetic\n\ngreens"),
        None,
        _row(quantity=""),
        _row(traceability_lot_code="SYNTH-002"),
    )
    events, errors, warnings, log = _parse(text)
    assert len(events) == 2
    assert {e.row_number for e in log if e.reason == "blank_physical_line"} == {5}
    assert any("Row 6:" in e and "required by law (21 CFR 1.1340(a)(2))" in e for e in errors)
    assert {e.row_number for e in log if e.disposition == "accepted"} == {2, 7}


def test_quoted_control_characters_keep_all_rows_and_source_numbers():
    text = _csv(
        _row(product_description="Synthetic x\ry, greens"),
        _row(product_description="Synthetic p\nq, greens"),
        _row(product_description="Synthetic x\x0by, greens"),
        _row(traceability_lot_code="SYNTH-002"),
    )
    events, errors, _, log = _parse(text)
    assert len(events) == 4
    assert not errors
    assert [(e.row_number, e.disposition) for e in log] == [
        (2, "accepted"), (3, "accepted"), (5, "accepted"), (6, "accepted")
    ]


def test_unreadable_file_control_characters_do_not_add_physical_rows():
    text = _csv(_row(product_description="Synthetic x\ry\x0bz, greens"))
    events, errors, _, log = _parse(text + '"synthetic-unclosed-cell')
    assert not events
    assert errors[0].startswith("Line 3:")
    assert [(e.row_number, e.reason) for e in log] == [
        (3, "unreadable_csv"), (2, "unreadable_file")
    ]


def test_missing_kdes_name_law_and_retailer_separately_without_dates():
    _, _, warnings, _ = _parse(_csv(_row(ship_to_location="")))
    assert any("ship to location: required by law (21 CFR 1.1340(a)(4))" in w for w in warnings)
    result = score_shipping_readiness({})
    assert any("purchase order number: asked for by the retailer" in line for line in result.gap_reasons)
    assert any("reference document: required by law" in line for line in result.gap_reasons)
    assert not any(date in " ".join(result.gap_reasons) for date in ("Jan 1", "January 1", "Dec 31", "December 31"))


def test_broken_row_does_not_hide_valid_row():
    text = _csv(_row(), _row(traceability_lot_code="SYNTH-002"))
    lines = text.splitlines()
    lines[1] += ",synthetic-overflow"
    events, errors, _, log = _parse("\n".join(lines) + "\n")
    assert len(events) == 1
    assert any(e.row_number == 2 and e.disposition == "rejected" for e in log)
    assert any(e.row_number == 3 and e.disposition == "accepted" for e in log)
    assert "synthetic-overflow" not in str(errors) + str(log)


def test_unreadable_quoted_row_accounts_for_other_rows_without_contents():
    text = _csv(_row()) + '\n"synthetic-unclosed-cell'
    events, errors, _, log = _parse(text)
    assert not events
    assert "quoted field is not closed" in errors[0]
    assert next(e for e in log if e.reason == "unreadable_csv").row_number == 4
    assert {e.row_number for e in log if e.disposition == "skipped"} == {2, 3}
    assert "synthetic-unclosed-cell" not in str(errors) + str(log)
    assert "Synthetic greens" not in str(errors) + str(log)


def test_ingest_rejected_shipment_preserves_receiving_acceptance(monkeypatch):
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.webhook_models import EventResult, IngestResponse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    async def ingest(payload, **kwargs):
        return IngestResponse(
            accepted=1,
            rejected=1,
            total=2,
            events=[
                EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected" if index == 0 else "accepted",
                    errors=["rule_violation"] if index == 0 else [],
                )
                for index, event in enumerate(payload.events)
            ],
        )

    monkeypatch.setattr(ct, "ingest_events", ingest)
    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="synthetic-key-id", scopes=["*"], tenant_id="synthetic-tenant"
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("synthetic.csv", _csv(_row(), _row(cte_type="receiving")).encode(), "text/csv")},
        )
    assert response.status_code == 200
    body = response.json()
    assert (body["accepted"], body["rejected"]) == (1, 1)
    assert any("Row 3: broken shipment link: shipping row(s) 2" in w for w in body["kde_warnings"])
    assert any(e["row_number"] == 3 and e["disposition"] == "accepted" for e in body["row_disposition_log"])


def test_model_error_has_specific_missing_location_without_row_contents(caplog):
    text = _csv(_row(location_name="", ship_to_location="", ship_from_location="", receiving_location=""))
    events, errors, _, log = _parse(text)
    assert not events
    assert any("Missing location name: required by law (21 CFR 1.1340(a))" in error for error in errors)
    entry = next(e for e in log if e.reason == "missing_location")
    assert (entry.row_number, entry.field) == (2, "location_name")
    assert "Synthetic greens" not in str(errors) + str(log) + caplog.text


def test_parse_only_callers_also_get_broken_link_warning():
    events, errors, warnings = ct.parse_csv_rows(_csv(_row(quantity=""), _row(cte_type="receiving")))
    assert len(events) == 1 and len(errors) == 1
    assert any("Row 3: broken shipment link: shipping row(s) 2" in warning for warning in warnings)


def test_receiving_missing_source_cites_receiving_rule():
    events, errors, warnings, _ = _parse(_csv(_row(cte_type="receiving", tlc_source_reference="")))
    assert len(events) == 1 and not errors
    assert any(
        "traceability lot code source reference: required by law (21 CFR 1.1345(a))" in w
        for w in warnings
    )


def test_unreadable_multiline_record_reports_starting_physical_row():
    events, errors, _, log = _parse(_csv(_row()) + '"synthetic-unclosed\ncontinued')
    assert not events
    assert errors[0].startswith("Line 3:")
    assert next(e for e in log if e.reason == "unreadable_csv").row_number == 3


def test_stray_quote_rejects_only_its_physical_row():
    text = _csv(_row(product_description="Synthetic valid"), None, _row(), _row(traceability_lot_code="SYNTH-002"))
    text = text.replace("Synthetic greens", '"Synthetic" greens', 1)
    events, errors, _, log = _parse(text)
    assert [event.traceability_lot_code for event in events] == ["SYNTH-001", "SYNTH-002"]
    assert len(errors) == 1 and errors[0].startswith("Row 4:")
    assert {e.row_number for e in log if e.disposition == "rejected"} == {4}
    assert {e.row_number for e in log if e.disposition == "accepted"} == {2, 5}
    assert "Synthetic" not in str(errors) + str(log)


def test_csv_gln_validation_can_be_disabled(monkeypatch):
    monkeypatch.setenv("STRICT_GLN_VALIDATION", "false")
    events, errors, _, log = _parse(_csv(_row(location_gln="3456789012341")))
    assert len(events) == 1 and not errors
    assert not any(e.reason == "invalid_gln" for e in log)


@pytest.mark.parametrize("fields", [("cte_type",), ("traceability_lot_code",), ("cte_type", "traceability_lot_code")])
def test_broken_link_uses_mapped_lot_and_cte_columns(fields):
    text = _csv(_row(quantity=""), _row(cte_type="receiving"))
    mapping = {f"partner_{field}": field for field in fields}
    for source, canonical in mapping.items():
        text = text.replace(canonical, source, 1)
    events, errors, warnings = ct.parse_csv_rows(text, header_mapping=mapping)
    assert len(events) == 1 and len(errors) == 1
    assert any("Row 3: broken shipment link: shipping row(s) 2" in w for w in warnings)
