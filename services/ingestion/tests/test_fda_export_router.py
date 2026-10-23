"""Data-free FDA export route contract checks."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fda_export.router import router  # noqa: E402


def test_export_routes_are_registered() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/fda/export" in paths
    assert "/api/v1/fda/export/all" in paths
    assert "/api/v1/fda/export/verify" in paths


def test_single_export_requires_tenant_and_lot_query_fields() -> None:
    app = FastAPI()
    app.include_router(router)
    parameters = app.openapi()["paths"]["/api/v1/fda/export"]["get"]["parameters"]
    required = {item["name"] for item in parameters if item.get("required")}
    assert {"tenant_id", "tlc"} <= required


def test_export_defaults_to_redacted_package() -> None:
    app = FastAPI()
    app.include_router(router)
    parameters = app.openapi()["paths"]["/api/v1/fda/export"]["get"]["parameters"]
    defaults = {item["name"]: item.get("schema", {}).get("default") for item in parameters}
    assert defaults["include_pii"] is False
    assert defaults["format"] == "package"
