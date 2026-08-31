#!/usr/bin/env python3
"""Reproduce S2 offline using real export functions and synthetic DB results.

Run from the repository root with:
    .venv/bin/python3 docs/research/deep-market-lab-2026-08-31/export_verification_probe.py

This is an investigation artifact, not a passing product acceptance test. Exit
zero means the documented defects were reproduced. The process clears inherited
environment settings and disables Python socket connections before importing
application code. It does not connect to a database or modify repository data.
"""

from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
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
        from fastapi import HTTPException
        from app.fda_export.verification import verify_export_handler
        from app.fda_export_service import _generate_csv

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
        def __init__(self, _session):
            pass

        def query_events_by_tlc(self, **_kwargs):
            return [dict(event)]

    db_module = ModuleType("shared.database")
    db_module.SessionLocal = SyntheticSession
    cte_module = ModuleType("shared.cte_persistence")
    cte_module.CTEPersistence = SyntheticPersistence
    observations = []

    with patch.dict(sys.modules, {"shared.database": db_module, "shared.cte_persistence": cte_module}):
        for include_pii in (False, True):
            original_hash = hashlib.sha256(
                _generate_csv([event], include_pii=include_pii).encode("utf-8")
            ).hexdigest()
            current_row = (
                "fda_spreadsheet", "SYNTHETIC-LOT-A", None, None,
                1, original_hash, generated_at,
            )
            result = asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
            observations.append({
                "case": "unchanged_fixture",
                "original_include_pii": include_pii,
                "hashes_match": result["hashes_match"],
                "data_integrity": result["data_integrity"],
            })

        for export_type in ("fda_export_all", "fda_export_all_package"):
            current_row = (export_type, None, None, None, 1, original_hash, generated_at)
            try:
                asyncio.run(verify_export_handler("synthetic-export-1", "synthetic-tenant-A"))
            except HTTPException as exc:
                observations.append({"export_type": export_type, "verification_status": exc.status_code})
            else:
                raise AssertionError(f"Expected current verifier to reject producer type {export_type!r}")

    assert observations[0]["hashes_match"] is True, "Redacted control fixture must verify"
    assert observations[1]["hashes_match"] is False, "The documented PII-mode defect was not reproduced"
    assert observations[1]["data_integrity"] == "MISMATCH_DETECTED"
    assert all(row["verification_status"] == 409 for row in observations[2:])
    print(json.dumps({
        "network_disabled": True,
        "database": "synthetic patched reads only",
        "known_defects_reproduced": True,
        "observations": observations,
    }, indent=2))


if __name__ == "__main__":
    main()
