"""#2955: the regengine-verify CLI contract — envelope recognition and a
non-zero exit when nothing was verified.

Before this coverage existed the tool failed open: ``verify_file`` on
``{"records": []}`` returned ``[]``, ``print_results([])`` printed
``SUMMARY: 0 passed, 0 failed, 0 total`` under the verification-report banner
and returned ``0``, so ``regengine-verify --file F && echo OK`` reported
success for a file in which nothing was checked. Separately the platform's own
canonical export
(``services/ingestion/app/canonical_router.py:158`` →
``{"tenant_id": ..., "events": [...], "total": N}``) was not recognised, so the
whole envelope dict was hashed as a single bogus record via a ``[data]``
fallback.

These tests assert exit codes, not just printed text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from regengine import verify_records
from regengine.verify_records import (
    UnrecognizedExportError,
    compute_record_hash,
    extract_records,
    main,
    print_results,
    verify_file,
)


def _record(tlc: str) -> dict:
    """Build a canonical-shaped record carrying its own correct digest."""
    record = {
        "event_id": f"evt-{tlc}",
        "event_type": "shipping",
        "traceability_lot_code": tlc,
        "product_reference": "urn:gtin:0614141000001",
        "quantity": 10,
        "unit_of_measure": "cases",
        "from_facility_reference": "GLN:111",
        "to_facility_reference": "GLN:222",
        "event_timestamp": "2026-02-06T12:00:00Z",
        "kdes": {"lot_date": "2026-02-05"},
    }
    record["sha256_hash"] = compute_record_hash(record)
    return record


def _write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_cli(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["regengine-verify", *argv])
    with pytest.raises(SystemExit) as excinfo:
        main()
    return excinfo.value.code


class TestEmptyInputFailsClosed:
    def test_print_results_returns_nonzero_for_no_results(self, capsys):
        assert print_results([]) == 1
        out = capsys.readouterr().out
        assert "NO RECORDS VERIFIED" in out

    @pytest.mark.parametrize(
        "payload",
        [[], {"records": []}, {"events": []}],
        ids=["bare-empty-array", "empty-records-envelope", "empty-events-envelope"],
    )
    def test_cli_exits_nonzero_when_nothing_was_verified(self, tmp_path, monkeypatch, capsys, payload):
        path = _write(tmp_path, payload)
        code = _run_cli(monkeypatch, "--file", str(path), "--offline")
        assert code == 1, "a file containing no records must not exit 0"
        assert "NO RECORDS VERIFIED" in capsys.readouterr().out


class TestEnvelopeRecognition:
    def test_events_envelope_verifies_each_record_individually(self, tmp_path):
        """The canonical list-endpoint shape must yield N results, not one."""
        records = [_record("LOT-A"), _record("LOT-B")]
        path = _write(tmp_path, {"tenant_id": "t-1", "events": records, "total": 2})

        results = verify_file(path)

        assert len(results) == 2
        assert [r.tlc for r in results] == ["LOT-A", "LOT-B"]
        assert all(r.valid for r in results)
        # The pre-fix `[data]` fallback produced exactly one result with a
        # tlc of UNKNOWN — the envelope hashed as a record.
        assert "UNKNOWN" not in [r.tlc for r in results]

    def test_events_envelope_exits_zero_when_records_verify(self, tmp_path, monkeypatch, capsys):
        path = _write(tmp_path, {"tenant_id": "t-1", "events": [_record("LOT-A")], "total": 1})
        code = _run_cli(monkeypatch, "--file", str(path), "--offline")
        assert code == 0
        assert "SUMMARY: 1 passed, 0 failed, 1 total" in capsys.readouterr().out

    def test_records_envelope_still_recognised(self, tmp_path):
        path = _write(tmp_path, {"records": [_record("LOT-A")]})
        assert len(verify_file(path)) == 1

    def test_bare_array_still_recognised(self, tmp_path):
        path = _write(tmp_path, [_record("LOT-A"), _record("LOT-B")])
        assert len(verify_file(path)) == 2

    def test_single_record_dict_still_recognised(self, tmp_path):
        """A lone record (the shape ``GET /records/{tlc}`` returns) carries a
        digest, so it is a record — not an envelope."""
        path = _write(tmp_path, _record("LOT-A"))
        results = verify_file(path)
        assert len(results) == 1
        assert results[0].tlc == "LOT-A"

    def test_unrecognized_envelope_is_rejected_not_hashed(self):
        with pytest.raises(UnrecognizedExportError) as excinfo:
            extract_records({"tenant_id": "t-1", "rows": [], "total": 0})
        message = str(excinfo.value)
        # It must say what it looked for, so the operator can fix the export.
        assert "records" in message and "events" in message

    def test_cli_exits_nonzero_on_unrecognized_envelope(self, tmp_path, monkeypatch, capsys):
        path = _write(tmp_path, {"tenant_id": "t-1", "rows": [], "total": 0})
        code = _run_cli(monkeypatch, "--file", str(path), "--offline")
        assert code == 1
        assert "Unrecognized export envelope" in capsys.readouterr().err

    def test_non_list_under_envelope_key_is_rejected(self):
        with pytest.raises(UnrecognizedExportError):
            extract_records({"events": {"not": "a list"}})


class TestFlagContradictions:
    def test_file_and_tlc_together_are_rejected(self, tmp_path, monkeypatch, capsys):
        path = _write(tmp_path, [_record("LOT-A")])
        code = _run_cli(monkeypatch, "--file", str(path), "--tlc", "LOT-A")
        assert code == 1
        assert "mutually exclusive" in capsys.readouterr().err

    def test_invalid_json_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        path = tmp_path / "export.json"
        path.write_text("{not json", encoding="utf-8")
        code = _run_cli(monkeypatch, "--file", str(path), "--offline")
        assert code == 1
        assert "not valid JSON" in capsys.readouterr().err


def test_envelope_keys_cover_the_platform_export_surfaces():
    """Guardrail: the keys the verifier accepts must include the one the
    canonical router emits."""
    assert "events" in verify_records.RECORD_ENVELOPE_KEYS
    assert "records" in verify_records.RECORD_ENVELOPE_KEYS
