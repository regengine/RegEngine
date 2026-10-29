"""Hardening tests for the product catalog router.

Covers (data-free, no live DB/network):

- Rate limits on the mutation routes (POST/PUT/DELETE) return 429 when the
  shared slowapi limit is exceeded.
- Best-effort audit events fire on successful mutations and are skipped on
  404s, carrying field NAMES only (never values).
- Bounded request models reject over-length / over-count payloads (422) and
  accept boundary-valid ones.
- Negative auth: unauthenticated mutations return 401/403 using the real
  ``require_tenant_context``; a context pinned to one tenant cannot read,
  update, or delete another tenant's product, and writes land under
  ``ctx.tenant_id`` rather than the client-supplied path tenant id.
"""

from __future__ import annotations

import pytest
from app import product_catalog as pc
from app.product_catalog import (
    CreateProductRequest,
    Product,
    UpdateProductRequest,
    router,
)
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.rate_limit import limiter
from shared.tenant_context import TenantContext
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ---------------------------------------------------------------------------
# App / fixtures
# ---------------------------------------------------------------------------


def _build_app(*, pinned_tenant: str | None = "tenant-a", authed: bool = True) -> FastAPI:
    app = FastAPI()
    # slowapi needs the limiter on app.state and an exception handler to turn
    # RateLimitExceeded into a 429 response.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router)

    if authed:

        async def _ctx(request: Request) -> TenantContext:
            return TenantContext(
                tenant_id=pinned_tenant,
                principal_kind="test",
                principal_id="router-test",
            )

        app.dependency_overrides[pc.require_tenant_context] = _ctx
    return app


def _reset_limiter() -> None:
    try:
        limiter.reset()
    except Exception:  # pragma: no cover — defensive fallback
        storage = getattr(limiter, "_storage", None) or getattr(getattr(limiter, "limiter", None), "storage", None)
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    """Reset limiter + in-memory store and force the memory fallback path."""
    _reset_limiter()
    pc._catalog_store.clear()
    # No DB in these unit tests: every _db_* helper falls through to memory.
    monkeypatch.setattr(pc, "get_db_safe", lambda: None)
    yield
    _reset_limiter()
    pc._catalog_store.clear()


def _valid_body() -> dict:
    return {"name": "Romaine", "category": "Leafy Greens", "sku": "SKU1"}


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


def test_add_product_rate_limited() -> None:
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(35):
        resp = client.post("/api/v1/products/tenant-a", json=_valid_body())
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_update_product_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make the target exist so we exercise the limiter, not a 404.
    monkeypatch.setattr(
        pc,
        "_memory_get_product",
        lambda t, pid: Product(id=pid, name="x", category="Leafy Greens"),
    )
    monkeypatch.setattr(
        pc,
        "_memory_update_product",
        lambda t, pid, product: product,
    )
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(35):
        resp = client.put("/api/v1/products/tenant-a/p1", json=_valid_body())
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_delete_product_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_memory_delete_product", lambda t, pid: True)
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(35):
        resp = client.delete("/api/v1/products/tenant-a/p1")
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


# ---------------------------------------------------------------------------
# Audit on success / none on 404
# ---------------------------------------------------------------------------


def test_add_product_emits_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(pc, "_audit_product_mutation", lambda **kw: calls.append(kw))
    client = TestClient(_build_app())
    resp = client.post("/api/v1/products/tenant-a", json=_valid_body())
    assert resp.status_code == 200
    assert len(calls) == 1
    call = calls[0]
    assert call["event_type_name"] == "DATA_CREATE"
    assert call["tenant_id"] == "tenant-a"
    assert call["product_id"] == resp.json()["product"]["id"]
    # Field NAMES only — never values.
    assert "name" in call["changed_fields"]
    assert "Romaine" not in call["changed_fields"]


def test_update_product_emits_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(pc, "_audit_product_mutation", lambda **kw: calls.append(kw))
    monkeypatch.setattr(pc, "_memory_get_product", lambda t, pid: Product(id=pid, name="x", category="Herbs"))
    monkeypatch.setattr(pc, "_memory_update_product", lambda t, pid, product: product)
    client = TestClient(_build_app())
    resp = client.put("/api/v1/products/tenant-a/p1", json=_valid_body())
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["event_type_name"] == "DATA_UPDATE"
    assert calls[0]["product_id"] == "p1"


def test_delete_product_emits_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(pc, "_audit_product_mutation", lambda **kw: calls.append(kw))
    monkeypatch.setattr(pc, "_memory_delete_product", lambda t, pid: True)
    client = TestClient(_build_app())
    resp = client.delete("/api/v1/products/tenant-a/p1")
    assert resp.status_code == 204
    assert len(calls) == 1
    assert calls[0]["event_type_name"] == "DATA_DELETE"


# ---------------------------------------------------------------------------
# Audit actor provenance (PR #3745): actor is the signed-in principal, not a
# hardcoded service identity.
# ---------------------------------------------------------------------------


class _FakeAuditLogger:
    """Fake AuditLogger that records the actor passed to ``log`` synchronously.

    ``log`` is invoked (and its kwargs materialised) before the router
    schedules the fire-and-forget task, so the actor is captured even though
    the returned coroutine may never be awaited.
    """

    def __init__(self, sink: list) -> None:
        self._sink = sink

    def log(self, **kwargs):
        self._sink.append(kwargs)

        async def _noop() -> None:
            return None

        return _noop()


def _install_fake_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    import shared.audit_logging as audit_mod

    sink: list[dict] = []
    fake = _FakeAuditLogger(sink)
    monkeypatch.setattr(audit_mod.AuditLogger, "get_instance", classmethod(lambda cls: fake))
    return sink


def test_add_audit_actor_is_signed_in_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(_build_app())
    resp = client.post("/api/v1/products/tenant-a", json=_valid_body())
    assert resp.status_code == 200
    assert len(sink) == 1
    actor = sink[0]["actor"]
    assert actor.actor_id == "router-test"
    assert actor.actor_type == "test"
    assert actor.actor_id != "product-catalog"
    assert actor.actor_type != "service"
    assert actor.tenant_id == "tenant-a"


def test_add_audit_actor_email_from_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()

    async def _ctx(request: Request) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-a",
            principal_kind="test",
            principal_id="router-test",
            actor_email="[email protected]",
        )

    app.dependency_overrides[pc.require_tenant_context] = _ctx
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(app)
    resp = client.post("/api/v1/products/tenant-a", json=_valid_body())
    assert resp.status_code == 200
    assert len(sink) == 1
    actor = sink[0]["actor"]
    assert actor.actor_id == "router-test"
    assert actor.email == "[email protected]"


def test_update_delete_audit_actor_is_signed_in_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_memory_get_product", lambda t, pid: Product(id=pid, name="x", category="Herbs"))
    monkeypatch.setattr(pc, "_memory_update_product", lambda t, pid, product: product)
    monkeypatch.setattr(pc, "_memory_delete_product", lambda t, pid: True)
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(_build_app())

    resp = client.put("/api/v1/products/tenant-a/p1", json=_valid_body())
    assert resp.status_code == 200
    resp = client.delete("/api/v1/products/tenant-a/p1")
    assert resp.status_code == 204

    assert len(sink) == 2
    for call in sink:
        actor = call["actor"]
        assert actor.actor_id == "router-test"
        assert actor.actor_type == "test"
        assert actor.actor_id != "product-catalog"
        assert actor.actor_type != "service"


def test_no_audit_on_update_404(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(pc, "_audit_product_mutation", lambda **kw: calls.append(kw))
    client = TestClient(_build_app())
    resp = client.put("/api/v1/products/tenant-a/missing", json=_valid_body())
    assert resp.status_code == 404
    assert calls == []


def test_no_audit_on_delete_404(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(pc, "_audit_product_mutation", lambda **kw: calls.append(kw))
    client = TestClient(_build_app())
    resp = client.delete("/api/v1/products/tenant-a/missing")
    assert resp.status_code == 404
    assert calls == []


# ---------------------------------------------------------------------------
# Bounded request models
# ---------------------------------------------------------------------------


def test_create_request_rejects_over_length_name() -> None:
    with pytest.raises(ValidationError):
        CreateProductRequest(name="x" * 201, category="Leafy Greens")


def test_create_request_rejects_over_count_suppliers() -> None:
    with pytest.raises(ValidationError):
        CreateProductRequest(name="n", category="c", suppliers=["s"] * 101)


def test_create_request_rejects_over_length_supplier_item() -> None:
    with pytest.raises(ValidationError):
        CreateProductRequest(name="n", category="c", suppliers=["x" * 201])


def test_create_request_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        CreateProductRequest(name="n", category="c", tenant_id="tenant-b")


def test_update_request_rejects_over_length_description() -> None:
    with pytest.raises(ValidationError):
        UpdateProductRequest(name="n", category="c", description="d" * 2001)


def test_boundary_valid_request_passes() -> None:
    model = CreateProductRequest(
        name="n" * 200,
        category="c" * 100,
        sku="s" * 100,
        gtin="g" * 14,
        description="d" * 2000,
        suppliers=["x" * 200] * 100,
        facilities=["y" * 200] * 100,
    )
    assert len(model.suppliers) == 100


def test_route_rejects_over_length_payload() -> None:
    client = TestClient(_build_app())
    resp = client.post(
        "/api/v1/products/tenant-a",
        json={"name": "x" * 201, "category": "Leafy Greens"},
    )
    assert resp.status_code == 422


def test_route_rejects_extra_keys_payload() -> None:
    client = TestClient(_build_app())
    resp = client.post(
        "/api/v1/products/tenant-a",
        json={"name": "n", "category": "c", "tenant_id": "tenant-b"},
    )
    assert resp.status_code == 422


def test_route_accepts_boundary_valid_payload() -> None:
    client = TestClient(_build_app())
    resp = client.post(
        "/api/v1/products/tenant-a",
        json={
            "name": "n" * 200,
            "category": "Leafy Greens",
            "sku": "s" * 100,
            "gtin": "g" * 14,
            "description": "d" * 2000,
            "suppliers": ["x" * 200] * 100,
            "facilities": ["y" * 200] * 100,
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Negative auth / tenant isolation
# ---------------------------------------------------------------------------


def test_unauthenticated_post_rejected() -> None:
    # Real require_tenant_context, no override, no credentials.
    client = TestClient(_build_app(authed=False))
    resp = client.post("/api/v1/products/tenant-a", json=_valid_body())
    assert resp.status_code in (401, 403)


def test_unauthenticated_put_rejected() -> None:
    client = TestClient(_build_app(authed=False))
    resp = client.put("/api/v1/products/tenant-a/p1", json=_valid_body())
    assert resp.status_code in (401, 403)


def test_unauthenticated_delete_rejected() -> None:
    client = TestClient(_build_app(authed=False))
    resp = client.delete("/api/v1/products/tenant-a/p1")
    assert resp.status_code in (401, 403)


def _seed_tenant_b_product() -> Product:
    product = Product(id="b-prod", name="Secret", category="Herbs", gtin="0001")
    pc._catalog_store["tenant-b"] = [product]
    return product


def test_wrong_tenant_cannot_get_other_product() -> None:
    _seed_tenant_b_product()
    client = TestClient(_build_app(pinned_tenant="tenant-a"))
    resp = client.get("/api/v1/products/tenant-b/b-prod")
    assert resp.status_code == 404


def test_wrong_tenant_cannot_update_other_product() -> None:
    original = _seed_tenant_b_product()
    client = TestClient(_build_app(pinned_tenant="tenant-a"))
    resp = client.put("/api/v1/products/tenant-b/b-prod", json=_valid_body())
    assert resp.status_code == 404
    # tenant-b record is unchanged.
    assert pc._catalog_store["tenant-b"][0].name == original.name
    assert pc._catalog_store["tenant-b"][0].name == "Secret"


def test_wrong_tenant_cannot_delete_other_product() -> None:
    _seed_tenant_b_product()
    client = TestClient(_build_app(pinned_tenant="tenant-a"))
    resp = client.delete("/api/v1/products/tenant-b/b-prod")
    assert resp.status_code == 404
    # tenant-b record still present.
    assert len(pc._catalog_store["tenant-b"]) == 1


def test_write_lands_under_ctx_tenant_not_path_tenant() -> None:
    client = TestClient(_build_app(pinned_tenant="tenant-a"))
    # Path says tenant-b, but the authenticated ctx is tenant-a.
    resp = client.post("/api/v1/products/tenant-b", json=_valid_body())
    assert resp.status_code == 200
    assert "tenant-a" in pc._catalog_store
    assert "tenant-b" not in pc._catalog_store
