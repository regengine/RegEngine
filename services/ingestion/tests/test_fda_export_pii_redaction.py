"""FDA export PII redaction regression tests (#1219).

Covers:

  • By default (``include_pii=False``), facility *names* and shipping
    *locations* are replaced with ``[REDACTED]`` in every CSV/PDF/ZIP
    output path. GLNs and FDA registration numbers stay visible because
    they are the regulatory primary keys the FDA joins on.

  • The freeform "Additional KDEs (JSON)" blob strips values whose keys
    contain address/contact signals.

  • ``include_pii=true`` requires the ``fda.export.pii`` permission; the
    endpoint returns 403 for callers who hold ``fda.export`` alone.

  • Authorized ``include_pii=true`` requests emit full facility/location
    values, set ``X-PII-Redacted: false``, and log
    ``fda_export_pii_included`` to the audit logger.

  • Manifest metadata in the ZIP package records the PII posture in
    ``privacy.pii_redacted`` so downstream consumers can distinguish
    redacted from full-PII exports when comparing content hashes.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import types
import zipfile
from pathlib import Path
from typing import Any, Optional

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import shared.cte_persistence as shared_cte_persistence
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.fda_export.router import router as fda_router
from app.fda_export_service import (
    PII_REDACTION_PLACEHOLDER,
    _event_to_fda_row,
    _event_to_fda_row_v2,
    _generate_csv,
    _generate_csv_v2,
    _redact_extra_kde_pii,
    _redact_location_value,
)


# ─────────────────────────────────────────────────────────────────────
# Direct unit tests for the redaction helper
# ─────────────────────────────────────────────────────────────────────


def test_redact_location_value_redacts_pii_columns_by_default():
    for col in (
        "Location Name",
        "Ship From Name",
        "Ship To Name",
        "Immediate Previous Source",
        "Receiving Location",
    ):
        assert (
            _redact_location_value("Valley Fresh Farms", col, include_pii=False)
            == PII_REDACTION_PLACEHOLDER
        )


def test_redact_location_value_passes_through_when_include_pii_true():
    for col in (
        "Location Name",
        "Ship From Name",
        "Ship To Name",
        "Immediate Previous Source",
        "Receiving Location",
    ):
        assert (
            _redact_location_value("Valley Fresh Farms", col, include_pii=True)
            == "Valley Fresh Farms"
        )


def test_redact_location_value_does_not_touch_non_pii_columns():
    """GLN, FDA registration, product fields must pass through unchanged."""
    for col in (
        "Location GLN",
        "Ship From GLN",
        "Ship To GLN",
        "TLC Source GLN",
        "TLC Source FDA Registration",
        "Product Description",
        "Traceability Lot Code (TLC)",
    ):
        assert (
            _redact_location_value("0614141000005", col, include_pii=False)
            == "0614141000005"
        )


def test_redact_location_value_preserves_empty_strings():
    """Empty column values must stay empty — a blank cell shouldn't become '[REDACTED]'."""
    assert _redact_location_value("", "Location Name", include_pii=False) == ""
    assert _redact_location_value(None or "", "Ship From Name", include_pii=False) == ""


def test_redact_extra_kde_pii_redacts_address_and_contact_keys():
    """Freeform KDE blob strips PII-like values."""
    extras = {
        "facility_address": "123 Farm Road, Springfield",
        "receiver_contact": "Jane Doe",
        "origin_street": "456 Orchard Ln",
        "driver_name": "John Smith",
        "consignee_phone": "+1-555-0100",
        "owner_email": "ops@example.com",
        "temperature_recorded": 38.2,  # number — stays
        "truck_id": "TRK-1234",        # not PII-keyed — stays
    }
    redacted = _redact_extra_kde_pii(extras)
    assert redacted["facility_address"] == PII_REDACTION_PLACEHOLDER
    assert redacted["receiver_contact"] == PII_REDACTION_PLACEHOLDER
    assert redacted["origin_street"] == PII_REDACTION_PLACEHOLDER
    assert redacted["driver_name"] == PII_REDACTION_PLACEHOLDER
    assert redacted["consignee_phone"] == PII_REDACTION_PLACEHOLDER
    assert redacted["owner_email"] == PII_REDACTION_PLACEHOLDER
    # Non-PII and non-string values pass through.
    assert redacted["temperature_recorded"] == 38.2
    assert redacted["truck_id"] == "TRK-1234"


def test_redact_extra_kde_pii_preserves_keys_for_audit_visibility():
    """Keys must remain (so auditors see 'this field was set but redacted')."""
    redacted = _redact_extra_kde_pii({"facility_address": "123 Farm Rd"})
    assert set(redacted.keys()) == {"facility_address"}


# ─────────────────────────────────────────────────────────────────────
# _event_to_fda_row: PII column behavior under both flags
# ─────────────────────────────────────────────────────────────────────


def _leaky_event() -> dict:
    """An event whose KDEs carry maximum PII surface."""
    return {
        "traceability_lot_code": "TLC-ROMAINE-001",
        "event_type": "SHIPPING",
        "product_description": "Romaine Hearts",
        "quantity": 120.0,
        "unit_of_measure": "cases",
        "location_gln": "0614141000005",
        "location_name": "Valley Fresh Farms",
        "event_timestamp": "2026-04-17T09:00:00+00:00",
        "sha256_hash": "a" * 64,
        "chain_hash": "b" * 64,
        "source": "webhook",
        "kdes": {
            "ship_from_gln": "0614141000005",
            "ship_from_location": "Valley Fresh Farms — 123 Farm Rd",
            "ship_to_gln": "0614141000012",
            "ship_to_location": "Fresh Distribution Center — 456 Warehouse Way",
            "receiving_location": "Fresh Distribution Center — 456 Warehouse Way",
            "immediate_previous_source": "Valley Fresh Farms LLC",
            "tlc_source_gln": "0614141000005",
            "tlc_source_fda_reg": "12345678901",
            "reference_document_number": "PO-2026-001",
            "ship_date": "2026-04-17",
            "facility_address": "123 Farm Rd, Springfield IL",
        },
    }


def test_event_to_fda_row_redacts_pii_by_default():
    row = _event_to_fda_row(_leaky_event())
    # Names redacted
    assert row["Location Name"] == PII_REDACTION_PLACEHOLDER
    assert row["Ship From Name"] == PII_REDACTION_PLACEHOLDER
    assert row["Ship To Name"] == PII_REDACTION_PLACEHOLDER
    assert row["Immediate Previous Source"] == PII_REDACTION_PLACEHOLDER
    assert row["Receiving Location"] == PII_REDACTION_PLACEHOLDER
    # GLNs + FDA reg preserved (regulatory keys)
    assert row["Location GLN"] == "0614141000005"
    assert row["Ship From GLN"] == "0614141000005"
    assert row["Ship To GLN"] == "0614141000012"
    assert row["TLC Source GLN"] == "0614141000005"
    assert row["TLC Source FDA Registration"] == "12345678901"
    # Product/lot preserved
    assert row["Traceability Lot Code (TLC)"] == "TLC-ROMAINE-001"
    assert row["Product Description"] == "Romaine Hearts"


def test_event_to_fda_row_emits_pii_when_flag_true():
    row = _event_to_fda_row(_leaky_event(), include_pii=True)
    assert row["Location Name"] == "Valley Fresh Farms"
    assert row["Ship From Name"] == "Valley Fresh Farms — 123 Farm Rd"
    assert row["Ship To Name"] == "Fresh Distribution Center — 456 Warehouse Way"
    assert row["Immediate Previous Source"] == "Valley Fresh Farms LLC"
    assert row["Receiving Location"] == "Fresh Distribution Center — 456 Warehouse Way"


def test_event_to_fda_row_redacts_extras_json_blob_by_default():
    """Freeform KDE blob's address-like key gets redacted."""
    row = _event_to_fda_row(_leaky_event())
    extras = json.loads(row["Additional KDEs (JSON)"])
    assert extras["facility_address"] == PII_REDACTION_PLACEHOLDER


def test_event_to_fda_row_emits_extras_blob_unchanged_when_pii_true():
    row = _event_to_fda_row(_leaky_event(), include_pii=True)
    extras = json.loads(row["Additional KDEs (JSON)"])
    assert extras["facility_address"] == "123 Farm Rd, Springfield IL"


def test_event_to_fda_row_v2_forwards_include_pii():
    """v2 mapper must inherit the redaction behavior."""
    event = _leaky_event()
    event["rule_results"] = [
        {"rule_name": "time_arrow", "passed": True, "why_failed": ""},
    ]
    redacted = _event_to_fda_row_v2(event)
    full = _event_to_fda_row_v2(event, include_pii=True)
    assert redacted["Ship From Name"] == PII_REDACTION_PLACEHOLDER
    assert full["Ship From Name"] == "Valley Fresh Farms — 123 Farm Rd"


# ─────────────────────────────────────────────────────────────────────
# CSV generator: redacted + full paths
# ─────────────────────────────────────────────────────────────────────


def test_generate_csv_redacts_all_pii_columns_by_default():
    csv_content = _generate_csv([_leaky_event()])
    # Facility name must not appear in the CSV
    assert "Valley Fresh Farms" not in csv_content
    assert "Fresh Distribution Center" not in csv_content
    assert "Valley Fresh Farms LLC" not in csv_content
    # Placeholder must appear
    assert PII_REDACTION_PLACEHOLDER in csv_content
    # GLN survives
    assert "0614141000005" in csv_content
    assert "12345678901" in csv_content  # FDA reg


def test_generate_csv_emits_full_pii_when_flag_true():
    csv_content = _generate_csv([_leaky_event()], include_pii=True)
    assert "Valley Fresh Farms" in csv_content
    assert "Fresh Distribution Center" in csv_content
    assert "Valley Fresh Farms LLC" in csv_content


def test_generate_csv_v2_redacts_by_default():
    event = _leaky_event()
    event["rule_results"] = []
    csv_content = _generate_csv_v2([event])
    assert "Valley Fresh Farms" not in csv_content
    assert PII_REDACTION_PLACEHOLDER in csv_content


# ─────────────────────────────────────────────────────────────────────
# End-to-end: endpoint permission gate + audit + headers + manifest
# ─────────────────────────────────────────────────────────────────────


class _FakeChainVerification:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.chain_length = 1
        self.errors: list[str] = []
        self.checked_at = "2026-04-17T10:00:00+00:00"


class _Result:
    def __init__(self, *, row: Any = None, rows: Optional[list[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self):
        self.executes: list[tuple[Any, Any]] = []
        self.rollbacks = 0
        self.commits = 0

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


class _FakePersistence:
    captured_calls: list[dict] = []

    def __init__(self, session):
        self._session = session

    def query_events_by_tlc(self, tenant_id, tlc, start_date=None, end_date=None):
        _ = tenant_id, start_date, end_date
        return [_leaky_event()] if tlc == "TLC-ROMAINE-001" else []

    def query_all_events(self, tenant_id, start_date=None, end_date=None, event_type=None, limit=1000, offset=0):
        _ = tenant_id, start_date, end_date, event_type, limit, offset
        return ([{"traceability_lot_code": "TLC-ROMAINE-001"}], 1)

    def verify_chain(self, tenant_id):
        _ = tenant_id
        return _FakeChainVerification(valid=True)

    def log_export(self, **kwargs):
        _FakePersistence.captured_calls.append(kwargs)
        return "export-log-id"


@pytest.fixture(autouse=True)
def _reset_captured_calls():
    _FakePersistence.captured_calls = []
    yield
    _FakePersistence.captured_calls = []


def _install_fakes(monkeypatch):
    fake_db_module = types.ModuleType("shared.database")
    fake_db_module.SessionLocal = lambda: _FakeSession()
    monkeypatch.setitem(sys.modules, "shared.database", fake_db_module)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", _FakePersistence)


def _client_with_scopes(monkeypatch, scopes: list[str]):
    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-user-key-abc123",
        scopes=scopes,
        auth_mode="test",
        tenant_id="00000000-0000-0000-0000-000000000111",
    )
    _install_fakes(monkeypatch)
    return TestClient(app)


# ── Default behavior: CSV body and X-PII-Redacted header ──


def test_endpoint_default_csv_redacts_pii(monkeypatch):
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Valley Fresh Farms" not in body
    assert PII_REDACTION_PLACEHOLDER in body
    # GLN and FDA reg still present
    assert "0614141000005" in body
    assert "12345678901" in body
    assert resp.headers["X-PII-Redacted"] == "true"


def test_endpoint_include_pii_without_permission_returns_403(monkeypatch):
    """A caller with ``fda.export`` but NOT ``fda.export.pii`` must be blocked."""
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 403, resp.text
    assert "fda.export.pii" in resp.json()["detail"]
    # Critically: no log_export call — authorization ran BEFORE DB work.
    assert _FakePersistence.captured_calls == []


def test_endpoint_include_pii_with_permission_returns_full_values(monkeypatch):
    client = _client_with_scopes(monkeypatch, ["fda.export", "fda.export.pii"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Valley Fresh Farms" in body
    assert "Fresh Distribution Center" in body
    assert resp.headers["X-PII-Redacted"] == "false"


def test_endpoint_include_pii_with_wildcard_scope_allowed(monkeypatch):
    """Wildcard '*' implies fda.export.pii — admin-tier callers pass."""
    client = _client_with_scopes(monkeypatch, ["*"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 200
    assert "Valley Fresh Farms" in resp.text


def test_endpoint_include_pii_with_fda_namespace_wildcard_allowed(monkeypatch):
    """fda.* namespace wildcard covers fda.export.pii."""
    client = _client_with_scopes(monkeypatch, ["fda.*"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 200
    assert "Valley Fresh Farms" in resp.text


# ── Audit log: pii_included flag captured in every export ──


def test_endpoint_audit_log_captures_pii_included_false(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="fda-export")
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
        },
    )
    assert resp.status_code == 200
    audit_records = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_audit"
    ]
    assert audit_records
    assert getattr(audit_records[0], "pii_included", None) is False


def test_endpoint_audit_log_captures_pii_included_true(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="fda-export")
    client = _client_with_scopes(monkeypatch, ["*"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 200
    # Both the authorization audit line AND the main export audit line
    # should carry pii_included.
    pii_audit = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_pii_included"
    ]
    assert pii_audit, "expected fda_export_pii_included audit line"
    assert getattr(pii_audit[0], "pii_included", None) is True
    assert getattr(pii_audit[0], "user_id", None) == "test-user-key-abc123"

    main_audit = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_audit"
    ]
    assert main_audit
    assert getattr(main_audit[0], "pii_included", None) is True


def test_endpoint_denied_attempt_logs_warning(monkeypatch, caplog):
    """A refused include_pii request must log at WARNING for ops detection."""
    caplog.set_level(logging.WARNING, logger="fda-export")
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "csv",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 403
    denied = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_pii_access_denied"
    ]
    assert denied
    assert denied[0].levelno == logging.WARNING
    assert getattr(denied[0], "user_id", None) == "test-user-key-abc123"


# ── ZIP package: manifest privacy.pii_redacted is correct ──


def _package_manifest(resp_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(resp_bytes)) as zf:
        with zf.open("manifest.json") as f:
            return json.loads(f.read().decode("utf-8"))


def test_package_manifest_pii_redacted_default_true(monkeypatch):
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "package",
            "allow_incomplete": "true",
        },
    )
    assert resp.status_code == 200
    manifest = _package_manifest(resp.content)
    assert manifest["privacy"]["pii_redacted"] is True
    assert "Location Name" in manifest["privacy"]["redacted_columns"]
    assert "Ship From Name" in manifest["privacy"]["redacted_columns"]


def test_package_manifest_pii_redacted_false_when_included(monkeypatch):
    client = _client_with_scopes(monkeypatch, ["*"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "package",
            "allow_incomplete": "true",
            "include_pii": "true",
        },
    )
    assert resp.status_code == 200
    manifest = _package_manifest(resp.content)
    assert manifest["privacy"]["pii_redacted"] is False


def test_package_csv_body_redacted_by_default(monkeypatch):
    """The CSV INSIDE the ZIP must also be redacted, not just the top-level CSV."""
    client = _client_with_scopes(monkeypatch, ["fda.export"])
    resp = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-ROMAINE-001",
            "format": "package",
            "allow_incomplete": "true",
        },
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        assert csv_names
        csv_body = zf.read(csv_names[0]).decode("utf-8")
    assert "Valley Fresh Farms" not in csv_body
    assert PII_REDACTION_PLACEHOLDER in csv_body


# ── Regression lock: the exact field path the issue reported ──


def test_1219_regression_lock_ship_from_location_redacted():
    """Regression lock for #1219 — the specific field path cited in the
    issue (``kdes.ship_from_location`` → 'Ship From Name') must be
    redacted by default.
    """
    event = {
        "traceability_lot_code": "LOT",
        "event_type": "SHIPPING",
        "product_description": "P",
        "kdes": {"ship_from_location": "Customer Acme Farms"},
    }
    row = _event_to_fda_row(event)
    assert row["Ship From Name"] == PII_REDACTION_PLACEHOLDER
    # Full path
    row_full = _event_to_fda_row(event, include_pii=True)
    assert row_full["Ship From Name"] == "Customer Acme Farms"


def test_1219_regression_lock_receiving_location_redacted():
    """The fallback path (ship_to_location → receiving_location) also
    redacted by default.
    """
    event = {
        "traceability_lot_code": "LOT",
        "event_type": "RECEIVING",
        "product_description": "P",
        "kdes": {"receiving_location": "Acme Distribution — 456 Wharf St"},
    }
    row = _event_to_fda_row(event)
    # Both columns draw from the same KDE; both redacted.
    assert row["Ship To Name"] == PII_REDACTION_PLACEHOLDER
    assert row["Receiving Location"] == PII_REDACTION_PLACEHOLDER


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
