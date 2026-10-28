"""SEL-549: an unseen partner CSV fails clearly and never loses a row silently.

Uses only synthetic data from the repo fixture
``tests/fixtures/01_harvesting.csv`` (C.Lee's scoped exception to
real-data-only). No lot codes, product names, or IDs are invented in tests.
"""

from __future__ import annotations

import csv as _csv
import io as _io
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import csv_templates as ct

FIXTURE = Path(__file__).parent / "fixtures" / "01_harvesting.csv"


def _fixture_rows() -> tuple[list[str], list[dict]]:
    reader = _csv.DictReader(_io.StringIO(FIXTURE.read_text()))
    return list(reader.fieldnames or []), [dict(row) for row in reader]


def _to_csv(header: list[str], rows: list[dict]) -> str:
    out = _io.StringIO()
    writer = _csv.DictWriter(out, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def _parse(text: str, cte: str | None = "harvesting", mapping=None):
    """Parse and finalize successful rows as accepted (parse-only path).

    Production ingest_csv calls finalize_row_dispositions_from_ingest after
    ingest_events instead; tests that only exercise the parser still need
    every row to land in exactly one exclusive bucket.
    """
    log: list = []
    source_rows: list[int] = []
    row_notes: dict = {}
    events, errors, warnings = ct.parse_csv_rows(
        text,
        cte,
        header_mapping=mapping,
        row_log=log,
        event_source_rows=source_rows,
        row_notes=row_notes,
    )
    fake_results = [SimpleNamespace(status="accepted", errors=[]) for _ in source_rows]
    ct.finalize_row_dispositions_from_ingest(log, source_rows, fake_results, row_notes=row_notes)
    return events, errors, warnings, log


def _data_rows(log):
    return {e.row_number for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}}


def _assert_counts_balance(text: str, events, log) -> None:
    """Every physical input row lands in exactly one exclusive bucket."""
    rows_in = len([line for line in text.splitlines()[1:] if line is not None])
    # Include blank lines that csv still presents as records: count non-header lines.
    rows_in = len(text.splitlines()) - 1
    outcomes = [
        e.disposition for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}
    ]
    row_numbers = sorted(
        e.row_number for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}
    )
    assert row_numbers == list(range(2, 2 + rows_in)), (
        f"expected exclusive outcomes for rows 2..{1 + rows_in}, got {row_numbers}"
    )
    assert len(outcomes) == rows_in, "every input row needs exactly one exclusive outcome"
    assert outcomes.count("accepted") == len(events)
    assert outcomes.count("accepted") + outcomes.count("rejected") + outcomes.count("skipped") == rows_in


def test_fixture_rows_are_all_accepted_and_logged():
    text = FIXTURE.read_text()
    events, errors, _warnings, log = _parse(text)
    data_lines = len([line for line in text.splitlines()[1:] if line.strip()])
    assert errors == []
    assert len(events) == data_lines
    accepted = [e for e in log if e.disposition == "accepted"]
    assert [e.row_number for e in accepted] == list(range(2, 2 + data_lines))
    _assert_counts_balance(text, events, log)


def test_missing_required_columns_named_in_one_clear_error():
    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    text = _to_csv(kept, rows[:1])
    events, errors, _warnings, log = _parse(text)
    assert events == []
    assert len(errors) == 1
    assert "Missing required columns" in errors[0]
    assert "quantity (accepted column names: quantity, qty)" in errors[0]
    assert "unit_of_measure" in errors[0]
    missing = {e.field for e in log if e.reason == "missing_column"}
    assert missing == {"quantity", "unit_of_measure"}
    _assert_counts_balance(text, events, log)


def test_missing_cte_type_rejects_each_row_and_logs_it():
    header, rows = _fixture_rows()
    text = _to_csv(header, rows[:1])
    _e, errors, _w, log = _parse(text, cte=None)
    assert errors and "No CTE type" in errors[0]
    assert [e.reason for e in log if e.disposition == "rejected"] == ["missing_cte_type"]
    events, errors, _w, log = _parse(text, cte="harvesting")
    assert errors == [] and len(events) == 1
    assert any(e.reason == "cte_type_from_upload" for e in log)
    _assert_counts_balance(text, events, log)


def test_every_row_accounted_for_none_silent():
    header, rows = _fixture_rows()
    base = dict(rows[0])
    bad_qty = dict(base)
    bad_qty["quantity"] = "abc"
    missing_unit = dict(base)
    missing_unit["unit_of_measure"] = ""
    bad_date = dict(base)
    bad_date["harvest_date"] = "not-a-date"
    good = dict(base)
    # Build CSV manually so comment / blank / extra-field rows are present.
    out = _io.StringIO()
    writer = _csv.DictWriter(out, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerow(good)  # 2 accepted
    text = out.getvalue().rstrip("\n")
    text += "\n# synthetic comment row\n"  # 3 skipped comment
    text += "," * (len(header) - 1) + "\n"  # 4 blank
    # bad quantity / missing unit / bad date from fixture cells only
    for mutated in (bad_qty, missing_unit, bad_date):
        buf = _io.StringIO()
        w = _csv.DictWriter(buf, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        w.writerow(mutated)
        text += buf.getvalue()
    # extra field beyond header
    extra_line = ",".join(good.get(h, "") for h in header) + ",EXTRA\n"
    text += extra_line  # 8 extra fields

    events, errors, _w, log = _parse(text)
    assert len(events) == 1
    assert _data_rows(log) == set(range(2, 9))
    by_row = {e.row_number: e for e in log if e.disposition in {"accepted", "rejected", "skipped"}}
    assert by_row[2].disposition == "accepted"
    assert by_row[3].reason == "comment_row"
    assert by_row[4].reason == "blank_row"
    assert by_row[5].reason == "bad_quantity"
    assert by_row[6].reason == "missing_unit_of_measure"
    assert by_row[7].reason == "bad_date"
    assert by_row[8].reason == "extra_fields"
    rejected = [e for e in log if e.disposition == "rejected"]
    assert len(rejected) == len(errors) == 4
    _assert_counts_balance(text, events, log)


def test_unrecognized_columns_flagged_and_kept():
    header, rows = _fixture_rows()
    # Unknown column keeps a real fixture cell value (field_id), never dropped.
    fixture_value = rows[0]["field_id"]
    for row in rows:
        row["partner_bin"] = row["field_id"]
    text = _to_csv([*header, "partner_bin"], rows[:1])
    events, errors, _w, log = _parse(text)
    assert errors == [] and len(events) == 1
    assert events[0].kdes.get("partner_bin") == fixture_value
    flagged = [e for e in log if e.reason == "unrecognized_column"]
    assert [e.field for e in flagged] == ["partner_bin"]
    _assert_counts_balance(text, events, log)


def test_header_mapping_guess_logged_without_cell_value():
    header, rows = _fixture_rows()
    # Rename quantity -> amount; mapping restores it. Values stay from fixture.
    renamed = ["amount" if h == "quantity" else h for h in header]
    mapped_rows = [{("amount" if k == "quantity" else k): v for k, v in row.items()} for row in rows[:1]]
    text = _to_csv(renamed, mapped_rows)
    events, errors, _w, log = _parse(text, mapping={"amount": "quantity"})
    assert errors == [] and len(events) == 1
    guesses = [e for e in log if e.reason == "header_guess_applied"]
    assert len(guesses) == 1
    assert guesses[0].field == "amount" and guesses[0].guessed_as == "quantity"
    qty = rows[0]["quantity"]
    assert qty not in (guesses[0].detail or "")
    _assert_counts_balance(text, events, log)


def test_log_detail_never_echoes_guessed_cell_values():
    header, rows = _fixture_rows()
    text = _to_csv(header, rows[:1])
    _e, _err, _w, log = _parse(text)
    lot = rows[0]["traceability_lot_code"]
    for entry in log:
        if entry.disposition == "flagged":
            assert lot not in (entry.detail or "")


def test_header_only_file_is_not_a_missing_column_error():
    _e, errors, _w, _log = _parse("partner_col_a,partner_col_b\n")
    assert errors == []


def test_row_limit_first_overflow_not_double_counted(monkeypatch):
    """First row past the limit is rejected once; further rows are skipped only."""
    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    # Three fixture rows: 2 accepted-capacity, 1 rejected, and invent no values —
    # duplicate the third fixture row to create a 4th physical row for skipped.
    four = [dict(rows[0]), dict(rows[1]), dict(rows[2]), dict(rows[2])]
    text = _to_csv(header, four)
    events, errors, _w, log = _parse(text)
    assert len(events) == 2
    by_row = {
        e.row_number: e for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}
    }
    assert by_row[2].disposition == "accepted"
    assert by_row[3].disposition == "accepted"
    assert by_row[4].disposition == "rejected"
    assert by_row[4].reason == "row_limit_exceeded"
    assert by_row[5].disposition == "skipped"
    assert by_row[5].reason == "row_limit_overflow"
    # Same row must not be both skipped and rejected.
    exclusive = [e for e in log if e.row_number == 4 and e.disposition in {"accepted", "rejected", "skipped"}]
    assert len(exclusive) == 1
    assert any("1 more row(s)" in err for err in errors)
    assert errors[-1].endswith("CSV exceeds maximum row limit of 2")
    _assert_counts_balance(text, events, log)


def test_finalize_uses_ingest_result_not_parse_claim():
    """A parsed row rejected by ingest (duplicate) is logged rejected, not accepted."""
    header, rows = _fixture_rows()
    text = _to_csv(header, rows[:1])
    log: list = []
    source_rows: list[int] = []
    events, errors, _w = ct.parse_csv_rows(text, "harvesting", row_log=log, event_source_rows=source_rows)
    assert errors == [] and len(events) == 1 and source_rows == [2]
    # No exclusive outcome yet — parse must not claim ingested.
    assert not any(e.disposition == "accepted" for e in log)
    assert not any(e.reason == "ingested" for e in log)
    ct.finalize_row_dispositions_from_ingest(
        log,
        source_rows,
        [SimpleNamespace(status="rejected", errors=["Duplicate event in batch"])],
    )
    exclusive = [e for e in log if e.row_number == 2 and e.disposition != "flagged"]
    assert len(exclusive) == 1
    assert exclusive[0].disposition == "rejected"
    assert exclusive[0].reason == "duplicate"


# ---------------------------------------------------------------------------
# Red Team acceptance bar: every unrecognised field, event type or format is
# flagged in the disposition log AND the error/warning output, and
# rows in == accepted + rejected + skipped (nothing silently dropped).
# Inputs are derived from the synthetic fixture 01_harvesting.csv.
# ---------------------------------------------------------------------------


@pytest.fixture
def unknown_column_csv() -> str:
    header, rows = _fixture_rows()
    for row in rows:
        # Reuse an existing fixture cell; do not invent pallet IDs.
        row["partner_pallet_code"] = row["field_id"]
    return _to_csv([*header, "partner_pallet_code"], rows)


@pytest.fixture
def unknown_cte_csv() -> str:
    header, rows = _fixture_rows()
    for row in rows:
        row["cte_type"] = "harvesting"
    rows[1]["cte_type"] = "teleporting"
    return _to_csv([*header, "cte_type"], rows)


@pytest.fixture
def malformed_date_csv() -> str:
    header, rows = _fixture_rows()
    rows[0]["harvest_date"] = "32/13/2026"
    return _to_csv(header, rows)


@pytest.fixture
def malformed_quantity_csv() -> str:
    header, rows = _fixture_rows()
    rows[0]["quantity"] = "5,000 lbs"
    return _to_csv(header, rows)


@pytest.fixture
def missing_columns_csv() -> str:
    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    return _to_csv(kept, rows)


@pytest.fixture
def garbled_and_empty_rows_csv() -> str:
    text = FIXTURE.read_text().rstrip("\n").split("\n")
    header, good = text[0], text[1:]
    garbled = "\x00\x07%%LOT??,,,,,,,,,,,,ZZZ"
    empty = "," * (header.count(","))
    return "\n".join([header, good[0], garbled, empty, *good[1:]]) + "\n"


def test_acceptance_unknown_column_is_flagged(unknown_column_csv):
    events, errors, warnings, log = _parse(unknown_column_csv)
    assert any(e.reason == "unrecognized_column" and e.field == "partner_pallet_code" for e in log)
    assert any("partner_pallet_code" in w for w in warnings)
    assert errors == []
    # Unknown column values are kept on the event, never silently dropped.
    header, rows = _fixture_rows()
    assert events[0].kdes.get("partner_pallet_code") == rows[0]["field_id"]
    _assert_counts_balance(unknown_column_csv, events, log)


def test_acceptance_unknown_cte_type_is_rejected_not_defaulted(unknown_cte_csv):
    events, errors, _w, log = _parse(unknown_cte_csv, cte="harvesting")
    assert [e.row_number for e in log if e.reason == "unknown_cte_type"] == [3]
    assert any("Row 3" in e and "teleporting" in e for e in errors)
    _assert_counts_balance(unknown_cte_csv, events, log)


def test_acceptance_malformed_date_is_flagged(malformed_date_csv):
    events, errors, _w, log = _parse(malformed_date_csv)
    assert [e.row_number for e in log if e.reason == "bad_date"] == [2]
    assert any(e.startswith("Row 2:") for e in errors)
    _assert_counts_balance(malformed_date_csv, events, log)


def test_acceptance_malformed_quantity_format_is_flagged(malformed_quantity_csv):
    events, errors, _w, log = _parse(malformed_quantity_csv)
    assert [e.row_number for e in log if e.reason == "bad_quantity"] == [2]
    assert any(e.startswith("Row 2:") and "not a number" in e for e in errors)
    _assert_counts_balance(malformed_quantity_csv, events, log)


def test_acceptance_missing_required_columns_flagged(missing_columns_csv):
    events, errors, _w, log = _parse(missing_columns_csv)
    assert events == []
    assert {e.field for e in log if e.reason == "missing_column"} == {"quantity", "unit_of_measure"}
    assert len(errors) == 1 and "quantity" in errors[0] and "unit_of_measure" in errors[0]
    # Per-row outcomes, not file-level only.
    data_rejects = [e for e in log if e.row_number >= 2 and e.reason == "missing_required_columns"]
    assert len(data_rejects) == len(missing_columns_csv.splitlines()) - 1
    _assert_counts_balance(missing_columns_csv, events, log)


def test_acceptance_garbled_and_empty_rows_flagged(garbled_and_empty_rows_csv):
    events, errors, _w, log = _parse(garbled_and_empty_rows_csv)
    outcome = {e.row_number: e for e in log if e.row_number >= 2 and e.disposition != "flagged"}
    assert outcome[3].disposition == "rejected"  # garbled
    assert any(e.startswith("Row 3:") for e in errors)
    assert outcome[4].reason == "blank_row"  # empty
    _assert_counts_balance(garbled_and_empty_rows_csv, events, log)


# ---------------------------------------------------------------------------
# Codex FAIL bf0265123 follow-ups: one final disposition; missing-column
# overflow; 400 surfaces row_disposition_log; overflow aggregates do not
# inflate rejected EventResults.
# ---------------------------------------------------------------------------


def test_missing_kdes_flag_is_not_a_second_disposition_when_ingest_rejects():
    """Parse must not leave a flagged 'Accepted with missing KDEs' beside a later reject."""
    header, rows = _fixture_rows()
    # Drop reference_document so harvesting KDE completeness warns.
    kept = [h for h in header if h != "reference_document"]
    row = {k: v for k, v in rows[0].items() if k != "reference_document"}
    text = _to_csv(kept, [row])
    log: list = []
    source_rows: list[int] = []
    row_notes: dict = {}
    events, errors, warnings = ct.parse_csv_rows(
        text,
        "harvesting",
        row_log=log,
        event_source_rows=source_rows,
        row_notes=row_notes,
    )
    assert errors == [] and len(events) == 1 and source_rows == [2]
    assert any("Missing KDEs" in w for w in warnings)
    # No exclusive or flagged disposition claiming acceptance before ingest.
    assert not any(e.disposition == "accepted" for e in log)
    assert not any(e.reason == "missing_kdes" for e in log)
    assert not any("Accepted with missing KDEs" in (e.detail or "") for e in log)
    ct.finalize_row_dispositions_from_ingest(
        log,
        source_rows,
        [SimpleNamespace(status="rejected", errors=["Duplicate event in batch"])],
        row_notes=row_notes,
    )
    exclusive = [e for e in log if e.row_number == 2 and e.disposition in {"accepted", "rejected", "skipped"}]
    assert len(exclusive) == 1
    assert exclusive[0].disposition == "rejected"
    assert exclusive[0].reason == "duplicate"
    assert "Accepted with missing KDEs" not in (exclusive[0].detail or "")
    # Missing KDEs may appear as a note on the final entry only.
    assert "missing KDEs" in (exclusive[0].detail or "").lower() or exclusive[0].reason == "duplicate"


def test_missing_kdes_note_on_final_accepted_entry_only():
    header, rows = _fixture_rows()
    kept = [h for h in header if h != "reference_document"]
    row = {k: v for k, v in rows[0].items() if k != "reference_document"}
    text = _to_csv(kept, [row])
    log: list = []
    source_rows: list[int] = []
    row_notes: dict = {}
    events, errors, warnings = ct.parse_csv_rows(
        text,
        "harvesting",
        row_log=log,
        event_source_rows=source_rows,
        row_notes=row_notes,
    )
    assert len(events) == 1
    ct.finalize_row_dispositions_from_ingest(
        log,
        source_rows,
        [SimpleNamespace(status="accepted", errors=[])],
        row_notes=row_notes,
    )
    row_entries = [e for e in log if e.row_number == 2]
    exclusive = [e for e in row_entries if e.disposition in {"accepted", "rejected", "skipped"}]
    flagged = [e for e in row_entries if e.disposition == "flagged" and e.reason == "missing_kdes"]
    assert len(exclusive) == 1 and exclusive[0].disposition == "accepted"
    assert flagged == []
    assert "missing KDEs" in (exclusive[0].detail or "")
    assert "Accepted with missing KDEs" not in (exclusive[0].detail or "")


def test_missing_columns_with_overflow_accounts_for_every_physical_row(monkeypatch):
    """Missing-column early return must still bucket unread overflow rows."""
    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    # 5 physical data rows from fixture only (repeat real rows).
    five = [dict(rows[i % len(rows)]) for i in range(5)]
    for row in five:
        row.pop("quantity", None)
        row.pop("unit_of_measure", None)
    text = _to_csv(kept, five)
    events, errors, _w, log = _parse(text)
    assert events == []
    assert errors and "Missing required columns" in errors[0]
    physical = len(text.splitlines()) - 1
    exclusive = [e for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}]
    assert len(exclusive) == physical
    _assert_counts_balance(text, events, log)


def test_missing_columns_400_includes_row_disposition_log(monkeypatch):
    """The no-valid-rows 400 must surface the per-row disposition log."""
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.webhook_compat import _verify_api_key
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    body_rows = [{k: v for k, v in rows[0].items() if k in kept}]
    text = _to_csv(kept, body_rows)

    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id="t1"
    )
    client = TestClient(app)
    resp = client.post(
        "/api/v1/ingest/csv",
        files={"file": ("partner.csv", text.encode(), "text/csv")},
        data={"cte_type": "harvesting"},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert "missing_columns" in detail
    assert "row_disposition_log" in detail
    log = detail["row_disposition_log"]
    exclusive = [
        e for e in log if e.get("row_number", 0) >= 2 and e.get("disposition") in {"accepted", "rejected", "skipped"}
    ]
    assert len(exclusive) == 1
    assert exclusive[0]["disposition"] == "rejected"


def test_overflow_aggregate_parse_errors_do_not_inflate_rejected_totals(monkeypatch):
    """Aggregate overflow parse_errors must not become extra rejected EventResults."""
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.webhook_compat import _verify_api_key
    from app.webhook_models import EventResult, IngestResponse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    four = [dict(rows[i % len(rows)]) for i in range(4)]
    text = _to_csv(header, four)

    async def _fake_ingest(payload, **kwargs):
        results = [
            EventResult(
                traceability_lot_code=ev.traceability_lot_code,
                cte_type=ev.cte_type.value if hasattr(ev.cte_type, "value") else ev.cte_type,
                status="accepted",
                event_id=f"evt-{i}",
            )
            for i, ev in enumerate(payload.events)
        ]
        return IngestResponse(accepted=len(results), rejected=0, total=len(results), events=results)

    monkeypatch.setattr(ct, "ingest_events", _fake_ingest)

    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id="t1"
    )
    client = TestClient(app)
    resp = client.post(
        "/api/v1/ingest/csv",
        files={"file": ("big.csv", text.encode(), "text/csv")},
        data={"cte_type": "harvesting"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    log = body["row_disposition_log"]
    exclusive = [e for e in log if e["row_number"] >= 2 and e["disposition"] in {"accepted", "rejected", "skipped"}]
    physical = 4
    assert len(exclusive) == physical
    bucket_rejected = sum(1 for e in exclusive if e["disposition"] == "rejected")
    bucket_skipped = sum(1 for e in exclusive if e["disposition"] == "skipped")
    bucket_accepted = sum(1 for e in exclusive if e["disposition"] == "accepted")
    assert bucket_accepted + bucket_rejected + bucket_skipped == physical
    assert body["accepted"] == bucket_accepted
    # The "N more row(s)" aggregate must never appear as its own rejected EventResult.
    assert not any(any("more row(s)" in err for err in e.get("errors", [])) for e in body.get("events", []))
    # First over-limit row may still surface as one rejected EventResult; totals
    # must match exclusive rejected, not rejected + aggregate count.
    assert body["rejected"] == bucket_rejected
    assert body["total"] == body["accepted"] + body["rejected"]


# ---------------------------------------------------------------------------
# Codex FAIL 2cfcc314 follow-ups: structural overflow marker (not substring);
# preserve partial skipped_overflow on csv.Error while counting the tail.
# ---------------------------------------------------------------------------


def test_adversarial_quantity_with_overflow_wording_still_counts_rejected(monkeypatch):
    """Adversarial input: a fixture quantity cell embeds overflow summary wording.

    The EventResult filter must not use substring matching on "more row(s)" /
    "were skipped", or a crafted cell can hide a real bad_quantity rejection
    from response.rejected / events. Built from a real 01_harvesting.csv row.
    """
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.webhook_compat import _verify_api_key
    from app.webhook_models import IngestResponse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    header, rows = _fixture_rows()
    # ADVERSARIAL INPUT (derived from fixture row 0): quantity cell text that
    # contains both substrings the old filter looked for. Pair with a second
    # real fixture row so the request stays on the 200 path where parse_errors
    # are synthesized into EventResults (the substring filter's blast radius).
    adversarial_qty = "7 more row(s) after this one were skipped and not ingested"
    crafted = dict(rows[0])
    crafted["quantity"] = adversarial_qty
    good = dict(rows[1 % len(rows)])
    csv_text = _to_csv(header, [crafted, good])

    async def _fake_ingest(payload, **kwargs):
        from app.webhook_models import EventResult

        results = [
            EventResult(
                traceability_lot_code=ev.traceability_lot_code,
                cte_type=ev.cte_type.value if hasattr(ev.cte_type, "value") else ev.cte_type,
                status="accepted",
                event_id=f"evt-{i}",
            )
            for i, ev in enumerate(payload.events)
        ]
        return IngestResponse(accepted=len(results), rejected=0, total=len(results), events=results)

    monkeypatch.setattr(ct, "ingest_events", _fake_ingest)

    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id="t1"
    )
    client = TestClient(app)
    resp = client.post(
        "/api/v1/ingest/csv",
        files={"file": ("adversarial.csv", csv_text.encode(), "text/csv")},
        data={"cte_type": "harvesting"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1
    assert body["rejected"] >= 1, (
        f"adversarial bad_quantity must still count as rejected EventResult; events={body.get('events')}"
    )
    assert any(any("is not a number" in err for err in e.get("errors", [])) for e in body.get("events", []))
    log_rejected = sum(
        1
        for e in body.get("row_disposition_log", [])
        if e.get("row_number", 0) >= 2 and e.get("disposition") == "rejected"
    )
    assert body["rejected"] == log_rejected


def test_overflow_aggregate_skipped_by_structural_marker_not_substring(monkeypatch):
    """Only messages recorded as overflow aggregates skip EventResult synthesis."""
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.webhook_compat import _verify_api_key
    from app.webhook_models import EventResult, IngestResponse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    four = [dict(rows[i % len(rows)]) for i in range(4)]
    csv_text = _to_csv(header, four)

    async def _fake_ingest(payload, **kwargs):
        results = [
            EventResult(
                traceability_lot_code=ev.traceability_lot_code,
                cte_type=ev.cte_type.value if hasattr(ev.cte_type, "value") else ev.cte_type,
                status="accepted",
                event_id=f"evt-{i}",
            )
            for i, ev in enumerate(payload.events)
        ]
        return IngestResponse(accepted=len(results), rejected=0, total=len(results), events=results)

    monkeypatch.setattr(ct, "ingest_events", _fake_ingest)

    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id="t1"
    )
    client = TestClient(app)
    resp = client.post(
        "/api/v1/ingest/csv",
        files={"file": ("big.csv", csv_text.encode(), "text/csv")},
        data={"cte_type": "harvesting"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert not any(any("more row(s)" in err for err in e.get("errors", [])) for e in body.get("events", []))
    exclusive = [
        e
        for e in body["row_disposition_log"]
        if e["row_number"] >= 2 and e["disposition"] in {"accepted", "rejected", "skipped"}
    ]
    assert body["accepted"] + body["rejected"] == sum(
        1 for e in exclusive if e["disposition"] in {"accepted", "rejected"}
    )


def test_csv_error_while_counting_overflow_keeps_partial_count(monkeypatch):
    """A csv.Error mid-tail must not zero skipped_overflow; keep what was counted."""
    import csv as csvmod

    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    # Buffer MAX+1 fixture rows, then one more readable overflow row (real
    # fixture line), then a field that exceeds a lowered field_size_limit so
    # counting the unread tail raises csv.Error after a partial count.
    three = [dict(rows[i % len(rows)]) for i in range(3)]
    base = _to_csv(header, three)
    extra = base.splitlines()[1]  # real fixture data line — invent nothing
    # Oversized field: reuse the fixture lot code as a prefix so we invent no
    # product/lot identity; pad with digits only.
    lot = rows[0]["traceability_lot_code"]
    huge = lot + ("0" * 200)
    n_cols = len(header)
    oversized_line = ",".join([huge] + [""] * (n_cols - 1))
    csv_text = base.rstrip("\n") + "\n" + extra + "\n" + oversized_line + "\n"

    old_limit = csvmod.field_size_limit()
    csvmod.field_size_limit(64)
    try:
        events, errors, _w, log = _parse(csv_text)
    finally:
        csvmod.field_size_limit(old_limit)

    # With MAX=2: rows 2–3 capacity, row 4 first over-limit rejected, row 5 the
    # one readable overflow counted before csv.Error. The unreadable remainder
    # must be reported explicitly rather than wiping the partial count to zero.
    exclusive = {
        e.row_number: e for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}
    }
    assert 5 in exclusive, f"partial overflow row 5 missing; got {sorted(exclusive)}"
    assert exclusive[5].disposition in {"skipped", "rejected"}
    assert exclusive[4].disposition == "rejected"
    assert exclusive[4].reason == "row_limit_exceeded"
    assert any(e.reason == "unreadable_overflow_tail" for e in log)


def test_missing_column_overflow_rows_are_rejected_not_skipped(monkeypatch):
    """Confirm missing-column unread overflow uses rejected/missing_required_columns."""
    monkeypatch.setattr(ct, "MAX_CSV_ROWS", 2)
    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    five = [dict(rows[i % len(rows)]) for i in range(5)]
    for row in five:
        row.pop("quantity", None)
        row.pop("unit_of_measure", None)
    csv_text = _to_csv(kept, five)
    _events, _errors, _w, log = _parse(csv_text)
    overflow = [e for e in log if e.row_number >= 5 and e.disposition in {"accepted", "rejected", "skipped"}]
    assert overflow
    assert all(e.disposition == "rejected" for e in overflow)
    assert all(e.reason == "missing_required_columns" for e in overflow)
