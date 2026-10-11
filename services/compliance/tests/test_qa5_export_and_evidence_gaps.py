"""QA deep-pass regression tests for services/compliance.

Covers three gaps found by reading every file in the module:

1. Zero-valued measurements vanish from the FDA spreadsheet
   (``app/fsma_spreadsheet.py::_normalise_event``). Falsy-but-recorded
   values such as ``quantity=0`` or ``temperature=0`` (a routine
   cold-chain reading) rendered as blank cells, indistinguishable from
   "not recorded" on a regulator-facing export.
2. A SUPERSEDED snapshot can still be attested
   (``app/snapshots.py::attest_snapshot``). Refreeze promises the prior
   freeze stays retrievable with its seal intact, but attesting the old
   row afterwards rewrites its content hash and attaches a fresh
   sign-off to stale content.
3. The checklist industry filter does not tolerate surrounding
   whitespace (``app/routes.py::list_checklists``), so
   ``?industry=%20Dairy%20`` reads as "no requirements exist".
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

service_dir = Path(__file__).parent.parent
for key in [key for key in sys.modules if key == "app" or key.startswith("app.") or key == "main"]:
    del sys.modules[key]
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))
_services_dir = service_dir.parent
_repo_root = _services_dir.parent
for _p in (_services_dir, _repo_root):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["REGENGINE_ENV"] = "test"
os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token-compliance"
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-qa5-compliance")

import pytest  # noqa: E402

pytest.importorskip("fastapi")

from app.fsma_spreadsheet import (  # noqa: E402
    FDA_COLUMNS,
    _normalise_event,
    generate_fda_csv,
)
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.database import get_db_session  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.compliance.app.snapshots import router as snapshots_router  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Zero values in the FDA spreadsheet
# ---------------------------------------------------------------------------


class TestZeroValuesPreserved:
    def test_top_level_zero_quantity_is_recorded(self):
        row = _normalise_event({"type": "SHIPPING", "quantity": 0, "kdes": {}})
        assert row["quantity"] == "0"

    def test_kde_zero_quantity_is_recorded(self):
        row = _normalise_event({"type": "SHIPPING", "kdes": {"quantity": 0}})
        assert row["quantity"] == "0"

    def test_zero_temperature_is_recorded(self):
        """0C is a routine cold-chain reading, not a missing value."""
        row = _normalise_event({"type": "SHIPPING", "kdes": {"temperature": 0}})
        assert row["temperature"] == "0"

    def test_zero_float_temperature_is_recorded(self):
        row = _normalise_event({"type": "SHIPPING", "kdes": {"temperature": 0.0}})
        assert row["temperature"] == "0.0"

    def test_zero_extra_kde_survives_in_json_column(self):
        row = _normalise_event({"type": "SHIPPING", "kdes": {"retained_samples": 0}})
        extra = json.loads(row["additional_kdes_json"])
        assert extra["retained_samples"] == 0

    def test_none_and_blank_still_render_empty(self):
        row = _normalise_event(
            {
                "type": "SHIPPING",
                "quantity": None,
                "kdes": {"temperature": None, "carrier": "", "custom": None},
            }
        )
        assert row["quantity"] == ""
        assert row["temperature"] == ""
        assert row["carrier"] == ""
        assert row["additional_kdes_json"] == ""

    def test_csv_row_carries_zero_cells_end_to_end(self):
        events = [
            {
                "type": "SHIPPING",
                "tlc": "TLC-ZERO",
                "quantity": 0,
                "kdes": {"event_date": "2026-03-15T10:00:00Z", "temperature": 0},
            }
        ]
        result = generate_fda_csv(events, start_date="2026-03-01", end_date="2026-03-31")
        rows = list(csv.reader(io.StringIO(result)))
        header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "Event Type (CTE)")
        data = [r for r in rows[header_idx + 1 :] if r and r[0]]
        assert len(data) == 1
        cells = dict(zip(FDA_COLUMNS, data[0]))
        assert cells["quantity"] == "0"
        assert cells["temperature"] == "0"


# ---------------------------------------------------------------------------
# 2. Attesting a superseded snapshot is rejected
# ---------------------------------------------------------------------------

_TENANT = str(uuid4())

_SQLITE_DDL = """
CREATE TABLE fsma.compliance_evidence_snapshots (
    id                   TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    snapshot_name        TEXT NOT NULL,
    snapshot_reason      TEXT,
    created_by           TEXT NOT NULL,
    trigger_alert_id     TEXT,
    is_auto_created      INTEGER NOT NULL DEFAULT 0,
    deadline             TEXT,
    regulatory_citation  TEXT,
    is_attested          INTEGER NOT NULL DEFAULT 0,
    attested_by          TEXT,
    attested_at          TEXT,
    attestation_title    TEXT,
    compliance_status    TEXT NOT NULL DEFAULT 'COMPLIANT',
    active_alert_count   INTEGER NOT NULL DEFAULT 0,
    critical_alert_count INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL,
    snapshot_state       TEXT NOT NULL DEFAULT 'VALID',
    degradation_reason   TEXT,
    captured_at          TEXT NOT NULL
)
"""

_SQLITE_ALERTS_DDL = """
CREATE TABLE fsma.compliance_alerts (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,
    tenant_id    TEXT,
    alert_type   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    resolved     INTEGER NOT NULL DEFAULT 0,
    resolved_at  TEXT,
    created_at   TEXT NOT NULL
)
"""


@pytest.fixture()
def snapshot_client():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS fsma")
        conn.exec_driver_sql(_SQLITE_DDL)
        conn.exec_driver_sql(_SQLITE_ALERTS_DDL)
    app = FastAPI()
    app.include_router(snapshots_router)
    factory = sessionmaker(bind=eng)

    def _db():
        db = factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    async def _auth(request: Request) -> APIKey:
        key = APIKey(
            key_id="test",
            key_hash="",
            name="Test Key",
            tenant_id=_TENANT,
            created_at=datetime.now(timezone.utc),
        )
        request.state.api_key = key
        return key

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_api_key] = _auth
    with TestClient(app) as client:
        yield client
    eng.dispose()


class TestSupersededAttestRejected:
    def test_attest_after_refreeze_is_409(self, snapshot_client):
        created = snapshot_client.post(
            f"/v1/compliance/snapshots/{_TENANT}",
            json={
                "snapshot_name": "Q3 Freeze",
                "snapshot_reason": "FDA audit prep",
                "created_by": "qa@example.com",
            },
        )
        assert created.status_code == 201, created.text
        sid = created.json()["id"]
        original_hash = created.json()["content_hash"]

        refrozen = snapshot_client.post(f"/v1/compliance/snapshots/{_TENANT}/{sid}/refreeze", json={})
        assert refrozen.status_code == 200, refrozen.text

        late = snapshot_client.post(
            f"/v1/compliance/snapshots/{_TENANT}/{sid}/attest",
            json={"attested_by": "Mallory", "attestation_title": "CCO"},
        )
        assert late.status_code == 409

        # The superseded freeze is untouched: same seal, still unattested.
        items = {
            item["id"]: item for item in snapshot_client.get(f"/v1/compliance/snapshots/{_TENANT}").json()["items"]
        }
        assert items[sid]["content_hash"] == original_hash
        assert items[sid]["is_attested"] is False
        assert items[sid]["integrity_verified"] is True
        assert items[sid]["snapshot_state"] == "SUPERSEDED"

    def test_attest_on_valid_row_still_works(self, snapshot_client):
        created = snapshot_client.post(
            f"/v1/compliance/snapshots/{_TENANT}",
            json={"snapshot_name": "Q3 Freeze", "created_by": "qa@example.com"},
        )
        assert created.status_code == 201, created.text
        sid = created.json()["id"]
        attested = snapshot_client.post(
            f"/v1/compliance/snapshots/{_TENANT}/{sid}/attest",
            json={"attested_by": "Chris Sellers", "attestation_title": "Owner"},
        )
        assert attested.status_code == 200, attested.text
        assert attested.json()["is_attested"] is True


# ---------------------------------------------------------------------------
# 3. Industry filter tolerates surrounding whitespace
# ---------------------------------------------------------------------------


class TestIndustryFilterWhitespace:
    def test_padded_industry_name_still_matches(self):
        from main import app as compliance_app

        client = TestClient(compliance_app)
        headers = {"X-RegEngine-API-Key": os.environ["AUTH_TEST_BYPASS_TOKEN"]}
        plain = client.get("/checklists", params={"industry": "Dairy"}, headers=headers)
        assert plain.status_code == 200
        assert plain.json()["total"] >= 1
        padded = client.get("/checklists", params={"industry": "  Dairy  "}, headers=headers)
        assert padded.status_code == 200
        assert [c["id"] for c in padded.json()["checklists"]] == [c["id"] for c in plain.json()["checklists"]]

    def test_padded_industry_id_still_matches(self):
        from main import app as compliance_app

        client = TestClient(compliance_app)
        headers = {"X-RegEngine-API-Key": os.environ["AUTH_TEST_BYPASS_TOKEN"]}
        resp = client.get("/checklists", params={"industry": "  fresh-produce "}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
