"""Data-free checks for remediation validation and empty-state behavior."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.integration_webhook import FieldMapping, _apply_mapping, _extract_nested  # noqa: E402
from app.remediation import (  # noqa: E402
    corrections,
    delivery,
    evidence,
    state as rem_state,
    supplier_router as sup,
    validation as rem_val,
)
from app.remediation.schemas import (  # noqa: E402
    CorrectionRequest,
    CreateLinkRequest,
    ExchangeRequest,
)


class TestValidateFieldPath:
    def test_allowed_top_level_and_kde_paths(self):
        allowed = ["quantity", "kdes.notes"]
        for path in allowed:
            corrections.validate_field_path(path, allowed)

    def test_not_in_allowlist_rejected(self):
        with pytest.raises(HTTPException) as exc:
            corrections.validate_field_path("quantity", [])
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
        updated = corrections.set_value({}, "kdes.notes", None)
        assert corrections.get_value(updated, "kdes.notes") is None
        assert updated == {"kdes": {"notes": None}}

    def test_set_does_not_mutate_original(self):
        original = {}
        assert corrections.set_value(original, "quantity", None) == {"quantity": None}
        assert original == {}

    def test_apply_empty_patches_preserves_empty_input(self):
        assert corrections.apply_patches({}, []) == {}


class TestPatchChain:
    def test_empty_chain_verifies(self):
        assert corrections.verify_patch_chain([]) is True

    def test_empty_body_hash_has_sha256_shape(self):
        digest = corrections.compute_patch_hash(None, {})
        assert len(digest) == 64
        int(digest, 16)


class TestStateTransition:
    def test_illegal_transition_is_409_before_any_write(self):
        class NoWriteDB:
            def execute(self, *_args, **_kwargs):
                pytest.fail("illegal transition attempted a database write")

        with pytest.raises(HTTPException) as exc:
            rem_state.transition(
                NoWriteDB(), tenant_id="", case_id="", to_status="released", expected_from="detected"
            )
        assert exc.value.status_code == 409
        assert "E_ILLEGAL_TRANSITION" in exc.value.detail

    def test_stale_transition_is_409(self):
        class EmptyDB:
            def execute(self, *_args, **_kwargs):
                return SimpleNamespace(rowcount=0)

        with pytest.raises(HTTPException) as exc:
            rem_state.transition(
                EmptyDB(),
                tenant_id="",
                case_id="",
                to_status="supplier_action_required",
                expected_from="detected",
            )
        assert exc.value.status_code == 409
        assert "E_STALE_TRANSITION" in exc.value.detail


class TestBuildEventFromRow:
    def test_empty_row_has_no_invented_fields(self):
        event, provenance, failures = rem_val.build_event_from_row({})
        assert event == {"kdes": {}}
        assert provenance == {}
        assert failures == []

    def test_empty_row_fingerprint_has_sha256_shape(self):
        fingerprint = rem_val.row_fingerprint({})
        assert len(fingerprint) == 64
        int(fingerprint, 16)

    def test_empty_canonical_json_is_stable(self):
        assert rem_val.canonical_json({}) == "{}"


class TestSnapshotFailures:
    def test_no_findings_are_not_blocking(self):
        failures, warnings, blocking = rem_val.snapshot_failures([], SimpleNamespace(results=[]), [])
        assert failures == []
        assert warnings == []
        assert blocking is False

    def test_duplicate_issue_ids_deduplicated(self):
        error = "Missing required KDE 'quantity'"
        failures, warnings, blocking = rem_val.snapshot_failures(
            [error, error], SimpleNamespace(results=[]), []
        )
        assert len(failures) == 1
        assert warnings == []
        assert blocking is True


class TestCorrectableFields:
    def test_no_failures_have_no_correctable_fields(self):
        assert rem_val.correctable_fields([]) == []

    def test_top_level_field_correctable(self):
        failures, _warnings, _blocking = rem_val.snapshot_failures(
            ["Missing required KDE 'quantity'"], SimpleNamespace(results=[]), []
        )
        assert [field["field_path"] for field in rem_val.correctable_fields(failures)] == ["quantity"]

    def test_row_level_finding_skipped(self):
        assert rem_val.correctable_fields([{"field": None}]) == []


class TestEvidence:
    def test_accepted_csv_with_no_records_contains_only_header(self):
        with io.StringIO(evidence._accepted_csv([])) as stream:
            import csv

            assert list(csv.reader(stream)) == [evidence._CSV_COLUMNS]

    def test_bundle_content_hash_stable_across_rebuilds(self):
        empty_sha = hashlib.sha256(b"").hexdigest()
        meta = {"raw_bytes": b"", "filename": "", "sha256": empty_sha}
        first = evidence.build_bundle(None, tenant_id="", run_meta=meta, records=[], run_id="")
        second = evidence.build_bundle(None, tenant_id="", run_meta=meta, records=[], run_id="")

        def manifest(bundle):
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                return json.loads(archive.read("manifest.json"))

        assert manifest(first)["records"] == []
        assert manifest(first)["bundle_content_hash"] == manifest(second)["bundle_content_hash"]


class TestDelivery:
    def test_correction_url_places_empty_fragment_after_base(self):
        assert delivery.correction_url("") == f"{delivery.CORRECTION_URL_BASE}#"

    def test_render_html_escapes_metacharacters(self):
        html = delivery._render_html("<>&'\"", None)
        assert "&lt;&gt;&amp;&#x27;&quot;" in html
        assert "<>&'\"" not in html

    def test_missing_token_is_skipped(self):
        assert delivery.NotificationOutboxDrainer._token_skip_reason(None) == "token_missing"


class TestSupplierRateLimit:
    def _request_without_host(self):
        return SimpleNamespace(headers={}, client=None)

    def test_missing_client_host_uses_unknown_bucket(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(sup, "_consume_rate_limit", lambda **kw: seen.update(kw) or (True, 0))
        sup._rate_limit(self._request_without_host(), "preview", 1)
        assert seen["tenant_id"] == "remsup:unknown"

    def test_denied_is_429(self, monkeypatch):
        monkeypatch.setattr(sup, "_consume_rate_limit", lambda **_kw: (False, 0))
        with pytest.raises(HTTPException) as exc:
            sup._rate_limit(self._request_without_host(), "exchange", 1)
        assert exc.value.status_code == 429


class TestSchemas:
    def test_empty_changes_rejected(self):
        with pytest.raises(ValidationError) as exc:
            CorrectionRequest.model_validate({"changes": {}})
        assert any(error["loc"] == ("changes",) for error in exc.value.errors())

    def test_empty_exchange_token_rejected(self):
        with pytest.raises(ValidationError):
            ExchangeRequest(token="")

    def test_link_expiry_bounds(self):
        with pytest.raises(ValidationError):
            CreateLinkRequest(expires_hours=0)
        with pytest.raises(ValidationError):
            CreateLinkRequest(expires_hours=169)
        assert CreateLinkRequest().expires_hours == 24


class TestIntegrationMappingHelpers:
    def test_missing_nested_source_produces_no_canonical_fields(self):
        mapping = FieldMapping(cte_type="header.docType")
        assert _apply_mapping({}, mapping) == {}
        assert _extract_nested({}, "header.docType") is None
