"""SEL-513: mock audit drills never use random or invented audit data."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app import mock_audit as ma
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    ma._active_drills.clear()
    monkeypatch.setattr(ma, "_persist_drill", lambda *a: None)
    app = FastAPI()
    app.include_router(ma.router)
    from app.webhook_compat import _verify_api_key

    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant="t1")
    yield TestClient(app)
    ma._active_drills.clear()


def test_no_random_source_in_module():
    src = Path(ma.__file__).read_text()
    assert "import random" not in src
    assert "ORDER BY random()" not in src


def test_templates_carry_no_placeholder_lots_or_products():
    for tpl in ma.FDA_SCENARIOS:
        assert "target_tlc" not in tpl
        assert "target_product" not in tpl
        assert "demo_mode" not in tpl


def test_tenant_without_records_gets_409_not_demo_drill(client, monkeypatch):
    monkeypatch.setattr(ma, "_get_real_tlc", lambda tid: None)
    r = client.post("/api/v1/audit/drill/start", json={"tenant_id": "t1"})
    assert r.status_code == 409
    assert ma._active_drills == {}


def test_product_comes_from_tenant_records(monkeypatch):
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = ("Recorded Product",)
    import shared.database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
    assert ma._get_product_for_tlc("t1", "TLC-1") == "Recorded Product"
    params = session.execute.call_args[0][1]
    assert params == {"tid": "t1", "tlc": "TLC-1"}
    assert session.close.called
