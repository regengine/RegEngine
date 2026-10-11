"""Deep QA for regengine.verify_records: the online verification path
(mocked transport, no network), CLI error exits, envelope edge cases, and
alias-key hash equality.

The online path had zero coverage: it performs two HTTP round trips and a
local-vs-server hash cross-check, which is exactly the code that must not
fail open.
"""

from __future__ import annotations

import json
import warnings

import pytest

import regengine.verify_records as vc
from regengine.verify_records import (
    UnrecognizedExportError,
    compute_record_hash,
    extract_records,
    main,
    print_results,
    verify_record_offline,
    verify_record_online,
)


def _record(tlc="LOT-A"):
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


def _run_cli(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["regengine-verify", *argv])
    with pytest.raises(SystemExit) as excinfo:
        main()
    return excinfo.value.code


class _Resp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload, ok=True, status=200):
        self._payload = payload
        self.ok = ok
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _patch_get(monkeypatch, mapping):
    """Route requests.get to a fake keyed by URL suffix."""

    def fake_get(url, headers=None, timeout=None):
        for suffix, resp in mapping.items():
            if url.endswith(suffix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(vc.requests, "get", fake_get)
    return fake_get


class TestVerifyRecordOnline:
    def test_missing_requests_library_fails_closed(self, monkeypatch):
        monkeypatch.setattr(vc, "HAS_REQUESTS", False)
        result = verify_record_online("LOT-A", "rge_x")
        assert result.valid is False
        assert "requests" in (result.error or "")

    def test_fetch_failure_reports_api_error(self, monkeypatch):
        import requests

        _patch_get(
            monkeypatch,
            {"/records/LOT-A": requests.exceptions.ConnectionError("refused")},
        )
        result = verify_record_online("LOT-A", "rge_x")
        assert result.valid is False
        assert "API request failed" in (result.error or "")

    def test_matching_server_hash_is_valid_with_chain_position(self, monkeypatch):
        record = _record("LOT-A")
        _patch_get(
            monkeypatch,
            {
                "/records/LOT-A": _Resp(record),
                "/records/LOT-A/verify": _Resp({"chain_position": 3, "hash": record["sha256_hash"]}),
            },
        )
        result = verify_record_online("LOT-A", "rge_x")
        assert result.valid is True
        assert result.chain_position == 3
        assert result.error is None

    def test_server_hash_mismatch_is_invalid(self, monkeypatch):
        record = _record("LOT-A")
        _patch_get(
            monkeypatch,
            {
                "/records/LOT-A": _Resp(record),
                "/records/LOT-A/verify": _Resp({"chain_position": 3, "hash": "f" * 64}),
            },
        )
        result = verify_record_online("LOT-A", "rge_x")
        assert result.valid is False
        assert "mismatch" in (result.error or "").lower()

    def test_verify_endpoint_down_still_returns_offline_result(self, monkeypatch):
        record = _record("LOT-A")
        _patch_get(
            monkeypatch,
            {
                "/records/LOT-A": _Resp(record),
                "/records/LOT-A/verify": _Resp({}, ok=False, status=404),
            },
        )
        result = verify_record_online("LOT-A", "rge_x")
        assert result.valid is True
        assert result.chain_position is None


class TestCliErrorPaths:
    def test_missing_file_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        code = _run_cli(monkeypatch, "--file", str(tmp_path / "nope.json"), "--offline")
        assert code == 1
        assert "File not found" in capsys.readouterr().err

    def test_offline_with_tlc_exits_nonzero(self, monkeypatch, capsys):
        code = _run_cli(monkeypatch, "--tlc", "LOT-A", "--offline")
        assert code == 1
        assert "--offline requires --file" in capsys.readouterr().err

    def test_tlc_without_api_key_exits_nonzero(self, monkeypatch, capsys):
        code = _run_cli(monkeypatch, "--tlc", "LOT-A")
        assert code == 1
        assert "--api-key required" in capsys.readouterr().err

    def test_no_arguments_prints_help_and_exits_nonzero(self, monkeypatch, capsys):
        code = _run_cli(monkeypatch)
        assert code == 1
        assert "usage" in capsys.readouterr().out.lower()


class TestResultReporting:
    def test_mixed_results_exit_nonzero_with_counts(self, capsys):
        good = verify_record_offline(_record("LOT-A"))
        bad_record = _record("LOT-B")
        bad_record["quantity"] = 999
        bad = verify_record_offline(bad_record)
        assert print_results([good, bad]) == 1
        assert "SUMMARY: 1 passed, 1 failed, 2 total" in capsys.readouterr().out

    def test_all_valid_exit_zero(self, capsys):
        assert print_results([verify_record_offline(_record("LOT-A"))]) == 0


class TestEnvelopeEdges:
    @pytest.mark.parametrize("payload", ["just-a-string", 42, None, True])
    def test_scalar_input_is_rejected(self, payload):
        with pytest.raises(UnrecognizedExportError):
            extract_records(payload)

    def test_record_without_digest_is_invalid_not_a_crash(self):
        record = _record("LOT-A")
        del record["sha256_hash"]
        result = verify_record_offline(record)
        assert result.valid is False
        assert result.expected_hash == ""

    def test_alias_keys_hash_identically_to_canonical_keys(self):
        """Short aliases must only rename keys, never change hashed values."""
        canonical = _record("LOT-A")
        aliased = {
            "id": canonical["event_id"],
            "cte_type": canonical["event_type"],
            "tlc": canonical["traceability_lot_code"],
            "product_reference": canonical["product_reference"],
            "quantity": canonical["quantity"],
            "unit_of_measure": canonical["unit_of_measure"],
            "location": canonical["from_facility_reference"],
            "to_facility_reference": canonical["to_facility_reference"],
            "event_timestamp": canonical["event_timestamp"],
            "kdes": canonical["kdes"],
        }
        assert compute_record_hash(aliased) == canonical["sha256_hash"]
        assert verify_record_offline({**aliased, "hash": canonical["sha256_hash"]}).valid is True


class TestDeprecationShim:
    def test_shim_reexports_verifier_symbols(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import regengine.verify_chain as shim

        assert shim.compute_record_hash is compute_record_hash
        assert shim.verify_record_offline is verify_record_offline
        assert shim.extract_records is extract_records
        assert callable(shim.main)
