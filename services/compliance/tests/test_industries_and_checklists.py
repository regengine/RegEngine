"""Tests for industry listing and compliance checklist endpoints.

Covers:
- GET /industries
- GET /checklists (with and without industry filter)
- GET /checklists/{checklist_id}
- 404 handling for missing checklists
- Auth requirements
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == "app" or key.startswith("services.compliance.app.") or key == "main"]
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["REGENGINE_ENV"] = "test"
os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token-compliance"
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


# ─── Industry filter: ids as well as display names (#2851) ───────────────


class TestIndustryFilterAcceptsIds:
    """``GET /industries`` publishes an ``id`` per industry, and a client
    naturally feeds that id straight back into ``GET /checklists?industry=``.

    The filter used to compare only against ``checklists[].industry``, which
    holds the *display name* — so ``?industry=fresh-produce`` matched nothing
    and returned ``{"checklists": [], "total": 0}``. That is a 200, not an
    error, so it reads as "this industry has no compliance requirements".
    Three of the five published ids behaved that way.

    ``TestChecklists.test_filter_checklists_by_industry`` above passes the
    display *name*, which is why this went unnoticed.
    """

    def test_every_published_industry_id_returns_its_checklists(self):
        ind_resp = client.get("/industries", headers=_headers())
        assert ind_resp.status_code == 200
        industries = ind_resp.json()["industries"]
        assert industries, "no industries published — nothing to filter by"

        empty = []
        for ind in industries:
            resp = client.get(
                "/checklists", params={"industry": ind["id"]}, headers=_headers()
            )
            assert resp.status_code == 200
            if resp.json()["total"] == 0:
                empty.append(ind["id"])

        assert not empty, (
            f"GET /checklists?industry=<id> returned an empty list for ids "
            f"published by GET /industries: {empty}. A caller cannot tell this "
            f"apart from 'no requirements exist for this industry' (#2851)."
        )

    def test_id_and_display_name_agree(self):
        ind_resp = client.get("/industries", headers=_headers())
        for ind in ind_resp.json()["industries"]:
            by_id = client.get(
                "/checklists", params={"industry": ind["id"]}, headers=_headers()
            ).json()
            by_name = client.get(
                "/checklists", params={"industry": ind["name"]}, headers=_headers()
            ).json()
            assert [c["id"] for c in by_id["checklists"]] == [
                c["id"] for c in by_name["checklists"]
            ], f"id and display name disagree for industry {ind['id']!r}"

    def test_unknown_industry_still_returns_empty(self):
        """The alias table must not turn an unknown industry into a match."""
        resp = client.get(
            "/checklists",
            params={"industry": "not-a-real-industry-2851"},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
