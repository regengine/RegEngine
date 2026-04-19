"""Coverage for app/onboarding.py — 5-step guided onboarding flow.

Target: 100% on the router that tracks tenants from company profile to
first CTE. Covers Pydantic surface, obligation seeding, step definitions,
and both endpoint paths with DB / memory fallback / concurrency shape.

Issue: #1342
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import onboarding as ob
from app.onboarding import (
    ONBOARDING_STEPS,
    OnboardingCTE,
    OnboardingFacility,
    OnboardingProduct,
    OnboardingProfile,
    OnboardingProgress,
    _db_get_onboarding,
    _db_save_onboarding,
    _onboarding_store,
    _seed_obligations_if_needed,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store():
    _onboarding_store.clear()
    yield
    _onboarding_store.clear()


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class _FakeJsonbStore:
    def __init__(self):
        self.data: dict[tuple, dict] = {}
        self.write_fail_for: set[str] = set()
        self.get_calls: list[tuple] = []
        self.set_calls: list[tuple] = []

    def get(self, tenant_id, table, col):
        self.get_calls.append((tenant_id, table, col))
        return self.data.get((tenant_id, table, col))

    def set(self, tenant_id, table, col, val) -> bool:
        self.set_calls.append((tenant_id, table, col, dict(val)))
        if tenant_id in self.write_fail_for:
            return False
        self.data[(tenant_id, table, col)] = val
        return True


@pytest.fixture
def fake_jsonb(monkeypatch):
    store = _FakeJsonbStore()
    monkeypatch.setattr(ob, "get_jsonb", store.get)
    monkeypatch.setattr(ob, "set_jsonb", store.set)
    return store


@pytest.fixture
def no_seed(monkeypatch):
    """Replace obligation seeding with a no-op so step completion doesn't hit DB."""
    calls = []
    def _noop(tid):
        calls.append(tid)
    monkeypatch.setattr(ob, "_seed_obligations_if_needed", _noop)
    return calls


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_onboarding_profile(self):
        p = OnboardingProfile(
            company_name="Acme", company_type="grower",
            contact_name="Alice", contact_email="a@x.com",
        )
        assert p.company_type == "grower"

    def test_onboarding_facility_optional_gln(self):
        f = OnboardingFacility(facility_name="Main", address="123 Main")
        assert f.gln is None

    def test_onboarding_facility_with_gln(self):
        f = OnboardingFacility(facility_name="Main", address="123 Main", gln="1234567890123")
        assert f.gln == "1234567890123"

    def test_onboarding_product(self):
        p = OnboardingProduct(product_name="Spinach", product_category="Leafy Greens")
        assert p.product_category == "Leafy Greens"

    def test_onboarding_cte_defaults(self):
        c = OnboardingCTE(tlc="LOT-1", quantity=10, ship_to="B")
        assert c.cte_type == "shipping"
        assert c.unit == "cases"

    def test_onboarding_cte_custom(self):
        c = OnboardingCTE(cte_type="cooling", tlc="LOT-1", quantity=5, unit="lbs", ship_to="Dest")
        assert c.cte_type == "cooling"
        assert c.unit == "lbs"

    def test_onboarding_progress(self):
        p = OnboardingProgress(
            tenant_id="t1", current_step=3,
            completed_steps=["company_profile", "first_facility"],
            total_steps=5, percent_complete=40, steps=ONBOARDING_STEPS,
            started_at="2026-04-18T00:00:00+00:00",
        )
        assert p.first_cte_at is None
        assert p.time_to_first_cte is None


# ---------------------------------------------------------------------------
# ONBOARDING_STEPS catalog
# ---------------------------------------------------------------------------


class TestOnboardingStepsCatalog:
    def test_five_steps_defined(self):
        assert len(ONBOARDING_STEPS) == 5

    def test_step_ids_in_order(self):
        ids = [s["id"] for s in ONBOARDING_STEPS]
        assert ids == [
            "company_profile", "first_facility", "first_product",
            "first_cte", "verify_chain",
        ]

    def test_step_numbers_1_to_5(self):
        nums = [s["step"] for s in ONBOARDING_STEPS]
        assert nums == [1, 2, 3, 4, 5]

    def test_every_step_has_required_keys(self):
        for s in ONBOARDING_STEPS:
            assert "step" in s and "id" in s and "title" in s
            assert "description" in s and "estimated_time" in s


# ---------------------------------------------------------------------------
# _seed_obligations_if_needed
# ---------------------------------------------------------------------------


class TestSeedObligations:
    def test_happy_path_executes_and_commits(self, monkeypatch):
        session = MagicMock()
        session.execute = MagicMock()
        session.commit = MagicMock()
        session.close = MagicMock()

        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: session)

        _seed_obligations_if_needed("tenant-abc")

        session.execute.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()
        _sql, params = session.execute.call_args[0]
        assert params == {"tid": "tenant-abc"}

    def test_close_called_on_execute_failure(self, monkeypatch):
        session = MagicMock()
        session.execute.side_effect = RuntimeError("boom")
        session.close = MagicMock()

        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: session)

        # Exception caught by outer try/except — function should not raise
        _seed_obligations_if_needed("tenant-abc")

        session.close.assert_called_once()

    def test_outer_exception_swallowed(self, monkeypatch):
        # Make SessionLocal raise — caught by outer except
        import shared.database as shared_db

        def boom():
            raise RuntimeError("session-local-broken")

        monkeypatch.setattr(shared_db, "SessionLocal", boom)
        _seed_obligations_if_needed("tenant-abc")  # should not raise


# ---------------------------------------------------------------------------
# _db_get/save_onboarding
# ---------------------------------------------------------------------------


class TestDbHelpers:
    def test_get_delegates_to_jsonb_helper(self, fake_jsonb):
        _db_get_onboarding("t1")
        assert fake_jsonb.get_calls == [("t1", "tenant_onboarding", "state")]

    def test_get_returns_stored_value(self, fake_jsonb):
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {"current_step": 2}
        assert _db_get_onboarding("t1") == {"current_step": 2}

    def test_get_missing_returns_none(self, fake_jsonb):
        assert _db_get_onboarding("missing") is None

    def test_save_returns_true(self, fake_jsonb):
        assert _db_save_onboarding("t1", {"x": 1}) is True
        assert fake_jsonb.data[("t1", "tenant_onboarding", "state")] == {"x": 1}

    def test_save_returns_false_on_write_failure(self, fake_jsonb):
        fake_jsonb.write_fail_for.add("t1")
        assert _db_save_onboarding("t1", {"x": 1}) is False


# ---------------------------------------------------------------------------
# GET /steps
# ---------------------------------------------------------------------------


class TestGetStepsEndpoint:
    def test_returns_steps_and_time_estimate(self, client):
        resp = client.get("/api/v1/onboarding/steps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_estimated_time"] == "5 min"
        assert len(body["steps"]) == 5


# ---------------------------------------------------------------------------
# GET /{tenant_id}/progress
# ---------------------------------------------------------------------------


class TestGetProgressEndpoint:
    def test_db_hit_caches_state_and_returns(self, client, fake_jsonb):
        started = "2026-04-18T00:00:00+00:00"
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {
            "current_step": 3,
            "completed_steps": ["company_profile", "first_facility"],
            "started_at": started,
            "first_cte_at": None,
        }
        resp = client.get("/api/v1/onboarding/t1/progress")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["current_step"] == 3
        assert body["percent_complete"] == 40  # 2 of 5
        assert body["total_steps"] == 5
        assert body["first_cte_at"] is None
        assert body["time_to_first_cte"] is None
        assert "t1" in _onboarding_store  # cached

    def test_db_miss_initializes_default_progress(self, client, fake_jsonb):
        resp = client.get("/api/v1/onboarding/new-tenant/progress")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_step"] == 1
        assert body["completed_steps"] == []
        assert body["percent_complete"] == 0

    def test_db_miss_uses_memory_when_present(self, client, fake_jsonb):
        _onboarding_store["t1"] = {
            "current_step": 4,
            "completed_steps": ["company_profile", "first_facility", "first_product"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.get("/api/v1/onboarding/t1/progress")
        assert resp.json()["current_step"] == 4
        assert resp.json()["percent_complete"] == 60  # 3 of 5

    def test_time_to_first_cte_formatted_minutes(self, client, fake_jsonb):
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {
            "current_step": 5,
            "completed_steps": ["company_profile", "first_facility", "first_product", "first_cte"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": "2026-04-18T00:03:30+00:00",
        }
        resp = client.get("/api/v1/onboarding/t1/progress")
        assert resp.json()["time_to_first_cte"] == "3 min"

    def test_time_to_first_cte_under_one_minute(self, client, fake_jsonb):
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {
            "current_step": 5,
            "completed_steps": ["company_profile", "first_cte"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": "2026-04-18T00:00:30+00:00",  # 30 seconds
        }
        resp = client.get("/api/v1/onboarding/t1/progress")
        assert resp.json()["time_to_first_cte"] == "< 1 min"

    def test_100_percent_when_all_completed(self, client, fake_jsonb):
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {
            "current_step": 5,
            "completed_steps": [s["id"] for s in ONBOARDING_STEPS],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.get("/api/v1/onboarding/t1/progress")
        assert resp.json()["percent_complete"] == 100


# ---------------------------------------------------------------------------
# POST /{tenant_id}/step/{step_id}
# ---------------------------------------------------------------------------


class TestCompleteStepEndpoint:
    def test_complete_first_step_seeds_obligations(self, client, fake_jsonb, no_seed):
        resp = client.post("/api/v1/onboarding/t1/step/company_profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["step_id"] == "company_profile"
        assert body["completed"] is True
        assert body["onboarding_complete"] is False
        assert body["next_step"]["id"] == "first_facility"
        # Obligation seeding was triggered for the company_profile step
        assert no_seed == ["t1"]

    def test_complete_non_first_step_does_not_seed_obligations(self, client, fake_jsonb, no_seed):
        _onboarding_store["t1"] = {
            "current_step": 2,
            "completed_steps": ["company_profile"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.post("/api/v1/onboarding/t1/step/first_facility")
        assert resp.status_code == 200
        assert resp.json()["next_step"]["id"] == "first_product"
        assert no_seed == []  # not called again

    def test_complete_step_idempotent_does_not_duplicate(self, client, fake_jsonb, no_seed):
        client.post("/api/v1/onboarding/t1/step/company_profile")
        client.post("/api/v1/onboarding/t1/step/company_profile")
        state = fake_jsonb.data[("t1", "tenant_onboarding", "state")]
        assert state["completed_steps"].count("company_profile") == 1

    def test_complete_first_cte_sets_first_cte_at(self, client, fake_jsonb, no_seed):
        _onboarding_store["t1"] = {
            "current_step": 4,
            "completed_steps": ["company_profile", "first_facility", "first_product"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.post("/api/v1/onboarding/t1/step/first_cte")
        assert resp.status_code == 200
        state = fake_jsonb.data[("t1", "tenant_onboarding", "state")]
        assert state["first_cte_at"] is not None

    def test_complete_first_cte_does_not_overwrite_existing(self, client, fake_jsonb, no_seed):
        original = "2026-04-18T00:01:00+00:00"
        _onboarding_store["t1"] = {
            "current_step": 5,
            "completed_steps": ["company_profile", "first_facility", "first_product", "first_cte"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": original,
        }
        client.post("/api/v1/onboarding/t1/step/first_cte")
        state = fake_jsonb.data[("t1", "tenant_onboarding", "state")]
        assert state["first_cte_at"] == original

    def test_complete_last_step_signals_onboarding_complete(self, client, fake_jsonb, no_seed):
        _onboarding_store["t1"] = {
            "current_step": 5,
            "completed_steps": ["company_profile", "first_facility", "first_product", "first_cte"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": "2026-04-18T00:02:00+00:00",
        }
        resp = client.post("/api/v1/onboarding/t1/step/verify_chain")
        body = resp.json()
        assert body["onboarding_complete"] is True
        # current_step capped at total, so next_step exists (the 5th one)
        # but since current_step == len after cap, result depends on last step:
        # state["current_step"] = min(5, 5) = 5, so 5 <= 5 -> next_step is ONBOARDING_STEPS[4]
        assert body["next_step"]["id"] == "verify_chain"

    def test_complete_current_step_cap_at_total(self, client, fake_jsonb, no_seed):
        # Complete the last step; current_step caps at len
        _onboarding_store["t1"] = {
            "current_step": 5,
            "completed_steps": [],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        client.post("/api/v1/onboarding/t1/step/verify_chain")
        state = fake_jsonb.data[("t1", "tenant_onboarding", "state")]
        assert state["current_step"] == 5

    def test_complete_unknown_step_id_no_advance(self, client, fake_jsonb, no_seed):
        _onboarding_store["t1"] = {
            "current_step": 2,
            "completed_steps": ["company_profile"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.post("/api/v1/onboarding/t1/step/mystery_step")
        assert resp.status_code == 200
        state = fake_jsonb.data[("t1", "tenant_onboarding", "state")]
        assert state["current_step"] == 2  # unchanged
        assert "mystery_step" in state["completed_steps"]  # still appended

    def test_complete_step_uses_db_state_when_available(self, client, fake_jsonb, no_seed):
        fake_jsonb.data[("t1", "tenant_onboarding", "state")] = {
            "current_step": 3,
            "completed_steps": ["company_profile", "first_facility"],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.post("/api/v1/onboarding/t1/step/first_product")
        assert resp.status_code == 200
        body = resp.json()
        assert body["next_step"]["id"] == "first_cte"

    def test_complete_step_memory_fallback_on_db_write_failure(self, client, fake_jsonb, no_seed):
        fake_jsonb.write_fail_for.add("t1")
        resp = client.post("/api/v1/onboarding/t1/step/company_profile")
        assert resp.status_code == 200
        # Memory cache reflects the change
        assert "company_profile" in _onboarding_store["t1"]["completed_steps"]

    def test_complete_next_step_is_none_when_past_last(self, client, fake_jsonb, no_seed):
        # Force current_step past total via memory seed
        _onboarding_store["t1"] = {
            "current_step": 10,  # out of bounds
            "completed_steps": [],
            "started_at": "2026-04-18T00:00:00+00:00",
            "first_cte_at": None,
        }
        resp = client.post("/api/v1/onboarding/t1/step/mystery")
        assert resp.status_code == 200
        assert resp.json()["next_step"] is None


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix_and_tags(self):
        assert router.prefix == "/api/v1/onboarding"
        assert "Onboarding" in router.tags

    def test_paths_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/onboarding/steps" in paths
        assert "/api/v1/onboarding/{tenant_id}/progress" in paths
        assert "/api/v1/onboarding/{tenant_id}/step/{step_id}" in paths
