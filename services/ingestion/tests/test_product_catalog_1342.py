"""Data-free schema, empty-store, and route checks for product catalog."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app import product_catalog as pc
from app.product_catalog import (
    FTL_CATEGORIES,
    CreateProductRequest,
    Product,
    ProductCatalogResponse,
    _db_get_catalog,
    _db_lookup_by_gtin,
    _derive_products_from_events,
    _fsma_row_to_product,
    _row_to_product,
    learn_from_event,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_product_schema_requires_identity_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        Product.model_validate({})
    assert {error["loc"][0] for error in exc.value.errors()} == {"id", "name", "category"}


def test_catalog_response_schema_requires_summary_fields() -> None:
    with pytest.raises(ValidationError):
        ProductCatalogResponse.model_validate({})


def test_create_product_request_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        CreateProductRequest.model_validate({})
    assert {error["loc"][0] for error in exc.value.errors()} == {"name", "category"}


def test_empty_row_has_only_model_defaults() -> None:
    product = _row_to_product({})
    assert product.name == ""
    assert product.suppliers == []
    assert product.facilities == []
    assert product.cte_count == 0


def test_empty_fsma_row_has_only_model_defaults() -> None:
    product = _fsma_row_to_product({})
    assert product.name == ""
    assert product.suppliers == []
    assert product.facilities == []
    assert product.ftl_covered is False


def test_derive_products_from_empty_result() -> None:
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    assert _derive_products_from_events(db, "") == []


def test_derive_products_sql_error_returns_empty() -> None:
    from sqlalchemy.exc import SQLAlchemyError

    db = MagicMock()
    db.execute.side_effect = SQLAlchemyError()
    assert _derive_products_from_events(db, "") == []


def test_derive_statement_references_only_real_columns() -> None:
    ddl = (Path(__file__).resolve().parents[3] / "alembic/sql/V043__canonical_traceability_events.sql").read_text()
    table = ddl.split("CREATE TABLE IF NOT EXISTS fsma.traceability_events (", 1)[1].split("\n);", 1)[0]
    columns = set(re.findall(r"^ {4}([a-z_]+) ", table, flags=re.MULTILINE))
    assert "event_timestamp" in columns

    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    _derive_products_from_events(db, "")
    sql = str(db.execute.call_args.args[0])
    aliases = {"cte_count", "last_cte", "first_seen", "lot_codes", "array_agg", "fsma", "traceability_events", "tid", "uuid"}
    referenced = set(re.findall(r"\b[a-z_]+\b", sql)) - aliases
    assert referenced <= columns


def test_db_get_catalog_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "get_db_safe", lambda: None)
    assert _db_get_catalog("") is None


def test_db_get_catalog_with_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(pc, "get_db_safe", lambda: db)
    assert _db_get_catalog("") == []
    assert db.close.called


def test_db_lookup_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "get_db_safe", lambda: None)
    assert _db_lookup_by_gtin("", "") is None


def test_learn_from_empty_event_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "get_db_safe", lambda: pytest.fail("empty event accessed database"))
    pc._catalog_store.clear()
    learn_from_event("", {})
    assert pc._catalog_store == {}


def test_ftl_categories_endpoint_has_only_category_metadata() -> None:
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/v1/products/categories/ftl")
    assert response.status_code == 200
    assert response.json() == {"categories": FTL_CATEGORIES, "total": len(FTL_CATEGORIES)}


def test_product_routes_registered() -> None:
    paths = {route.path for route in router.routes}
    assert "/api/v1/products/{tenant_id}" in paths
    assert "/api/v1/products/{tenant_id}/lookup" in paths
    assert "/api/v1/products/categories/ftl" in paths
