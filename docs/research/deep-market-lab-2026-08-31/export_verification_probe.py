#!/usr/bin/env python3
"""Exercise S2 offline using real export functions and synthetic DB results.

Run from the repository root with:
    .venv/bin/python3 docs/research/deep-market-lab-2026-08-31/export_verification_probe.py

The original failures remain in ``export_verification_results.json``. This
post-integration probe checks the repaired producer/verifier contract plus the
intentional fail-closed cases. Exit zero means those scoped expectations passed;
it is not a product acceptance test. The process clears inherited environment
settings and disables Python socket connections before importing application
code. It does not connect to a database or modify repository data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _deny_network(*_args, **_kwargs):
    raise RuntimeError("Network access is disabled for this offline probe")


def main() -> None:
    # All changes apply only to this disposable process, never the caller's shell.
    os.environ.clear()
    os.environ.update(
        REGENGINE_ENV="test",
        DATABASE_URL="sqlite:///:memory:",
        AUTH_SECRET_KEY="offline-probe-synthetic-secret-long-enough",  # pragma: allowlist secret
        PYTHON_DOTENV_DISABLED="1",
    )
    socket.socket.connect = _deny_network
    socket.socket.connect_ex = _deny_network
    socket.create_connection = _deny_network
    socket.getaddrinfo = _deny_network

    repo_root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(repo_root / "services/ingestion"), str(repo_root / "services")]

    from datetime import datetime, timezone

    # Imported app modules may log configuration warnings. Keep stdout as JSON.
    with redirect_stdout(sys.stderr):
        from app.fda_export.verification import verify_export_handler
        from app.fda_export_service import _generate_csv
        from fastapi import HTTPException

    event = {
        "id": "synthetic-event-1",
        "event_type": "receiving",
        "traceability_lot_code": "SYNTHETIC-LOT-A",
        "quantity": 10,
        "location_name": "Synthetic Test Facility",
        "event_timestamp": "2026-08-31T00:00:00+00:00",
        "kdes": {},
    }
    generated_at = datetime(2026, 8, 31, tzinfo=timezone.utc)
    current_row = None

    class SyntheticResult:
        def fetchone(self):
            return current_row

    class SyntheticSession:
        def execute(self, *_args, **_kwargs):
            return SyntheticResult()

        def close(self):
            pass

    class SyntheticPersistence:
        calls = []

        def __init__(self, _session):
            pass

        def query_events_by_tlc(self, **kwargs):
            self.calls.append({"method": "query_events_by_tlc", **kwargs})
            return [dict(event)]

        def query_all_events(self, **kwargs):
            self.calls.append({"method": "query_all_events", **kwargs})
            return [dict(event)], 1

        def query_events_by_tlcs(self, **kwargs):
            self.calls.append({"method": "query_events_by_tlcs", **kwargs})
            return [dict(event)]

    db_module = ModuleType("shared.database")
    db_module.SessionLocal = SyntheticSession
    cte_module = ModuleType("shared.cte_persistence")
    cte_module.CTEPersistence = SyntheticPersistence
    observations = []

    with patch.dict(sys.modules, {"shared.database": db_module, "shared.cte_persistence": cte_module}):
        for include_pii in (False, True):
            original_hash = hashlib.sha256(_generate_csv([event], include_pii=include_pii).encode("utf-8")).hexdigest()
            current_row = (
                "fda_spreadsheet",
                "SYNTHETIC-LOT-A",
                None,
                None,
                1,
                original_hash,
                generated_at,
                include_pii,
                None,
            )
            result = asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
            observations.append(
                {
                    "case": "single_tlc_round_trip",
                    "original_include_pii": include_pii,
                    "hashes_match": result["hashes_match"],
                    "data_integrity": result["data_integrity"],
                }
            )

        for export_type in ("fda_export_all", "fda_export_all_package"):
            for include_pii in (False, True):
                original_hash = hashlib.sha256(
                    _generate_csv([event], include_pii=include_pii).encode("utf-8")
                ).hexdigest()
                current_row = (
                    export_type,
                    None,
                    None,
                    None,
                    1,
                    original_hash,
                    generated_at,
                    include_pii,
                    "receiving",
                )
                result = asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
                observations.append(
                    {
                        "case": "full_export_round_trip",
                        "export_type": export_type,
                        "original_include_pii": include_pii,
                        "query_event_type": "receiving",
                        "hashes_match": result["hashes_match"],
                        "data_integrity": result["data_integrity"],
                    }
                )

        # Audit rows from before include_pii was persisted cannot be reproduced
        # deterministically. This is an unsupported historical format, not a
        # content-mismatch verdict.
        current_row = (
            "fda_spreadsheet",
            "SYNTHETIC-LOT-A",
            None,
            None,
            1,
            original_hash,
            generated_at,
            None,
            None,
        )
        try:
            asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
        except HTTPException as exc:
            observations.append(
                {
                    "case": "legacy_missing_privacy_mode",
                    "verification_status": exc.status_code,
                    "detail": exc.detail,
                }
            )
        else:
            raise AssertionError("Expected legacy row without include_pii to fail closed")

        # Recall filters include fields that are not fully persisted in the
        # historical audit row. The verifier must refuse rather than guess.
        current_row = (
            "recall",
            None,
            None,
            None,
            1,
            original_hash,
            generated_at,
            False,
            None,
        )
        try:
            asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
        except HTTPException as exc:
            observations.append(
                {
                    "case": "unsupported_recall_filters",
                    "verification_status": exc.status_code,
                    "detail": exc.detail,
                }
            )
        else:
            raise AssertionError("Expected recall audit row without TLC to fail closed")

    round_trips = observations[:6]
    assert all(row["hashes_match"] is True for row in round_trips)
    assert all(row["data_integrity"] == "VERIFIED" for row in round_trips)
    assert observations[6]["verification_status"] == 409
    assert "not a tamper finding" in observations[6]["detail"]
    assert observations[7]["verification_status"] == 409
    assert "not fully reproducible" in observations[7]["detail"]
    full_query_calls = [call for call in SyntheticPersistence.calls if call["method"] == "query_all_events"]
    assert len(full_query_calls) == 4
    assert all(call["event_type"] == "receiving" for call in full_query_calls)

    print(
        json.dumps(
            {
                "network_disabled": True,
                "database": "synthetic patched reads only",
                "historical_baseline": "export_verification_results.json",
                "current_contract_passed": True,
                "observations": observations,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
