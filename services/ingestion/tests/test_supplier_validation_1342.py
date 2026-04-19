"""Coverage for app/supplier_validation.py — FSMA 204 supplier compliance scorer.

Target: 100% on the validation engine that runs 6 checks per supplier
(recent submission, portal status, email, CTE coverage, KDE, GLN) and
rolls them up into a tenant-level compliance report.

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import supplier_validation as sv
from app.supplier_validation import (
    SupplierValidationResult,
    TenantSupplierReport,
    ValidationCheck,
    _EMAIL_RE,
    _REQUIRED_CTE_TYPES,
    _build_report,
    _fetch_supplier_submissions,
    _fetch_suppliers,
    _reports_store,
    _validate_supplier,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store():
    _reports_store.clear()
    yield
    _reports_store.clear()


@pytest.fixture(autouse=True)
def _stub_tenant_settings(monkeypatch):
    """Neutralize get_tenant_data / set_tenant_data (used for persistence)."""
    monkeypatch.setattr(sv, "get_tenant_data", lambda tid, a, b: None)
    monkeypatch.setattr(sv, "set_tenant_data", lambda tid, a, b, d: True)


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_db(rows=None, raise_on_execute=False):
    session = MagicMock()
    if raise_on_execute:
        session.execute.side_effect = RuntimeError("boom")
    else:
        result = MagicMock()
        result.fetchall.return_value = rows or []
        session.execute.return_value = result
    return session


def _perfect_supplier():
    """A supplier that passes every check (score=100, status=compliant)."""
    now = datetime.now(timezone.utc)
    return {
        "id": "t1-sup-001",
        "name": "Perfect Co",
        "contact_email": "contact@perfect.com",
        "portal_link_id": "portal-xyz",
        "portal_status": "active",
        "submissions_count": 5,
        "last_submission": now.isoformat(),
        "compliance_status": "compliant",
        "missing_kdes": [],
        "products": ["Produce"],
    }


def _passing_submissions():
    """Submissions that cover produce CTEs with high KDE and GLN."""
    return [
        {"cte_type": "Growing", "kde_completeness": 95.0, "gln": "1234567890123"},
        {"cte_type": "receiving", "kde_completeness": 90.0, "gln": "1234567890123"},
        {"cte_type": "SHIPPING", "kde_completeness": 85.0, "gln": "1234567890123"},
    ]


# ---------------------------------------------------------------------------
# Pydantic models + module constants
# ---------------------------------------------------------------------------


class TestPydanticSurface:
    def test_validation_check_shape(self):
        c = ValidationCheck(name="x", passed=True, details="ok", severity="info")
        assert c.passed is True

    def test_supplier_validation_result_score_bounds(self):
        # Pydantic Field enforces ge=0, le=100
        with pytest.raises(ValueError):
            SupplierValidationResult(
                supplier_id="s", supplier_name="n", status="compliant",
                last_validated="x", score=101,
            )

    def test_supplier_validation_result_defaults(self):
        r = SupplierValidationResult(
            supplier_id="s", supplier_name="n", status="compliant",
            last_validated="x", score=85,
        )
        assert r.checks == []
        assert r.missing_requirements == []

    def test_tenant_supplier_report_defaults(self):
        r = TenantSupplierReport(
            tenant_id="t", total_suppliers=0, compliant_count=0,
            partial_count=0, non_compliant_count=0, overall_compliance_pct=0,
            generated_at="x",
        )
        assert r.suppliers == []


class TestEmailRegex:
    def test_valid_emails(self):
        assert _EMAIL_RE.match("a@b.com")
        assert _EMAIL_RE.match("alice.smith@company.co.uk")
        assert _EMAIL_RE.match("user+tag@example.org")

    @pytest.mark.parametrize("bad", [
        "", "no-at-sign.com", "a@b", "@b.com", "a@.com", "a b@c.com", "a@b c.com",
    ])
    def test_invalid_emails(self, bad):
        assert not _EMAIL_RE.match(bad)


class TestRequiredCteTypes:
    def test_has_default(self):
        assert _REQUIRED_CTE_TYPES["default"] == ["receiving", "shipping"]

    def test_produce_categories(self):
        assert "growing" in _REQUIRED_CTE_TYPES["produce"]

    def test_seafood_categories(self):
        assert "harvesting" in _REQUIRED_CTE_TYPES["seafood"]

    def test_dairy_categories(self):
        assert "transformation" in _REQUIRED_CTE_TYPES["dairy"]


# ---------------------------------------------------------------------------
# _fetch_suppliers
# ---------------------------------------------------------------------------


class TestFetchSuppliers:
    def test_returns_none_when_no_db(self, monkeypatch):
        monkeypatch.setattr(sv, "get_db_safe", lambda: None)
        assert _fetch_suppliers("t1") is None

    def test_maps_rows_with_json_fields(self, monkeypatch):
        session = _mock_db(rows=[
            ("s1", "Acme", "a@x.com", "pl-1", "active", 3,
             "2026-04-18T00:00:00+00:00", "compliant",
             '["kde1"]', '["Spinach"]'),
        ])
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        result = _fetch_suppliers("t1")
        assert len(result) == 1
        assert result[0]["id"] == "s1"
        assert result[0]["missing_kdes"] == ["kde1"]
        assert result[0]["products"] == ["Spinach"]

    def test_null_json_fields_become_empty(self, monkeypatch):
        session = _mock_db(rows=[
            ("s1", "A", "a@x.com", None, "active", 0, None, "unknown", None, None),
        ])
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        result = _fetch_suppliers("t1")
        assert result[0]["missing_kdes"] == []
        assert result[0]["products"] == []

    def test_exception_returns_none_and_closes(self, monkeypatch):
        session = _mock_db(raise_on_execute=True)
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        assert _fetch_suppliers("t1") is None
        session.close.assert_called_once()

    def test_tid_param(self, monkeypatch):
        session = _mock_db(rows=[])
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        _fetch_suppliers("tenant-xyz")
        _sql, params = session.execute.call_args[0]
        assert params == {"tid": "tenant-xyz"}


# ---------------------------------------------------------------------------
# _fetch_supplier_submissions
# ---------------------------------------------------------------------------


class TestFetchSupplierSubmissions:
    def test_returns_none_when_no_db(self, monkeypatch):
        monkeypatch.setattr(sv, "get_db_safe", lambda: None)
        assert _fetch_supplier_submissions("t1", "s1") is None

    def test_maps_rows(self, monkeypatch):
        session = _mock_db(rows=[
            ("shipping", 95.5, "1234567890123"),
            ("receiving", 80.0, None),
        ])
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        result = _fetch_supplier_submissions("t1", "s1")
        assert len(result) == 2
        assert result[0]["cte_type"] == "shipping"
        assert result[0]["kde_completeness"] == 95.5
        assert result[0]["gln"] == "1234567890123"

    def test_exception_returns_none_and_closes(self, monkeypatch):
        session = _mock_db(raise_on_execute=True)
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        assert _fetch_supplier_submissions("t1", "s1") is None
        session.close.assert_called_once()

    def test_tid_and_sid_params(self, monkeypatch):
        session = _mock_db(rows=[])
        monkeypatch.setattr(sv, "get_db_safe", lambda: session)
        _fetch_supplier_submissions("tenant-xyz", "sup-123")
        _sql, params = session.execute.call_args[0]
        assert params == {"tid": "tenant-xyz", "sid": "sup-123"}


# ---------------------------------------------------------------------------
# _validate_supplier — the scoring engine
# ---------------------------------------------------------------------------


class TestValidateSupplier:
    def test_perfect_supplier_scores_100(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 100
        assert result.status == "compliant"
        assert result.missing_requirements == []
        # All 6 checks present
        assert len(result.checks) == 6

    def test_stale_submission_fails_recent_check(self, monkeypatch):
        supp = _perfect_supplier()
        # 31 days ago
        supp["last_submission"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 70  # -30 for critical
        assert result.status == "partial"
        recent_check = next(c for c in result.checks if c.name == "recent_submission")
        assert recent_check.passed is False
        assert "No submission in 30+ days" in recent_check.details

    def test_no_last_submission_fails_recent_check(self, monkeypatch):
        supp = _perfect_supplier()
        supp["last_submission"] = None
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        recent_check = next(c for c in result.checks if c.name == "recent_submission")
        assert recent_check.passed is False

    def test_malformed_last_submission_treated_as_stale(self, monkeypatch):
        supp = _perfect_supplier()
        supp["last_submission"] = "not-a-date"
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        recent_check = next(c for c in result.checks if c.name == "recent_submission")
        assert recent_check.passed is False

    def test_z_suffix_timestamp_parsed(self, monkeypatch):
        supp = _perfect_supplier()
        # Use Z suffix (replaced with +00:00 in impl)
        supp["last_submission"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        recent_check = next(c for c in result.checks if c.name == "recent_submission")
        assert recent_check.passed is True

    def test_naive_timestamp_gets_utc_tzinfo(self, monkeypatch):
        supp = _perfect_supplier()
        # Naive datetime string
        supp["last_submission"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        recent_check = next(c for c in result.checks if c.name == "recent_submission")
        assert recent_check.passed is True

    def test_inactive_portal_fails_portal_check(self, monkeypatch):
        supp = _perfect_supplier()
        supp["portal_status"] = "expired"
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 70  # -30 critical
        portal_check = next(c for c in result.checks if c.name == "portal_status")
        assert portal_check.passed is False
        assert "expired" in portal_check.details

    def test_invalid_email_fails_warning(self, monkeypatch):
        supp = _perfect_supplier()
        supp["contact_email"] = "not-an-email"
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 90  # -10 warning
        email_check = next(c for c in result.checks if c.name == "valid_contact_email")
        assert email_check.passed is False

    def test_missing_email_fails(self, monkeypatch):
        supp = _perfect_supplier()
        supp["contact_email"] = ""
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        email_check = next(c for c in result.checks if c.name == "valid_contact_email")
        assert email_check.passed is False

    def test_no_submissions_fails_cte_coverage(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: None)
        result = _validate_supplier(supp, "t1")
        cte_check = next(c for c in result.checks if c.name == "cte_type_coverage")
        assert cte_check.passed is False

    def test_empty_submissions_fails_cte_coverage(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [])
        result = _validate_supplier(supp, "t1")
        cte_check = next(c for c in result.checks if c.name == "cte_type_coverage")
        assert cte_check.passed is False

    def test_partial_cte_coverage_fails(self, monkeypatch):
        supp = _perfect_supplier()
        # produce requires growing/receiving/shipping, only shipping submitted
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "shipping", "kde_completeness": 90.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        cte_check = next(c for c in result.checks if c.name == "cte_type_coverage")
        assert cte_check.passed is False
        assert "Missing CTE types" in cte_check.details

    def test_no_products_uses_default_cte_types(self, monkeypatch):
        supp = _perfect_supplier()
        supp["products"] = []
        # Default requires receiving + shipping
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "receiving", "kde_completeness": 90.0, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": 90.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        cte_check = next(c for c in result.checks if c.name == "cte_type_coverage")
        assert cte_check.passed is True

    def test_seafood_product_requires_harvesting(self, monkeypatch):
        supp = _perfect_supplier()
        supp["products"] = ["Seafood"]
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "harvesting", "kde_completeness": 90.0, "gln": "g1"},
            {"cte_type": "receiving", "kde_completeness": 90.0, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": 90.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        cte_check = next(c for c in result.checks if c.name == "cte_type_coverage")
        assert cte_check.passed is True

    def test_low_kde_fails(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": 50.0, "gln": "g1"},
            {"cte_type": "receiving", "kde_completeness": 60.0, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": 70.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        kde_check = next(c for c in result.checks if c.name == "kde_completeness")
        assert kde_check.passed is False
        assert "Average KDE completeness: 60.0%" in kde_check.details

    def test_kde_80_exactly_passes(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": 80.0, "gln": "g1"},
            {"cte_type": "receiving", "kde_completeness": 80.0, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": 80.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        kde_check = next(c for c in result.checks if c.name == "kde_completeness")
        assert kde_check.passed is True

    def test_no_kde_data_fails(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": None, "gln": "g1"},
            {"cte_type": "receiving", "kde_completeness": None, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": None, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        kde_check = next(c for c in result.checks if c.name == "kde_completeness")
        assert kde_check.passed is False
        assert "No KDE data available" in kde_check.details

    def test_malformed_kde_skipped(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": "not-a-number", "gln": "g1"},
            {"cte_type": "receiving", "kde_completeness": 90.0, "gln": "g1"},
            {"cte_type": "shipping", "kde_completeness": 90.0, "gln": "g1"},
        ])
        result = _validate_supplier(supp, "t1")
        kde_check = next(c for c in result.checks if c.name == "kde_completeness")
        # Only two valid scores averaged -> 90
        assert kde_check.passed is True

    def test_no_gln_info_deduction(self, monkeypatch):
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": 95.0, "gln": None},
            {"cte_type": "receiving", "kde_completeness": 95.0, "gln": None},
            {"cte_type": "shipping", "kde_completeness": 95.0, "gln": None},
        ])
        result = _validate_supplier(supp, "t1")
        gln_check = next(c for c in result.checks if c.name == "valid_gln")
        assert gln_check.passed is False
        assert result.score == 95  # -5 info

    def test_score_floor_at_zero(self, monkeypatch):
        # Every check fails -> 100 - 30 - 30 - 10 - 10 - 10 - 5 = 5
        # But also test the max(0, ...) floor with even worse
        supp = {
            "id": "s1", "name": "Bad Co",
            "contact_email": "bad",
            "portal_status": "expired",
            "last_submission": None,
            "products": [],
            "missing_kdes": [],
        }
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: None)
        result = _validate_supplier(supp, "t1")
        assert result.score >= 0
        assert result.status == "non_compliant"

    def test_partial_status_50_to_79(self, monkeypatch):
        # Drop a critical and a warning -> 100 - 30 - 10 = 60
        supp = _perfect_supplier()
        supp["portal_status"] = "expired"
        supp["contact_email"] = "bad"
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 60
        assert result.status == "partial"

    def test_non_compliant_status_below_50(self, monkeypatch):
        # Both criticals fail + a warning = 100 - 30 - 30 - 10 = 30
        supp = _perfect_supplier()
        supp["portal_status"] = "expired"
        supp["last_submission"] = None
        supp["contact_email"] = "bad"
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        result = _validate_supplier(supp, "t1")
        assert result.score == 30
        assert result.status == "non_compliant"

    def test_compliant_status_80_and_up(self, monkeypatch):
        # Only GLN missing -> 100 - 5 = 95
        supp = _perfect_supplier()
        monkeypatch.setattr(sv, "_fetch_supplier_submissions", lambda tid, sid: [
            {"cte_type": "growing", "kde_completeness": 95.0, "gln": None},
            {"cte_type": "receiving", "kde_completeness": 95.0, "gln": None},
            {"cte_type": "shipping", "kde_completeness": 95.0, "gln": None},
        ])
        result = _validate_supplier(supp, "t1")
        assert result.score == 95
        assert result.status == "compliant"


# ---------------------------------------------------------------------------
# _build_report
# ---------------------------------------------------------------------------


class TestBuildReport:
    def _result(self, status, score=80):
        return SupplierValidationResult(
            supplier_id="s", supplier_name="n", status=status,
            last_validated="x", score=score,
        )

    def test_empty_results_zero_pct(self):
        report = _build_report("t1", [])
        assert report.total_suppliers == 0
        assert report.overall_compliance_pct == 0.0

    def test_counts_by_status(self):
        results = [
            self._result("compliant"),
            self._result("compliant"),
            self._result("partial"),
            self._result("non_compliant"),
        ]
        report = _build_report("t1", results)
        assert report.total_suppliers == 4
        assert report.compliant_count == 2
        assert report.partial_count == 1
        assert report.non_compliant_count == 1
        assert report.overall_compliance_pct == 50.0  # 2/4

    def test_cached_in_reports_store(self):
        results = [self._result("compliant")]
        report = _build_report("t1", results)
        assert _reports_store["t1"] is report

    def test_write_through_exception_swallowed(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("db-write-failed")
        monkeypatch.setattr(sv, "set_tenant_data", boom)
        # Should not raise
        report = _build_report("t1", [self._result("compliant")])
        assert report.total_suppliers == 1

    def test_includes_generated_at(self):
        report = _build_report("t1", [])
        # Parseable ISO timestamp
        datetime.fromisoformat(report.generated_at)


# ---------------------------------------------------------------------------
# POST /{tenant_id}/validate
# ---------------------------------------------------------------------------


class TestValidateAllEndpoint:
    def test_happy_path(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [_perfect_supplier()])
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        resp = client.post("/api/v1/suppliers/validation/t1/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["total_suppliers"] == 1
        assert body["compliant_count"] == 1
        assert body["overall_compliance_pct"] == 100.0

    def test_db_unavailable_returns_empty_report(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: None)
        resp = client.post("/api/v1/suppliers/validation/t1/validate")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 0

    def test_no_suppliers_returns_empty_report(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [])
        resp = client.post("/api/v1/suppliers/validation/t1/validate")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 0


# ---------------------------------------------------------------------------
# POST /{tenant_id}/{supplier_id}/validate
# ---------------------------------------------------------------------------


class TestValidateSingleEndpoint:
    def test_found_supplier(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [_perfect_supplier()])
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        resp = client.post("/api/v1/suppliers/validation/t1/t1-sup-001/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["supplier_id"] == "t1-sup-001"
        assert body["status"] == "compliant"
        assert body["score"] == 100

    def test_supplier_not_found_returns_placeholder(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [])
        resp = client.post("/api/v1/suppliers/validation/t1/missing/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["supplier_id"] == "missing"
        assert body["supplier_name"] == "Unknown"
        assert body["status"] == "non_compliant"
        assert body["score"] == 0
        assert body["missing_requirements"] == ["Supplier must be registered"]
        # Contains the supplier_exists critical failure
        assert any(c["name"] == "supplier_exists" for c in body["checks"])

    def test_db_unavailable_returns_placeholder(self, client, monkeypatch):
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: None)
        resp = client.post("/api/v1/suppliers/validation/t1/any/validate")
        assert resp.status_code == 200
        assert resp.json()["supplier_name"] == "Unknown"


# ---------------------------------------------------------------------------
# GET /{tenant_id}/report
# ---------------------------------------------------------------------------


class TestGetReportEndpoint:
    def test_cached_report_returned(self, client, monkeypatch):
        # Pre-populate the in-memory store
        report = TenantSupplierReport(
            tenant_id="t1", total_suppliers=1, compliant_count=1,
            partial_count=0, non_compliant_count=0,
            overall_compliance_pct=100.0, generated_at="2026-04-18T00:00:00+00:00",
        )
        _reports_store["t1"] = report
        resp = client.get("/api/v1/suppliers/validation/t1/report")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 1

    def test_no_cache_falls_back_to_db(self, client, monkeypatch):
        # DB returns a saved report
        db_data = TenantSupplierReport(
            tenant_id="t1", total_suppliers=2, compliant_count=2,
            partial_count=0, non_compliant_count=0,
            overall_compliance_pct=100.0, generated_at="2026-04-18T00:00:00+00:00",
        ).model_dump()
        monkeypatch.setattr(sv, "get_tenant_data", lambda tid, a, b: db_data)
        resp = client.get("/api/v1/suppliers/validation/t1/report")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 2
        # Repopulates cache
        assert "t1" in _reports_store

    def test_db_read_exception_swallowed_generates_fresh(self, client, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("db-failed")
        monkeypatch.setattr(sv, "get_tenant_data", boom)
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [])
        resp = client.get("/api/v1/suppliers/validation/t1/report")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 0

    def test_no_cache_no_db_data_generates_fresh_from_suppliers(self, client, monkeypatch):
        monkeypatch.setattr(sv, "get_tenant_data", lambda tid, a, b: None)
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: [_perfect_supplier()])
        monkeypatch.setattr(sv, "_fetch_supplier_submissions",
                            lambda tid, sid: _passing_submissions())
        resp = client.get("/api/v1/suppliers/validation/t1/report")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 1

    def test_no_cache_suppliers_db_none_generates_empty(self, client, monkeypatch):
        monkeypatch.setattr(sv, "get_tenant_data", lambda tid, a, b: None)
        monkeypatch.setattr(sv, "_fetch_suppliers", lambda tid: None)
        resp = client.get("/api/v1/suppliers/validation/t1/report")
        assert resp.status_code == 200
        assert resp.json()["total_suppliers"] == 0


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix_and_tags(self):
        assert router.prefix == "/api/v1/suppliers/validation"
        assert "Supplier Validation" in router.tags

    def test_paths_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/suppliers/validation/{tenant_id}/validate" in paths
        assert "/api/v1/suppliers/validation/{tenant_id}/{supplier_id}/validate" in paths
        assert "/api/v1/suppliers/validation/{tenant_id}/report" in paths
