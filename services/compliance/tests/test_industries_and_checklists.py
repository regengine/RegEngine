"""Tests for industry listing and compliance checklist endpoints.

Covers:
- GET /industries
- GET /checklists (with and without industry filter)
- GET /checklists/{checklist_id}
- 404 handling for missing checklists
- Auth requirements
"""

import sys
import os
from pathlib import Path
from uuid import uuid4

service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == "app" or key.startswith("app.") or key == "main"]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REGENGINE_ENV", "test")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-industries")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-industries")

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

API_KEY = os.environ["AUTH_TEST_BYPASS_TOKEN"]


def _headers() -> dict:
    return {"X-RegEngine-API-Key": API_KEY}


# ─── Industries ──────────────────────────────────────────────────────────


class TestIndustries:
    def test_list_industries_returns_all_five(self):
        resp = client.get("/industries", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["industries"]) == 5

    def test_each_industry_has_required_fields(self):
        resp = client.get("/industries", headers=_headers())
        for ind in resp.json()["industries"]:
            assert "id" in ind
            assert "name" in ind
            assert isinstance(ind["name"], str)
            assert len(ind["name"]) > 0

    def test_known_industry_names_present(self):
        resp = client.get("/industries", headers=_headers())
        names = [i["name"].lower() for i in resp.json()["industries"]]
        # At least these should exist based on the FSMA rules
        assert any("produce" in n for n in names)
        assert any("seafood" in n for n in names)

    def test_industries_requires_api_key(self):
        resp = client.get("/industries")
        assert resp.status_code in (401, 403, 422)


# ─── Checklists ──────────────────────────────────────────────────────────


class TestChecklists:
    def test_list_all_checklists(self):
        resp = client.get("/checklists", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 5
        assert len(body["checklists"]) == body["total"]

    def test_filter_checklists_by_industry(self):
        # First get an industry name
        ind_resp = client.get("/industries", headers=_headers())
        first_industry = ind_resp.json()["industries"][0]["name"]

        resp = client.get(
            "/checklists",
            params={"industry": first_industry},
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        for cl in body["checklists"]:
            assert cl["industry"].lower() == first_industry.lower()

    def test_filter_by_nonexistent_industry_returns_empty(self):
        resp = client.get(
            "/checklists",
            params={"industry": "nonexistent-industry-xyz"},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["checklists"] == []

    def test_get_checklist_by_id(self):
        # Get the list first
        list_resp = client.get("/checklists", headers=_headers())
        first_id = list_resp.json()["checklists"][0]["id"]

        resp = client.get(f"/checklists/{first_id}", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == first_id
        assert "requirements" in body
        assert "items" in body

    def test_get_checklist_not_found(self):
        resp = client.get("/checklists/nonexistent-id-999", headers=_headers())
        assert resp.status_code == 404

    def test_checklist_requirements_have_structure(self):
        list_resp = client.get("/checklists", headers=_headers())
        first_id = list_resp.json()["checklists"][0]["id"]
        resp = client.get(f"/checklists/{first_id}", headers=_headers())
        body = resp.json()

        assert len(body["requirements"]) > 0
        for req in body["requirements"]:
            assert "id" in req
            assert "title" in req
            assert "description" in req
            # category and priority may be present
            if req.get("priority"):
                assert req["priority"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_checklists_requires_api_key(self):
        resp = client.get("/checklists")
        assert resp.status_code in (401, 403, 422)
