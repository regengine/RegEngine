"""Focused coverage tests for the admin content-graph overlay API.

Covers services/admin/app/api_overlay.py with a minimal FastAPI app and
faked OverlayWriter/OverlayResolver collaborators, so no database, graph,
or external service is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app import api_overlay as overlay_mod
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from shared.auth import APIKey
from shared.tenant_models import MappingType, ProductType

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CONTROL_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
PRODUCT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
MAPPING_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

# One shared app and client for the whole module: building a TestClient
# portal per test costs ~0.5s each, which would push the suite past its
# ~10s budget. Each test installs its own auth override and writer /
# resolver fakes, and the autouse fixture below clears the overrides.
_APP = FastAPI()
_APP.include_router(overlay_mod.router)
_CLIENT = TestClient(_APP)


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    _APP.dependency_overrides.clear()


def _api_key(**overrides) -> APIKey:
    values: dict = {
        "key_id": "test-key-1",
        "key_hash": "hash",
        "name": "test",
        "tenant_id": str(TENANT_ID),
        "created_at": NOW,
    }
    values.update(overrides)
    return APIKey(**values)


def _client_for(api_key: APIKey) -> TestClient:
    _APP.dependency_overrides[overlay_mod.require_api_key] = lambda: api_key
    return _CLIENT


def _control_ns(**overrides) -> SimpleNamespace:
    values: dict = {
        "id": CONTROL_ID,
        "tenant_id": TENANT_ID,
        "control_id": "CTRL-1",
        "title": "Access control",
        "description": "Restrict access",
        "framework": "NIST CSF",
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _product_ns(**overrides) -> SimpleNamespace:
    values: dict = {
        "id": PRODUCT_ID,
        "tenant_id": TENANT_ID,
        "product_name": "Spring mix",
        "description": "Bagged greens",
        "product_type": ProductType.TRADING,
        "jurisdictions": ["US"],
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _mapping_ns(**overrides) -> SimpleNamespace:
    values: dict = {
        "id": MAPPING_ID,
        "tenant_id": TENANT_ID,
        "control_id": CONTROL_ID,
        "provision_hash": "abc123",
        "mapping_type": MappingType.IMPLEMENTS,
        "confidence": 0.9,
        "notes": None,
        "created_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_tenant_id_returns_uuid() -> None:
    assert overlay_mod.get_tenant_id_from_api_key(_api_key()) == TENANT_ID


def test_get_tenant_id_missing_raises_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        overlay_mod.get_tenant_id_from_api_key(_api_key(tenant_id=None))
    assert exc_info.value.status_code == 403


def test_missing_tenant_id_returns_403_at_http(monkeypatch) -> None:
    monkeypatch.setattr(overlay_mod, "OverlayWriter", lambda tenant_id: pytest.fail("writer must not be called"))
    response = _client_for(_api_key(tenant_id=None)).get("/v1/overlay/controls")
    assert response.status_code == 403


def test_create_control_returns_201(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            assert tenant_id == TENANT_ID

        def create_tenant_control(self, control) -> SimpleNamespace:
            assert control.tenant_id == TENANT_ID
            assert control.control_id == "CTRL-1"
            return _control_ns()

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {
        "control_id": "CTRL-1",
        "title": "Access control",
        "description": "Restrict access",
        "framework": "NIST CSF",
    }
    response = _client_for(_api_key()).post("/v1/overlay/controls", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["control_id"] == "CTRL-1"
    assert body["tenant_id"] == str(TENANT_ID)


def test_create_control_writer_failure_returns_500(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def create_tenant_control(self, control) -> SimpleNamespace:
            raise RuntimeError("db down")

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {"control_id": "CTRL-1", "title": "T", "description": "D", "framework": "F"}
    response = _client_for(_api_key()).post("/v1/overlay/controls", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "internal_error"


def test_create_control_rejects_blank_title() -> None:
    payload = {"control_id": "CTRL-1", "title": "", "description": "D", "framework": "F"}
    response = _client_for(_api_key()).post("/v1/overlay/controls", json=payload)
    assert response.status_code == 422


def test_list_controls_passes_filter_and_pagination(monkeypatch) -> None:
    observed: dict = {}

    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        async def list_controls(self, *, framework=None, skip=0, limit=50):
            observed.update(framework=framework, skip=skip, limit=limit)
            return ([{"id": "c1"}], 1)

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).get("/v1/overlay/controls", params={"framework": "SOC2", "skip": 5, "limit": 10})
    assert response.status_code == 200
    assert observed == {"framework": "SOC2", "skip": 5, "limit": 10}
    body = response.json()
    assert body["total"] == 1
    assert body["controls"] == [{"id": "c1"}]


def test_get_control_details_not_found_returns_404(monkeypatch) -> None:
    class Resolver:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def get_control_details(self, control_id: uuid.UUID) -> dict:
            assert control_id == CONTROL_ID
            return {"error": "not found"}

    monkeypatch.setattr(overlay_mod, "OverlayResolver", Resolver)
    response = _client_for(_api_key()).get(f"/v1/overlay/controls/{CONTROL_ID}")
    assert response.status_code == 404


def test_get_control_details_returns_payload(monkeypatch) -> None:
    class Resolver:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def get_control_details(self, control_id: uuid.UUID) -> dict:
            return {"control_id": str(control_id), "mappings": []}

    monkeypatch.setattr(overlay_mod, "OverlayResolver", Resolver)
    response = _client_for(_api_key()).get(f"/v1/overlay/controls/{CONTROL_ID}")
    assert response.status_code == 200
    assert response.json()["mappings"] == []


def test_update_control_not_found_returns_404(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def update_control(self, **kwargs) -> None:
            return None

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {"control_id": "CTRL-1", "title": "T2", "description": "D2", "framework": "F2"}
    response = _client_for(_api_key()).put(f"/v1/overlay/controls/{CONTROL_ID}", json=payload)
    assert response.status_code == 404


def test_delete_control_returns_204(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def delete_control(self, control_id: uuid.UUID) -> bool:
            assert control_id == CONTROL_ID
            return True

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).delete(f"/v1/overlay/controls/{CONTROL_ID}")
    assert response.status_code == 204


def test_delete_control_missing_returns_404(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def delete_control(self, control_id: uuid.UUID) -> bool:
            return False

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).delete(f"/v1/overlay/controls/{CONTROL_ID}")
    assert response.status_code == 404


def test_create_product_returns_201(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def create_customer_product(self, product) -> SimpleNamespace:
            assert product.product_type == ProductType.TRADING
            return _product_ns()

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {
        "product_name": "Spring mix",
        "description": "Bagged greens",
        "product_type": "TRADING",
        "jurisdictions": ["US"],
    }
    response = _client_for(_api_key()).post("/v1/overlay/products", json=payload)
    assert response.status_code == 201
    assert response.json()["product_name"] == "Spring mix"


def test_list_products_returns_items(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        async def list_products(self, *, product_type=None, skip=0, limit=50):
            assert product_type is None
            return ([{"id": "p1"}], 1)

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).get("/v1/overlay/products")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_get_product_requirements_not_found_returns_404(monkeypatch) -> None:
    class Resolver:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def get_regulatory_requirements(self, product_id: uuid.UUID) -> dict:
            return {"error": "no such product"}

    monkeypatch.setattr(overlay_mod, "OverlayResolver", Resolver)
    response = _client_for(_api_key()).get(f"/v1/overlay/products/{PRODUCT_ID}/requirements")
    assert response.status_code == 404


def test_get_compliance_gaps_returns_payload(monkeypatch) -> None:
    observed: dict = {}

    class Resolver:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def get_compliance_gaps(self, product_id: uuid.UUID, jurisdiction: str) -> dict:
            observed.update(product_id=product_id, jurisdiction=jurisdiction)
            return {"gaps": []}

    monkeypatch.setattr(overlay_mod, "OverlayResolver", Resolver)
    response = _client_for(_api_key()).get(
        f"/v1/overlay/products/{PRODUCT_ID}/compliance-gaps", params={"jurisdiction": "US"}
    )
    assert response.status_code == 200
    assert response.json() == {"gaps": []}
    assert observed == {"product_id": PRODUCT_ID, "jurisdiction": "US"}


def test_create_mapping_returns_201(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def map_control_to_provision(self, mapping) -> SimpleNamespace:
            assert mapping.confidence == 0.9
            return _mapping_ns()

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {
        "control_id": str(CONTROL_ID),
        "provision_hash": "abc123",
        "mapping_type": "IMPLEMENTS",
        "confidence": 0.9,
    }
    response = _client_for(_api_key()).post("/v1/overlay/mappings", json=payload)
    assert response.status_code == 201
    assert response.json()["provision_hash"] == "abc123"


def test_create_mapping_validation_error_returns_400(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def map_control_to_provision(self, mapping) -> SimpleNamespace:
            raise ValueError("unknown control")

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {
        "control_id": str(CONTROL_ID),
        "provision_hash": "abc123",
        "mapping_type": "IMPLEMENTS",
        "confidence": 0.5,
    }
    response = _client_for(_api_key()).post("/v1/overlay/mappings", json=payload)
    assert response.status_code == 400


def test_create_mapping_rejects_confidence_above_one() -> None:
    payload = {
        "control_id": str(CONTROL_ID),
        "provision_hash": "abc123",
        "mapping_type": "IMPLEMENTS",
        "confidence": 1.5,
    }
    response = _client_for(_api_key()).post("/v1/overlay/mappings", json=payload)
    assert response.status_code == 422


def test_link_control_to_product_returns_201(monkeypatch) -> None:
    created_at = NOW.isoformat()

    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def link_control_to_product(self, link) -> SimpleNamespace:
            assert link.product_id == PRODUCT_ID
            assert link.control_id == CONTROL_ID
            return SimpleNamespace(product_id=PRODUCT_ID, control_id=CONTROL_ID, tenant_id=TENANT_ID, created_at=NOW)

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    payload = {"control_id": str(CONTROL_ID), "product_id": str(PRODUCT_ID)}
    response = _client_for(_api_key()).post("/v1/overlay/products/link-control", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["product_id"] == str(PRODUCT_ID)
    assert body["created_at"] == created_at


def test_delete_mapping_missing_returns_404(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def delete_mapping(self, mapping_id: uuid.UUID) -> bool:
            return False

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).delete(f"/v1/overlay/mappings/{MAPPING_ID}")
    assert response.status_code == 404


def test_delete_product_missing_returns_404(monkeypatch) -> None:
    class Writer:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def delete_product(self, product_id: uuid.UUID) -> bool:
            return False

    monkeypatch.setattr(overlay_mod, "OverlayWriter", Writer)
    response = _client_for(_api_key()).delete(f"/v1/overlay/products/{PRODUCT_ID}")
    assert response.status_code == 404


def test_get_provision_overlays_returns_payload(monkeypatch) -> None:
    class Resolver:
        def __init__(self, tenant_id: uuid.UUID) -> None:
            pass

        def get_provision_with_overlays(self, provision_hash: str) -> dict:
            assert provision_hash == "abc123"
            return {"provision_hash": "abc123", "controls": []}

    monkeypatch.setattr(overlay_mod, "OverlayResolver", Resolver)
    response = _client_for(_api_key()).get("/v1/overlay/provisions/abc123/overlays")
    assert response.status_code == 200
    assert response.json()["controls"] == []
