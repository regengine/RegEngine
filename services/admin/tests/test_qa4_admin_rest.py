"""Deep QA gap-fill for admin non-auth routes and services.

Covers compliance countdowns, bulk-upload parsing/commit/session paths,
supplier helpers, review list pagination, FDA export scoping and data
export serialization. Pure unit tests plus sqlite-backed helper tests;
no sleeps, no network.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app import review_routes as review_mod  # noqa: E402
from shared.rate_limit import add_rate_limiting  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000003")


# ===========================================================================
# 1. Bulk-upload parser: bare TLC rows must not become events
# ===========================================================================


def _empty_parsed():
    return {"facilities": [], "ftl_scopes": [], "tlcs": [], "events": [], "warnings": []}


class TestClassifyBareTlcRow:
    def test_bare_tlc_row_is_classified_as_tlc(self):
        """A row with only TLC-shape keys is a lot definition, not an
        event. Pre-fix it fell into the ``tlc_code -> event`` catch-all
        and failed downstream validation with a missing-cte_type error
        instead of creating the lot."""
        from app.bulk_upload.parsers import _classify_row

        parsed = _empty_parsed()
        _classify_row(
            parsed,
            {"tlc_code": "TLC-1", "facility_name": "Farm A", "product_description": "Spinach"},
            warnings=[],
        )
        assert len(parsed["tlcs"]) == 1
        assert parsed["tlcs"][0]["tlc_code"] == "TLC-1"
        assert parsed["events"] == []

    def test_event_row_with_event_time_stays_an_event(self):
        """Guard: rows carrying event-shaped fields keep the event path
        so validation still flags a missing cte_type."""
        from app.bulk_upload.parsers import _classify_row

        parsed = _empty_parsed()
        _classify_row(
            parsed,
            {"tlc_code": "TLC-1", "facility_name": "Farm A", "event_time": "2026-03-03T12:00:00Z"},
            warnings=[],
        )
        assert len(parsed["events"]) == 1
        assert parsed["tlcs"] == []

    def test_event_row_with_kde_data_stays_an_event(self):
        from app.bulk_upload.parsers import _classify_row

        parsed = _empty_parsed()
        _classify_row(
            parsed,
            {"tlc_code": "TLC-1", "facility_name": "Farm A", "kde_data": {"quantity": 5}},
            warnings=[],
        )
        assert len(parsed["events"]) == 1
        assert parsed["tlcs"] == []

    def test_cte_type_row_still_wins_over_tlc_branch(self):
        from app.bulk_upload.parsers import _classify_row

        parsed = _empty_parsed()
        _classify_row(
            parsed,
            {"tlc_code": "TLC-1", "facility_name": "Farm A", "cte_type": "shipping"},
            warnings=[],
        )
        assert len(parsed["events"]) == 1
        assert parsed["events"][0]["cte_type"] == "shipping"
        assert parsed["tlcs"] == []


# ===========================================================================
# 2. Bulk commit: ValueError mid-commit must roll back
# ===========================================================================


class TestBulkCommitValueErrorRollback:
    def _mock_db(self):
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []
        db.execute.return_value.scalar_one_or_none.return_value = None
        return db

    def test_unknown_ftl_category_rolls_back(self):
        """Pre-fix only SQLAlchemyError triggered rollback; a ValueError
        (unknown category, unknown facility, empty TLC) propagated with
        the transaction half-flushed."""
        from app.bulk_upload import transaction_manager as tm

        db = self._mock_db()
        user = SimpleNamespace(id=USER_ID, email="u@example.com")
        payload = {
            "facilities": [
                {
                    "name": "Farm A",
                    "street": "1 Main St",
                    "city": "Salinas",
                    "state": "CA",
                    "postal_code": "93901",
                    "roles": [],
                }
            ],
            "ftl_scopes": [{"facility_name": "Farm A", "category_id": "no-such-category"}],
            "tlcs": [],
            "events": [],
        }
        with pytest.raises(ValueError, match="Unknown FTL category_id"):
            tm.execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload=payload,
            )
        assert db.rollback.called, "ValueError path must roll back the half-flushed transaction"


# ===========================================================================
# 3. Compliance countdowns: naive datetimes must not crash to_dict
# ===========================================================================


def _status_model(**kwargs):
    from app.compliance_models import ComplianceStatus, TenantComplianceStatusModel

    m = MagicMock(spec=TenantComplianceStatusModel)
    m._get_status_emoji = TenantComplianceStatusModel._get_status_emoji.__get__(m)
    m._get_status_label = TenantComplianceStatusModel._get_status_label.__get__(m)
    m.to_dict = TenantComplianceStatusModel.to_dict.__get__(m)
    defaults = dict(
        tenant_id=TENANT_ID,
        status=ComplianceStatus.COMPLIANT.value,
        active_alert_count=0,
        critical_alert_count=0,
        completeness_score=1.0,
        last_status_change=None,
        next_deadline=None,
        next_deadline_description=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _alert_model(**kwargs):
    from app.compliance_models import AlertSeverity, ComplianceAlertModel

    m = MagicMock(spec=ComplianceAlertModel)
    m._get_severity_emoji = ComplianceAlertModel._get_severity_emoji.__get__(m)
    m.to_dict = ComplianceAlertModel.to_dict.__get__(m)
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        source_type="FDA_RECALL",
        source_id="R-001",
        title="Test recall",
        summary=None,
        severity=AlertSeverity.HIGH.value,
        countdown_start=None,
        countdown_end=None,
        countdown_hours=24,
        required_actions=None,
        status="ACTIVE",
        acknowledged_at=None,
        acknowledged_by=None,
        resolved_at=None,
        resolved_by=None,
        match_reason=None,
        created_at=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class TestNaiveDatetimeCountdowns:
    def test_status_naive_next_deadline_computes_countdown(self):
        """SQLite/dev rows come back naive; subtracting an aware now()
        raised TypeError and the route returned 500 for a widget that
        should render. Naive is read as UTC."""
        # A UTC instant as SQLite would return it: aware UTC with tzinfo stripped.
        naive_future = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
        assert naive_future.tzinfo is None
        d = _status_model(next_deadline=naive_future).to_dict()
        assert d["countdown_seconds"] is not None
        assert d["countdown_seconds"] > 0

    def test_alert_naive_countdown_end_computes_countdown(self):
        naive_future = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
        d = _alert_model(countdown_end=naive_future).to_dict()
        assert d["countdown_seconds"] > 0
        assert d["is_expired"] is False

    def test_alert_naive_past_deadline_is_expired(self):
        naive_past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
        d = _alert_model(countdown_end=naive_past).to_dict()
        assert d["countdown_seconds"] == 0
        assert d["is_expired"] is True


# ===========================================================================
# 4. Bulk-upload session store: in-memory path must not alias caller dicts
# ===========================================================================


def _memory_only_store():
    from app.bulk_upload.session_store import BulkUploadSessionStore

    store = BulkUploadSessionStore(redis_url="redis://invalid:6379/0")
    store._redis_available = False
    return store


class TestSessionMemoryIsolation:
    def test_create_does_not_alias_caller_payload(self):
        """Pre-fix the memory fallback stored the caller's dict by
        reference, so mutating the input after create_session rewrote
        the stored upload session."""
        store = _memory_only_store()
        payload = {"status": "validated", "rows": [1, 2]}
        sid = asyncio.run(store.create_session("t", "u", payload))
        payload["rows"].append(999)
        stored = asyncio.run(store.get_session("t", "u", sid))
        assert stored["rows"] == [1, 2]

    def test_get_returns_a_copy(self):
        store = _memory_only_store()
        payload = {"status": "validated", "count": 1}
        sid = asyncio.run(store.create_session("t", "u", payload))
        first = asyncio.run(store.get_session("t", "u", sid))
        first["count"] = 999
        second = asyncio.run(store.get_session("t", "u", sid))
        assert second["count"] == 1

    def test_claim_commit_is_single_winner(self):
        """Idempotency: exactly one of two claims from 'validated'
        succeeds; the loser sees None (would-be 409 path)."""
        store = _memory_only_store()
        sid = asyncio.run(store.create_session("t", "u", {"status": "validated"}))
        won = asyncio.run(store.try_claim_commit("t", "u", sid))
        lost = asyncio.run(store.try_claim_commit("t", "u", sid))
        assert won is not None
        assert won["status"] == "processing"
        assert lost is None

    def test_claim_from_wrong_status_returns_none(self):
        store = _memory_only_store()
        sid = asyncio.run(store.create_session("t", "u", {"status": "draft"}))
        assert asyncio.run(store.try_claim_commit("t", "u", sid)) is None
        assert asyncio.run(store.try_claim_commit("t", "u", sid, from_status="draft")) is not None

    def test_claim_returns_a_copy(self):
        store = _memory_only_store()
        sid = asyncio.run(store.create_session("t", "u", {"status": "validated"}))
        claimed = asyncio.run(store.try_claim_commit("t", "u", sid))
        claimed["status"] = "tampered"
        reread = asyncio.run(store.get_session("t", "u", sid))
        assert reread["status"] == "processing"


# ===========================================================================
# 5. Review list pagination gaps (unfixed: xfail)
# ===========================================================================


def _reset_route_limiter(limiter) -> None:
    reset = getattr(limiter, "reset", None)
    if callable(reset):
        reset()
    storage = getattr(limiter, "_storage", None)
    if storage is None:
        return
    storage_reset = getattr(storage, "reset", None)
    if callable(storage_reset):
        storage_reset()


def _fake_review_actor(tenant_id="11111111-1111-1111-1111-111111111111"):
    from app.privileged_auth import PrivilegedActor

    return PrivilegedActor(
        actor_type="tenant_user",
        actor_id="22222222-2222-2222-2222-222222222222",
        session_id="33333333-3333-3333-3333-333333333333",
        auth_method="webauthn",
        tenant_id=tenant_id,
        permissions=("review.read",),
    )


class _LimitHonoringFakeTracker:
    """Fake that honors limit like the real tracker, so the offset/total
    contract can be tested at the HTTP layer."""

    def __init__(self, items):
        self._items = items

    def list_hallucinations(self, *, status, tenant_id, limit, cursor):
        return {
            "items": self._items[:limit],
            "next_cursor": "cursor-1" if len(self._items) > limit else None,
            "has_more": len(self._items) > limit,
        }


@pytest.fixture
def review_app():
    _reset_route_limiter(review_mod.limiter)
    app = FastAPI()
    app.include_router(review_mod.router)
    add_rate_limiting(app)

    now = datetime.now(timezone.utc)
    items = [
        {
            "review_id": f"00000000-0000-0000-0000-00000000000{i}",
            "doc_hash": f"hash-{i}",
            "confidence_score": 0.4,
            "text_preview": f"preview {i}",
            "extraction": {},
            "created_at": now,
            "status": "PENDING",
        }
        for i in range(3)
    ]
    orig = review_mod._get_tracker
    review_mod._get_tracker = lambda: _LimitHonoringFakeTracker(items)
    app.dependency_overrides[review_mod.require_review_read] = lambda: _fake_review_actor()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        review_mod._get_tracker = orig
        _reset_route_limiter(review_mod.limiter)


@pytest.mark.xfail(
    strict=True,
    reason="review-list-offset-ignored: get_review_queue accepts offset but never "
    "forwards it to the cursor-based tracker, so page 2 returns page 1 rows",
)
def test_review_list_offset_skips_items(review_app):
    resp = review_app.get("/v1/admin/review/hallucinations?limit=2&offset=2")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["offset"] == 2
    assert [i["review_id"] for i in body["items"]] == ["00000000-0000-0000-0000-000000000002"]


@pytest.mark.xfail(
    strict=True,
    reason="review-list-total-is-page-size: tracker returns no total so the "
    "response echoes len(items); clients cannot know how many pages exist",
)
def test_review_list_total_reflects_full_count(review_app):
    resp = review_app.get("/v1/admin/review/hallucinations?limit=2&offset=0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3


# ===========================================================================
# 6. Merkle integrity ratio: linkage only, no tamper detection (xfail)
# ===========================================================================


def _fake_event(seq, prev_hash, merkle_hash):
    return SimpleNamespace(sequence_number=seq, merkle_prev_hash=prev_hash, merkle_hash=merkle_hash)


class TestMerkleIntegrityRatio:
    def test_empty_chain_scores_perfect(self):
        from app.supplier_onboarding_routes import _merkle_integrity_ratio

        assert _merkle_integrity_ratio([]) == 1.0

    def test_sequence_gap_lowers_ratio(self):
        from app.supplier_onboarding_routes import _merkle_integrity_ratio

        events = [_fake_event(1, None, "h1"), _fake_event(3, "h1", "h3")]
        assert _merkle_integrity_ratio(events) == pytest.approx(0.5)

    def test_broken_hash_link_lowers_ratio(self):
        from app.supplier_onboarding_routes import _merkle_integrity_ratio

        events = [_fake_event(1, None, "h1"), _fake_event(2, "tampered", "h2")]
        assert _merkle_integrity_ratio(events) == pytest.approx(0.5)

    @pytest.mark.xfail(
        strict=True,
        reason="merkle-integrity-ratio-ignores-payload-tampering: the ratio "
        "checks sequence/linkage shape only and never recomputes "
        "payload_sha256, so edited KDE payloads still score 1.0",
    )
    def test_payload_tampering_lowers_ratio(self):
        from app.supplier_onboarding_routes import _merkle_integrity_ratio

        events = [_fake_event(1, None, "aaaa"), _fake_event(2, "aaaa", "bbbb")]
        assert _merkle_integrity_ratio(events) < 1.0


# ===========================================================================
# 7. FDA export scoping: TLC-only queries intentionally widen to the chain
# ===========================================================================


@pytest.fixture
def supplier_db():
    from app.sqlalchemy_models import (
        SupplierCTEEventModel,
        SupplierFacilityFTLCategoryModel,
        SupplierFacilityModel,
        SupplierFunnelEventModel,
        SupplierTraceabilityLotModel,
        TenantModel,
        UserModel,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    tables = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
        SupplierFunnelEventModel.__table__,
    ]
    for t in tables:
        t.create(bind=engine)
    sm = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = sm()
    session.add(TenantModel(id=TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=USER_ID, email="a@example.com", status="active", is_sysadmin=False))
    session.add(UserModel(id=OTHER_USER_ID, email="b@example.com", status="active", is_sysadmin=False))

    def _facility(owner, name):
        f = SupplierFacilityModel(
            tenant_id=TENANT_ID,
            supplier_user_id=owner,
            name=name,
            street="1 Main St",
            city="Salinas",
            state="CA",
            postal_code="93901",
            roles=["Grower"],
        )
        session.add(f)
        session.flush()
        return f

    fa = _facility(USER_ID, "Farm A")
    fb = _facility(OTHER_USER_ID, "Farm B")
    # TLC codes are unique per tenant: one shared lot, events from both suppliers.
    lot = SupplierTraceabilityLotModel(
        tenant_id=TENANT_ID,
        supplier_user_id=USER_ID,
        facility_id=fa.id,
        tlc_code="TLC-SHARED",
        product_description="Spinach",
        status="active",
    )
    session.add(lot)
    session.flush()
    now = datetime.now(timezone.utc)
    session.add(
        SupplierCTEEventModel(
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            facility_id=fa.id,
            lot_id=lot.id,
            cte_type="harvesting",
            event_time=now,
            kde_data={"quantity": 10},
            payload_sha256="p1",
            merkle_prev_hash=None,
            merkle_hash="h1",
            sequence_number=1,
            obligation_ids=[],
        )
    )
    session.add(
        SupplierCTEEventModel(
            tenant_id=TENANT_ID,
            supplier_user_id=OTHER_USER_ID,
            facility_id=fb.id,
            lot_id=lot.id,
            cte_type="shipping",
            event_time=now,
            kde_data={"quantity": 9},
            payload_sha256="p2",
            merkle_prev_hash="h1",
            merkle_hash="h2",
            sequence_number=2,
            obligation_ids=[],
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


class TestFdaExportScoping:
    def test_supplier_scoped_export_returns_only_own_rows(self, supplier_db):
        """Owner isolation: a supplier-scoped query never sees the other
        supplier's events on the shared lot."""
        from app.supplier_onboarding_routes import _build_fda_export_rows

        rows = _build_fda_export_rows(
            supplier_db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            facility_id=None,
            tlc_code="TLC-SHARED",
            start_time=None,
            end_time=None,
        )
        assert len(rows) == 1
        assert rows[0]["cte_type"] == "harvesting"

    def test_tlc_only_export_returns_full_chain(self, supplier_db):
        """Documents current behavior: a TLC-only query (supplier None,
        as the preview/download routes issue when only tlc_code is
        given) returns every supplier's events on that lot. This is the
        farm-to-fork chain view; flagging for C.Lee to confirm it is
        intended that supplier A can read supplier B's KDE rows."""
        from app.supplier_onboarding_routes import _build_fda_export_rows

        rows = _build_fda_export_rows(
            supplier_db,
            tenant_id=TENANT_ID,
            supplier_user_id=None,
            facility_id=None,
            tlc_code="TLC-SHARED",
            start_time=None,
            end_time=None,
        )
        assert {r["cte_type"] for r in rows} == {"harvesting", "shipping"}


# ===========================================================================
# 8. Pure-helper coverage: cte types, hashes, templates, parsers, export
# ===========================================================================


class TestSupplierCteTypeNormalization:
    def test_alias_and_case_and_whitespace(self):
        from app.supplier_cte_service import _normalize_supplier_cte_type

        assert _normalize_supplier_cte_type("  Transformation ") == "transforming"
        assert _normalize_supplier_cte_type("FIRST_LAND_BASED_RECEIVING") == "first_receiver"
        assert _normalize_supplier_cte_type("Shipping") == "shipping"

    def test_unknown_type_passes_through_for_caller_to_reject(self):
        from app.supplier_cte_service import _normalize_supplier_cte_type

        assert _normalize_supplier_cte_type("teleporting") == "teleporting"


class TestSupplierHashHelpers:
    def test_sha256_json_is_key_order_independent(self):
        from app.supplier_cte_service import _sha256_json

        assert _sha256_json({"b": 1, "a": 2}) == _sha256_json({"a": 2, "b": 1})

    def test_merkle_genesis_differs_from_chained(self):
        from app.supplier_cte_service import _next_merkle_hash

        genesis = _next_merkle_hash(None, "payload")
        chained = _next_merkle_hash("prev", "payload")
        assert genesis != chained
        assert _next_merkle_hash("prev", "payload") == chained


class TestDeriveRequiredCtes:
    def test_dedupes_preserving_first_seen_order(self):
        from app.supplier_onboarding_routes import _derive_required_ctes

        cats = [{"ctes": ["receiving", "shipping"]}, {"ctes": ["shipping", "cooling"]}]
        assert _derive_required_ctes(cats) == ["receiving", "shipping", "cooling"]


class TestBulkUploadTemplates:
    def test_csv_template_has_expected_headers(self):
        from app.bulk_upload.templates import CSV_HEADERS, generate_template

        payload, media_type, filename = generate_template("csv")
        assert media_type == "text/csv"
        assert filename.endswith(".csv")
        header_line = payload.decode("utf-8").splitlines()[0]
        for expected in ("record_type", "facility_name", "tlc_code", "cte_type"):
            assert expected in header_line
        assert set(CSV_HEADERS) >= {"record_type", "facility_name", "tlc_code", "cte_type"}

    def test_unknown_format_rejected(self):
        from app.bulk_upload.templates import generate_template

        with pytest.raises(HTTPException) as exc:
            generate_template("xml")
        assert exc.value.status_code == 400

    def test_xlsx_template_is_a_workbook(self):
        pytest.importorskip("openpyxl")
        from app.bulk_upload.templates import generate_template

        payload, media_type, filename = generate_template("XLSX")
        assert media_type.startswith("application/vnd.openxmlformats")
        assert filename.endswith(".xlsx")
        assert payload[:2] == b"PK"


class TestParserFieldHelpers:
    def test_parse_list_field_variants(self):
        from app.bulk_upload.parsers import _parse_list_field

        assert _parse_list_field(None) == []
        assert _parse_list_field("") == []
        assert _parse_list_field(["a", " ", "b"]) == ["a", "b"]
        assert _parse_list_field('["a", "b"]') == ["a", "b"]
        assert _parse_list_field("Grower, Packer") == ["Grower", "Packer"]

    def test_parse_json_field_invalid_string_is_empty(self):
        from app.bulk_upload.parsers import _parse_json_field

        assert _parse_json_field("{not json") == {}
        assert _parse_json_field("") == {}
        assert _parse_json_field({"a": 1}) == {"a": 1}

    def test_extract_event_row_merges_extra_columns_into_kde(self):
        from app.bulk_upload.parsers import _extract_event_row

        row = {
            "facility_name": "Farm A",
            "tlc_code": "TLC-1",
            "cte_type": "shipping",
            "event_time": "2026-03-03T12:00:00Z",
            "kde_data": {"quantity": 5},
            "origin_city": "Salinas",
            "obligation_ids": "a, b",
        }
        out = _extract_event_row(row)
        assert out["kde_data"]["quantity"] == 5
        assert out["kde_data"]["origin_city"] == "Salinas"
        assert out["obligation_ids"] == ["a", "b"]

    def test_normalize_row_first_writer_wins(self):
        from app.bulk_upload.parsers import _normalize_row

        normalized = _normalize_row({"lot_number": "TLC-9", "tlc": ""})
        assert normalized["tlc_code"] == "TLC-9"


class TestDataExportSerialize:
    def test_serialize_handles_uuid_datetime_none(self):
        from app.data_export_routes import _serialize

        uid = UUID("00000000-0000-0000-0000-000000000001")
        assert _serialize(uid) == str(uid)
        assert _serialize(None) is None
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _serialize(stamp) == stamp.isoformat()
        assert _serialize(42) == "42"


class TestValidationPreviewCommitGate:
    def _preview(self, **kwargs):
        from app.bulk_upload.transaction_manager import build_validation_preview

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []
        return build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            # One row: an all-empty upload is itself a blocking error (#3263).
            normalized_payload={
                "facilities": [{"name": "Farm A"}],
                "ftl_scopes": [],
                "tlcs": [],
                "events": [],
            },
            validation_errors=kwargs.get("validation_errors", []),
        )

    def test_clean_preview_can_commit(self):
        assert self._preview()["can_commit"] is True

    def test_warnings_only_still_can_commit(self):
        preview = self._preview(validation_errors=[{"severity": "warning", "message": "w"}])
        assert preview["can_commit"] is True

    def test_hard_error_blocks_commit(self):
        preview = self._preview(validation_errors=[{"severity": "error", "message": "bad cte"}])
        assert preview["can_commit"] is False

    def test_error_without_severity_blocks_commit_fail_closed(self):
        """Errors missing the severity key (like the preview's own
        unknown-facility errors) must block, never silently pass."""
        preview = self._preview(validation_errors=[{"message": "no severity"}])
        assert preview["can_commit"] is False
