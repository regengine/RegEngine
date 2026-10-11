"""Deep-QA gap tests for the compliance service.

- Part 1: unit tests for the /validate mapping helpers (app/routes.py).
- Part 2: endpoint robustness (industry filter, cte gate, checklist_id).
- Part 3: unit tests for the snapshot seal/render helpers (app/snapshots.py).
- Part 4: known unfixed integrity gaps, marked xfail(strict=True).

Fast and deterministic: no sleeps, no network, SQLite only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
_REPO_ROOT = _SERVICES_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for _key in [k for k in sys.modules if k == "app" or k.startswith("app.") or k == "main"]:
    del sys.modules[_key]

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["REGENGINE_ENV"] = "test"
os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token-compliance"
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-qa-gaps-sixteen")

import pytest
from app.routes import (  # noqa: E402
    _canonicalize_ftl_commodity,
    _config_to_engine_event,
    _is_ftl_commodity,
    _summary_to_validate_response,
    _validation_issue,
)

# ---------------------------------------------------------------------------
# Part 1a: FTL canonicalization
# ---------------------------------------------------------------------------


class TestCanonicalizeFtlCommodity:
    def test_underscores_dashes_and_case_fold(self):
        assert _canonicalize_ftl_commodity("Leafy_Greens") == "leafy greens"
        assert _canonicalize_ftl_commodity("LEAFY-GREENS") == "leafy greens"
        assert _canonicalize_ftl_commodity("  leafy   greens  ") == "leafy greens"

    def test_canonical_forms_are_ftl_members(self):
        assert _is_ftl_commodity("leafy_greens")
        assert _is_ftl_commodity("Leafy Greens")
        assert not _is_ftl_commodity("bananas")
        assert not _is_ftl_commodity("")

    def test_validation_issue_shape(self):
        issue = _validation_issue("cte_type", "INVALID_CTE_TYPE", "bad type")
        assert issue == {"path": "cte_type", "code": "INVALID_CTE_TYPE", "message": "bad type"}
        with_suggestion = _validation_issue("c", "X", "m", suggestion="fix it")
        assert with_suggestion["suggestion"] == "fix it"


# ---------------------------------------------------------------------------
# Part 1b: config -> engine event mapping
# ---------------------------------------------------------------------------


class TestConfigToEngineEvent:
    def test_aliases_land_on_engine_top_level_fields(self):
        event = _config_to_engine_event(
            {"cte_type": "SHIPPING", "tlc": "TLC-1", "product_description": "Lettuce"},
            "leafy greens",
        )
        assert event["event_type"] == "shipping"
        assert event["traceability_lot_code"] == "TLC-1"
        assert event["product_reference"] == "Lettuce"
        assert event["ftl_category"] == "leafy greens"
        assert "tlc" not in event["kdes"]
        assert event["event_id"].startswith("validate:")

    def test_flat_kdes_nest_under_kdes(self):
        event = _config_to_engine_event(
            {"cte_type": "SHIPPING", "harvest_date": "2026-01-01"},
            "leafy greens",
        )
        assert event["kdes"] == {"harvest_date": "2026-01-01"}

    def test_nested_kdes_preserved_and_input_not_mutated(self):
        config = {"cte_type": "SHIPPING", "kdes": {"lot_size_unit": "cases"}}
        event = _config_to_engine_event(config, "leafy greens")
        assert event["kdes"] == {"lot_size_unit": "cases"}
        assert config == {"cte_type": "SHIPPING", "kdes": {"lot_size_unit": "cases"}}

    def test_nested_kde_wins_over_conflicting_flat_key(self):
        """Current precedence: nested ``kdes`` wins, flat duplicate dropped."""
        event = _config_to_engine_event(
            {"cte_type": "SHIPPING", "kdes": {"x": "nested"}, "x": "flat"},
            "leafy greens",
        )
        assert event["kdes"]["x"] == "nested"

    def test_engine_top_level_fields_pass_through(self):
        event = _config_to_engine_event(
            {"cte_type": "RECEIVING", "from_entity_reference": "SUP-1"},
            "leafy greens",
        )
        assert event["from_entity_reference"] == "SUP-1"
        assert "from_entity_reference" not in event["kdes"]

    def test_non_dict_kdes_ignored(self):
        event = _config_to_engine_event(
            {"cte_type": "SHIPPING", "kdes": "not-a-dict"},
            "leafy greens",
        )
        assert event["kdes"] == {}

    def test_event_ids_unique(self):
        config = {"cte_type": "SHIPPING"}
        first = _config_to_engine_event(config, "leafy greens")["event_id"]
        second = _config_to_engine_event(config, "leafy greens")["event_id"]
        assert first != second


# ---------------------------------------------------------------------------
# Part 1c: engine summary -> /validate response
# ---------------------------------------------------------------------------

from shared.rules.types import EvaluationSummary, RuleEvaluationResult  # noqa: E402


def _result(result: str, **overrides) -> RuleEvaluationResult:
    base = {
        "rule_id": "r-1",
        "rule_title": "TLC required",
        "severity": "critical",
        "result": result,
        "why_failed": "shipping event missing traceability_lot_code",
        "evidence_fields_inspected": [{"field": "traceability_lot_code"}],
        "remediation_suggestion": "Record the TLC",
        "citation_reference": "21 CFR 1.1345",
    }
    base.update(overrides)
    return RuleEvaluationResult(**base)


def _summary(results, total=None, reason=None) -> EvaluationSummary:
    failed = sum(1 for r in results if r.result == "fail")
    warned = sum(1 for r in results if r.result == "warn")
    errored = sum(1 for r in results if r.result == "error")
    return EvaluationSummary(
        event_id="e-1",
        total_rules=len(results) if total is None else total,
        passed=sum(1 for r in results if r.result == "pass"),
        failed=failed,
        warned=warned,
        errored=errored,
        no_verdict_reason=reason,
        results=list(results),
    )


class TestSummaryToValidateResponse:
    def test_all_pass_is_valid(self):
        resp = _summary_to_validate_response(_summary([_result("pass")]), "leafy greens", strict=False)
        assert resp.valid is True
        assert resp.errors == []
        assert resp.rules_evaluated == 1
        assert resp.no_verdict_reason is None

    def test_fail_maps_to_rule_failed_with_provenance(self):
        resp = _summary_to_validate_response(_summary([_result("fail")]), "leafy greens", strict=False)
        assert resp.valid is False
        (issue,) = resp.errors
        assert issue["code"] == "RULE_FAILED"
        assert issue["path"] == "traceability_lot_code"
        assert issue["rule_id"] == "r-1"
        assert issue["severity"] == "critical"
        assert issue["citation_reference"] == "21 CFR 1.1345"
        assert issue["suggestion"] == "Record the TLC"

    def test_error_result_maps_to_evaluation_error(self):
        resp = _summary_to_validate_response(_summary([_result("error")]), "leafy greens", strict=False)
        assert resp.valid is False
        assert resp.errors[0]["code"] == "RULE_EVALUATION_ERROR"

    def test_issue_without_evidence_defaults_to_config_path(self):
        result = _result("fail", evidence_fields_inspected=[{}, {"field": ""}])
        resp = _summary_to_validate_response(_summary([result]), "leafy greens", strict=False)
        assert resp.errors[0]["path"] == "config"

    def test_missing_title_falls_back_to_rule_title_and_no_suggestion_key(self):
        result = _result("fail", why_failed=None, remediation_suggestion=None, citation_reference=None)
        resp = _summary_to_validate_response(_summary([result]), "leafy greens", strict=False)
        assert resp.errors[0]["message"] == "TLC required"
        assert "suggestion" not in resp.errors[0]
        assert "citation_reference" not in resp.errors[0]

    def test_warn_stays_warning_outside_strict_mode(self):
        resp = _summary_to_validate_response(_summary([_result("warn")]), "leafy greens", strict=False)
        assert resp.valid is True
        assert resp.errors == []
        assert resp.warnings[0]["code"] == "RULE_WARNING"

    def test_warn_escalates_in_strict_mode(self):
        resp = _summary_to_validate_response(_summary([_result("warn")]), "leafy greens", strict=True)
        assert resp.valid is False
        assert resp.warnings == []
        assert resp.errors[0]["code"] == "STRICT_MODE_WARNING"

    def test_empty_ruleset_fails_closed_with_no_verdict(self):
        resp = _summary_to_validate_response(_summary([], reason="no_rules_loaded"), "leafy greens", strict=False)
        assert resp.valid is False
        assert resp.rules_evaluated == 0
        assert resp.no_verdict_reason == "no_rules_loaded"
        assert any(e["code"] == "NO_VERDICT" for e in resp.errors)

    def test_no_verdict_defaults_to_nothing_evaluated_reason(self):
        resp = _summary_to_validate_response(_summary([]), "leafy greens", strict=False)
        assert resp.valid is False
        assert any("nothing_evaluated" in e["message"] for e in resp.errors)


# ---------------------------------------------------------------------------
# Part 2: endpoint robustness (industry filter, cte gate, checklist branches)
# ---------------------------------------------------------------------------

from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_client = TestClient(app)
_API_KEY = os.environ["AUTH_TEST_BYPASS_TOKEN"]


def _headers() -> dict:
    return {"X-RegEngine-API-Key": _API_KEY}


class TestIndustryFilterRobustness:
    def test_padded_industry_matches_plain(self):
        """A pasted ``?industry=`` value with surrounding whitespace must
        resolve the same way as the trimmed value, never as an empty
        (zero-requirement) list."""
        plain = _client.get("/checklists", params={"industry": "Dairy"}, headers=_headers()).json()
        assert plain["total"] >= 1
        padded = _client.get("/checklists", params={"industry": "  Dairy  "}, headers=_headers()).json()
        assert [c["id"] for c in padded["checklists"]] == [c["id"] for c in plain["checklists"]]

    def test_uppercase_industry_id_matches(self):
        by_id = _client.get("/checklists", params={"industry": "DAIRY"}, headers=_headers()).json()
        assert by_id["total"] >= 1


def _one_rule():
    from shared.rules.types import RuleDefinition

    return RuleDefinition(
        rule_id="tlc-required",
        rule_version=1,
        title="TLC required",
        description=None,
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["shipping"], "ftl_scope": ["ALL"]},
        citation_reference="21 CFR 1.1345",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"},
        failure_reason_template="{event_type} event missing {field_name} ({citation})",
        remediation_suggestion="Record the missing field",
    )


@pytest.fixture()
def _seeded_rule(monkeypatch):
    from shared.rules.engine import RulesEngine

    monkeypatch.setattr(RulesEngine, "load_active_rules", lambda self: [_one_rule()])


class TestValidateCteGateRobustness:
    def test_padded_cte_type_reaches_engine(self, _seeded_rule):
        """The gate strips like ``_config_to_engine_event`` does."""
        resp = _client.post(
            "/validate",
            json={"ftl_commodity": "leafy_greens", "config": {"cte_type": "  shipping  ", "tlc": "T-1"}},
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["valid"] is True, body["errors"]

    def test_garbage_cte_type_still_rejected(self, _seeded_rule):
        resp = _client.post(
            "/validate",
            json={"ftl_commodity": "leafy_greens", "config": {"cte_type": "  NOT_A_CTE  ", "tlc": "T-1"}},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert resp.json()["errors"][0]["code"] == "INVALID_CTE_TYPE"

    def test_unknown_checklist_id_is_404(self, _seeded_rule):
        resp = _client.post(
            "/validate",
            json={"ftl_commodity": "leafy_greens", "checklist_id": "no-such-checklist"},
            headers=_headers(),
        )
        assert resp.status_code == 404, resp.text
        assert "no-such-checklist" in str(resp.json())

    def test_known_checklist_without_scope_is_noop(self, _seeded_rule):
        """No scope field in today's schema, so a known id changes nothing."""
        first = _client.get("/checklists", headers=_headers()).json()["checklists"][0]["id"]
        resp = _client.post(
            "/validate",
            json={"ftl_commodity": "leafy_greens", "checklist_id": first},
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["valid"] is True


# ---------------------------------------------------------------------------
# Part 3: snapshot seal and render helpers (pure unit tests)
# ---------------------------------------------------------------------------

from services.compliance.app import snapshots as snap_mod  # noqa: E402


def _row(**overrides) -> dict:
    captured = "2026-05-01T12:00:00+00:00"
    row = {
        "id": "snap-1",
        "tenant_id": "tenant-a",
        "snapshot_name": "Q3 Freeze",
        "snapshot_reason": "FDA audit prep",
        "created_by": "chris@regengine.co",
        "trigger_alert_id": None,
        "is_auto_created": 0,
        "deadline": None,
        "regulatory_citation": None,
        "is_attested": 0,
        "attested_by": None,
        "attested_at": None,
        "attestation_title": None,
        "compliance_status": "COMPLIANT",
        "active_alert_count": 0,
        "critical_alert_count": 0,
        "content_hash": "",
        "snapshot_state": "VALID",
        "degradation_reason": None,
        "captured_at": captured,
    }
    row.update(overrides)
    return row


def _sealed_row(**overrides) -> dict:
    row = _row(**overrides)
    row["content_hash"] = snap_mod._content_hash_v2(snap_mod._sealed_values(row))
    return row


class TestSnapshotSealHelpers:
    def test_derive_status_matrix(self):
        assert snap_mod._derive_status(0, 0) == "COMPLIANT"
        assert snap_mod._derive_status(2, 0) == "AT_RISK"
        assert snap_mod._derive_status(2, 1) == "NON_COMPLIANT"
        assert snap_mod._derive_status(0, 1) == "NON_COMPLIANT"

    def test_countdown_display_boundaries(self):
        assert snap_mod._countdown_display(0) == "0m"
        assert snap_mod._countdown_display(59) == "0m"
        assert snap_mod._countdown_display(3600) == "1h 0m"
        assert snap_mod._countdown_display(90000) == "1d 1h"

    def test_v2_hash_deterministic_and_sensitive(self):
        row = _row()
        first = snap_mod._content_hash_v2(snap_mod._sealed_values(row))
        second = snap_mod._content_hash_v2(snap_mod._sealed_values(_row()))
        assert first == second
        changed = snap_mod._content_hash_v2(snap_mod._sealed_values(_row(snapshot_name="Other")))
        assert changed != first

    def test_v1_and_v2_digests_differ_by_construction(self):
        row = _row()
        sealed = snap_mod._sealed_values(row)
        v2 = snap_mod._content_hash_v2(sealed)
        v1 = snap_mod._content_hash_v1(
            tenant_id="tenant-a",
            snapshot_name="Q3 Freeze",
            snapshot_reason="FDA audit prep",
            created_by="chris@regengine.co",
            captured_at_iso=sealed["captured_at"],
        )
        assert v1 != v2

    def test_sealed_values_normalize_drivers_identically(self):
        """SQLite stores booleans as ints and datetimes as ISO text while
        Postgres returns native types. Both must digest identically."""
        from datetime import datetime, timezone

        sqlite_row = _row(is_auto_created=1, is_attested=0, captured_at="2026-05-01T12:00:00+00:00")
        pg_row = _row(
            is_auto_created=True,
            is_attested=False,
            captured_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        )
        assert snap_mod._sealed_values(sqlite_row) == snap_mod._sealed_values(pg_row)

    def test_seal_version_detects_sealed_field_tampering(self):
        row = _sealed_row()
        assert snap_mod._seal_version(row) == 2
        for field, bad in (
            ("snapshot_name", "Forged"),
            ("compliance_status", "AT_RISK"),
            ("active_alert_count", 99),
            ("created_by", "mallory@evil.example"),
        ):
            tampered = dict(row)
            tampered[field] = bad
            assert snap_mod._seal_version(tampered) is None, field

    def test_lifecycle_fields_sit_outside_the_digest(self):
        row = _sealed_row()
        marked = dict(row)
        marked["snapshot_state"] = "SUPERSEDED"
        marked["degradation_reason"] = "Superseded by a refreeze"
        assert snap_mod._seal_version(marked) == 2

    def test_as_dt_parses_zulu_and_offsets(self):
        assert snap_mod._as_dt("2026-05-01T12:00:00Z") is not None
        assert snap_mod._as_dt(None) is None
        assert snap_mod._as_int(None) == 0
        assert snap_mod._as_int(None, default=7) == 7


class TestSnapshotSerialization:
    def test_unmeasured_posture_renders_not_captured(self):
        row = _sealed_row(
            compliance_status="UNKNOWN", active_alert_count=-1, critical_alert_count=-1
        )
        assert snap_mod._seal_version(row) == 2
        out = snap_mod._serialize(row)
        assert out["posture_captured"] is False
        assert out["compliance_status"] == "NOT_CAPTURED"
        assert out["active_alert_count"] is None
        assert out["critical_alert_count"] is None

    def test_past_deadline_clamps_countdown_at_zero(self):
        row = _sealed_row(deadline="2020-01-01T00:00:00+00:00")
        out = snap_mod._serialize(row)
        assert out["countdown_seconds"] == 0
        assert out["countdown_display"] == "0m"

    def test_render_lines_never_overclaim(self):
        assert snap_mod._integrity_line({"integrity_verified": False}) == "No"
        verified = snap_mod._integrity_line(
            {"integrity_verified": True, "hash_version": 2, "integrity_coverage": "identity, posture, attestation"}
        )
        assert "v2" in verified
        assert snap_mod._status_line({"posture_captured": False}) == "NOT CAPTURED"
        assert snap_mod._count_line(None) == "NOT CAPTURED"
        assert snap_mod._count_line(3) == "3"
        assert snap_mod._attestation_line({"is_attested": False}) == "No"
        backdated = snap_mod._attestation_line({"is_attested": True, "attestation_precedes_capture": True})
        assert backdated.startswith("INVALID")
        assert snap_mod._attestation_line({"is_attested": True, "attestation_precedes_capture": False}) == "Yes"


# ---------------------------------------------------------------------------
# Part 4: known unfixed integrity gaps (xfail, strict)
# ---------------------------------------------------------------------------

from fastapi import FastAPI, Request  # noqa: E402
from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.database import get_db_session  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.compliance.app.snapshots import router as _snapshots_router  # noqa: E402

_QA_DDL = """
CREATE TABLE fsma.compliance_evidence_snapshots (
    id                   TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    snapshot_name        TEXT NOT NULL,
    snapshot_reason      TEXT,
    created_by           TEXT NOT NULL,
    trigger_alert_id     TEXT,
    is_auto_created      INTEGER NOT NULL DEFAULT 0,
    deadline             TEXT,
    regulatory_citation  TEXT,
    is_attested          INTEGER NOT NULL DEFAULT 0,
    attested_by          TEXT,
    attested_at          TEXT,
    attestation_title    TEXT,
    compliance_status    TEXT NOT NULL DEFAULT 'COMPLIANT',
    active_alert_count   INTEGER NOT NULL DEFAULT 0,
    critical_alert_count INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL,
    snapshot_state       TEXT NOT NULL DEFAULT 'VALID',
    degradation_reason   TEXT,
    captured_at          TEXT NOT NULL
)
"""

_QA_TENANT = "qa-gap-tenant"


@pytest.fixture()
def _gap_client():
    from datetime import datetime, timezone

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS fsma")
        conn.exec_driver_sql(_QA_DDL)
    app = FastAPI()
    app.include_router(_snapshots_router)
    factory = sessionmaker(bind=eng)

    def _db():
        db = factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    async def _auth(request: Request) -> APIKey:
        key = APIKey(
            key_id="qa",
            key_hash="",
            name="QA Key",
            tenant_id=_QA_TENANT,
            created_at=datetime.now(timezone.utc),
        )
        request.state.api_key = key
        return key

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_api_key] = _auth
    client = TestClient(app)
    yield client, eng
    eng.dispose()


def _qa_create(client, name="Q3 Freeze"):
    resp = client.post(
        f"/v1/compliance/snapshots/{_QA_TENANT}",
        json={"snapshot_name": name, "snapshot_reason": "prep", "created_by": "chris@regengine.co"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.xfail(
    strict=True,
    reason="BUG (snapshots.py create_snapshot): freeze carries no idempotency key, a retried POST mints a duplicate evidence row",
)
def test_retry_of_create_does_not_duplicate(_gap_client):
    """A client retry after a dropped response must not fork the evidence
    trail. Today the second POST inserts a second row with a new id."""
    client, _eng = _gap_client
    _qa_create(client, name="Q3 Freeze")
    _qa_create(client, name="Q3 Freeze")
    listed = client.get(f"/v1/compliance/snapshots/{_QA_TENANT}").json()["items"]
    assert len([i for i in listed if i["snapshot_name"] == "Q3 Freeze"]) == 1


@pytest.mark.xfail(
    strict=True,
    reason="BUG (snapshots.py refreeze_snapshot): refreeze copies name/reason from a tampered row without a seal check, sealing attacker text under a fresh valid hash",
)
def test_refreeze_of_tampered_snapshot_is_rejected(_gap_client):
    """Refreezing a row whose seal is already broken must fail closed (409)
    like attest does. Today it succeeds and the tampered metadata is
    re-sealed as trustworthy."""
    client, eng = _gap_client
    created = _qa_create(client, name="Q3 Freeze")
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE fsma.compliance_evidence_snapshots SET snapshot_name = ? WHERE id = ?",
            ("Forged Name", created["id"]),
        )
    tampered = client.get(
        f"/v1/compliance/snapshots/{_QA_TENANT}/{created['id']}/verify"
    ).json()
    assert tampered["hash_match"] is False
    resp = client.post(
        f"/v1/compliance/snapshots/{_QA_TENANT}/{created['id']}/refreeze",
        json={},
    )
    assert resp.status_code == 409, resp.text
