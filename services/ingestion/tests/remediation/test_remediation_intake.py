"""Data-free manifest intake rejection tests."""

from __future__ import annotations

import csv
import io

import pytest
from app.remediation import service
from fastapi import HTTPException

HEADER = (
    "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,"
    "previous_source,tlc_source,reference_document\n"
)


@pytest.mark.parametrize("raw", [b"", HEADER.encode()])
def test_manifest_without_data_rows_is_rejected_before_persistence(monkeypatch, raw):
    def unexpected_persistence(*_args, **_kwargs):
        pytest.fail("An empty manifest reached persistence")

    monkeypatch.setattr(service, "_require_uuid_tenant", lambda value: value)
    monkeypatch.setattr(service, "set_tenant_guc", lambda *_args: None)
    monkeypatch.setattr(service, "CanonicalEventStore", unexpected_persistence)

    with pytest.raises(HTTPException) as excinfo:
        service.ingest_manifest(
            object(),
            tenant_id="",
            raw_bytes=raw,
            filename="manifest.csv",
            content_type="text/csv",
            uploaded_by=None,
            supplier_org="",
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Manifest contains no data rows"


def test_manifest_header_is_parsed_without_a_data_row():
    reader = csv.DictReader(io.StringIO(service._decode_manifest_bytes(HEADER.encode())))
    assert reader.fieldnames == HEADER.strip().split(",")
    assert list(reader) == []


def test_upload_requires_a_file(monkeypatch):
    from app import authz
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.remediation.router import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from shared.database import get_db_session

    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 0))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(key_id="", scopes=["*"])
    app.dependency_overrides[get_db_session] = lambda: None

    response = TestClient(app).post("/api/v1/remediation/manifests", data={"supplier_org": ""})
    assert response.status_code == 422
    assert any(error["loc"][-1] == "file" for error in response.json()["detail"])
