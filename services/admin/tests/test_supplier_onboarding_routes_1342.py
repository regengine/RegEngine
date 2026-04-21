"""
Regression coverage for ``app/supplier_onboarding_routes.py`` — closes the 87% gap.

All uncovered lines are in private helper functions. Tested by calling them
directly with in-memory SQLite sessions or as pure-Python unit tests.

Coverable targets:
* Line 347   — _compute_supplier_compliance: no-facilities early return
* Lines 398, 400 — _compute_supplier_compliance: skip empty / duplicate CTE names
* Line 435   — _compute_supplier_compliance: skip CTE event with empty cte_type
* Line 464   — _compute_supplier_compliance: stale CTE → medium-severity gap
* Line 588   — _compute_funnel_summary: skip FunnelEvent with empty step
* Line 649   — _string_value: None input returns ""
* Lines 686, 691, 693 — _build_fda_export_rows: tlc_code / start_time / end_time filters

Unreachable while openpyxl is installed (practical ceiling):
* Lines 749-754, 758, 768-848 — _xlsx_column_name, _xml_escape, xlsx fallback
* Lines 856-857 — openpyxl ModuleNotFoundError → fallback

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)
from app.supplier_onboarding_routes import (
    _build_fda_export_rows,
    _compute_funnel_summary,
    _compute_supplier_compliance,
    _render_fda_export_xlsx_fallback,
    _string_value,
    _xlsx_column_name,
    _xml_escape,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> Session:
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
    SM = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                      expire_on_commit=False, future=True)
    session = SM()
    session.add(TenantModel(id=TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=USER_ID, email="u@example.com",
                          password_hash="x", status="active", is_sysadmin=False))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


def _make_facility(db: Session, name: str = "Farm A") -> SupplierFacilityModel:
    f = SupplierFacilityModel(
        tenant_id=TENANT_ID, supplier_user_id=USER_ID,
        name=name, street="1 Main St", city="Salinas",
        state="CA", postal_code="93901", roles=["Grower"],
    )
    db.add(f)
    db.flush()
    return f


def _make_ftl_category(db: Session, facility_id: UUID,
                       category_id: str = "1", required_ctes=None) -> None:
    db.add(SupplierFacilityFTLCategoryModel(
        tenant_id=TENANT_ID, facility_id=facility_id,
        category_id=category_id, category_name="Leafy Greens",
        required_ctes=required_ctes or ["harvesting"],
    ))
    db.flush()


def _make_lot(db: Session, facility_id: UUID,
              tlc_code: str = "TLC-001") -> SupplierTraceabilityLotModel:
    lot = SupplierTraceabilityLotModel(
        tenant_id=TENANT_ID, supplier_user_id=USER_ID,
        facility_id=facility_id, tlc_code=tlc_code,
        product_description="Spinach", status="active",
    )
    db.add(lot)
    db.flush()
    return lot


_event_seq = [0]


def _make_event(db: Session, facility_id: UUID, lot_id: UUID,
                cte_type: str = "harvesting",
                event_time: datetime | None = None) -> SupplierCTEEventModel:
    import hashlib, json
    _event_seq[0] += 1
    event_time = event_time or datetime.now(timezone.utc)
    payload = {"cte_type": cte_type, "seq": _event_seq[0]}
    payload_sha256 = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    merkle_hash = hashlib.sha256(f"merkle-{_event_seq[0]}".encode()).hexdigest()
    e = SupplierCTEEventModel(
        tenant_id=TENANT_ID, supplier_user_id=USER_ID,
        facility_id=facility_id, lot_id=lot_id,
        cte_type=cte_type, event_time=event_time,
        payload_sha256=payload_sha256,
        merkle_hash=merkle_hash,
        merkle_prev_hash=None,
        sequence_number=_event_seq[0],
        kde_data={},
    )
    db.add(e)
    db.flush()
    return e


# ---------------------------------------------------------------------------
# _compute_supplier_compliance — lines 347, 398, 400, 435, 464
# ---------------------------------------------------------------------------


class TestComputeSupplierCompliance:

    def test_no_facilities_returns_zero_score(self, db: Session):
        """Line 347: when no facilities match, return early with score=0."""
        score, gaps = _compute_supplier_compliance(
            db, tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None, lookback_days=30,
        )
        assert score["score"] == 0
        assert score["coverage_ratio"] == 0.0
        assert gaps == []

    def test_duplicate_cte_type_in_category_skipped(self, db: Session):
        """Lines 398, 400: required_ctes list with duplicates — duplicates skipped.
        Only one entry for 'harvesting' regardless of how many times it appears."""
        f = _make_facility(db)
        # Two categories both requiring 'harvesting' → only counted once per facility
        _make_ftl_category(db, f.id, category_id="1",
                           required_ctes=["harvesting", "harvesting", "harvesting"])
        db.commit()

        score, gaps = _compute_supplier_compliance(
            db, tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None, lookback_days=30,
        )
        # One unique required CTE ('harvesting'), no events → 1 gap
        assert score["required_ctes"] == 1
        assert len(gaps) == 1

    def test_empty_cte_type_in_required_list_skipped(self, db: Session):
        """Lines 398, 400: empty string in required_ctes is skipped."""
        f = _make_facility(db)
        _make_ftl_category(db, f.id, required_ctes=["", "harvesting"])
        db.commit()

        score, gaps = _compute_supplier_compliance(
            db, tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None, lookback_days=30,
        )
        assert score["required_ctes"] == 1  # empty string skipped

    def test_event_with_empty_cte_type_skipped(self, db: Session):
        """Line 435: CTE event with empty cte_type is skipped in events_by_facility loop."""
        f = _make_facility(db)
        _make_ftl_category(db, f.id, required_ctes=["harvesting"])
        lot = _make_lot(db, f.id)
        _make_event(db, f.id, lot.id, cte_type="")  # empty → skipped
        db.commit()

        score, gaps = _compute_supplier_compliance(
            db, tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None, lookback_days=30,
        )
        # 'harvesting' is required, no valid event covered it
        assert score["covered_ctes"] == 0
        assert len(gaps) == 1  # harvesting missing

    def test_stale_event_produces_medium_severity_gap(self, db: Session):
        """Line 464: CTE event older than lookback_days → stale gap with severity='medium'."""
        f = _make_facility(db)
        _make_ftl_category(db, f.id, required_ctes=["harvesting"])
        lot = _make_lot(db, f.id)
        stale_time = datetime.now(timezone.utc) - timedelta(days=60)
        _make_event(db, f.id, lot.id, cte_type="harvesting", event_time=stale_time)
        db.commit()

        score, gaps = _compute_supplier_compliance(
            db, tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None, lookback_days=30,
        )
        stale_gaps = [g for g in gaps if g["severity"] == "medium"]
        assert len(stale_gaps) == 1
        assert stale_gaps[0]["cte_type"] == "harvesting"
        assert score["covered_ctes"] == 1
        assert score["stale_ctes"] == 1


# ---------------------------------------------------------------------------
# _compute_funnel_summary — line 588
# ---------------------------------------------------------------------------


class TestComputeFunnelSummary:

    def test_funnel_event_with_empty_step_skipped(self, db: Session):
        """Line 588: FunnelEvent with empty/None step is skipped in step aggregation."""
        db.add(SupplierFunnelEventModel(
            tenant_id=TENANT_ID, supplier_user_id=USER_ID,
            facility_id=None,
            event_name="step_viewed",
            step=None,  # empty step → skip
            status=None,
            metadata={},
        ))
        db.commit()

        result = _compute_funnel_summary(db, tenant_id=TENANT_ID)
        assert "steps" in result
        # No valid step was accumulated
        steps_with_data = [s for s in result["steps"] if s.get("viewed", 0) > 0]
        assert steps_with_data == []


# ---------------------------------------------------------------------------
# _string_value — line 649
# ---------------------------------------------------------------------------


class TestStringValue:

    def test_none_returns_empty_string(self):
        """Line 649: _string_value(None) → ''."""
        assert _string_value(None) == ""

    def test_string_returns_itself(self):
        """Line 651: _string_value(str) → same str."""
        assert _string_value("hello") == "hello"

    def test_non_string_returns_str(self):
        """Line 652: _string_value(int) → str(int)."""
        assert _string_value(42) == "42"


# ---------------------------------------------------------------------------
# _build_fda_export_rows — lines 686, 691, 693
# ---------------------------------------------------------------------------


class TestBuildFdaExportRows:

    def _base_export_kwargs(self, facility_id=None, tlc_code=None,
                            start_time=None, end_time=None):
        return dict(
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            facility_id=facility_id,
            tlc_code=tlc_code,
            start_time=start_time,
            end_time=end_time,
        )

    def test_tlc_code_filter_applied(self, db: Session):
        """Line 686: tlc_code filter narrows results."""
        f = _make_facility(db)
        lot1 = _make_lot(db, f.id, tlc_code="TLC-A")
        lot2 = _make_lot(db, f.id, tlc_code="TLC-B")
        _make_event(db, f.id, lot1.id, cte_type="harvesting")
        _make_event(db, f.id, lot2.id, cte_type="harvesting")
        db.commit()

        rows = _build_fda_export_rows(
            db, **self._base_export_kwargs(tlc_code="TLC-A")
        )
        assert len(rows) == 1
        assert rows[0]["tlc_code"] == "TLC-A"

    def test_start_time_filter_applied(self, db: Session):
        """Line 691: start_time filter excludes older events."""
        f = _make_facility(db)
        lot = _make_lot(db, f.id)
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _make_event(db, f.id, lot.id, cte_type="harvesting", event_time=old)
        _make_event(db, f.id, lot.id, cte_type="shipping", event_time=new)
        db.commit()

        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        rows = _build_fda_export_rows(
            db, **self._base_export_kwargs(start_time=cutoff)
        )
        # Only the 2026 event is after the cutoff
        assert len(rows) == 1

    def test_end_time_filter_applied(self, db: Session):  # noqa: F811
        """Line 693: end_time filter excludes newer events."""
        f = _make_facility(db)
        lot = _make_lot(db, f.id)
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new = datetime(2026, 4, 1, tzinfo=timezone.utc)
        _make_event(db, f.id, lot.id, cte_type="harvesting", event_time=old)
        _make_event(db, f.id, lot.id, cte_type="shipping", event_time=new)
        db.commit()

        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        rows = _build_fda_export_rows(
            db, **self._base_export_kwargs(end_time=cutoff)
        )
        # Only the 2025 event is before the cutoff
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# _xlsx_column_name — lines 749-754
# ---------------------------------------------------------------------------


class TestXlsxColumnName:

    def test_first_column_is_A(self):
        """Line 749-754: index 1 → 'A'."""
        assert _xlsx_column_name(1) == "A"

    def test_26th_column_is_Z(self):
        """Line 749-754: index 26 → 'Z'."""
        assert _xlsx_column_name(26) == "Z"

    def test_27th_column_is_AA(self):
        """Line 749-754: index 27 → 'AA' (multi-character column)."""
        assert _xlsx_column_name(27) == "AA"

    def test_index_zero_returns_empty(self):
        """Edge: index 0 → '' (loop never executes)."""
        assert _xlsx_column_name(0) == ""


# ---------------------------------------------------------------------------
# _xml_escape — line 758
# ---------------------------------------------------------------------------


class TestXmlEscape:

    def test_escapes_all_special_chars(self):
        """Line 758: all five special XML characters are escaped."""
        raw = """<a>&"'</a>"""
        escaped = _xml_escape(raw)
        assert "&amp;" in escaped
        assert "&lt;" in escaped
        assert "&gt;" in escaped
        assert "&quot;" in escaped
        assert "&apos;" in escaped
        assert "<" not in escaped
        assert ">" not in escaped

    def test_plain_string_unchanged(self):
        """Line 758: string without special chars passes through."""
        assert _xml_escape("hello world") == "hello world"


# ---------------------------------------------------------------------------
# _render_fda_export_xlsx_fallback — lines 768-848
# ---------------------------------------------------------------------------


class TestRenderFdaExportXlsxFallback:

    def test_empty_rows_returns_valid_xlsx_bytes(self):
        """Lines 768-848: no data rows → valid ZIP/xlsx bytes."""
        import zipfile, io
        result = _render_fda_export_xlsx_fallback([])
        assert isinstance(result, bytes)
        assert len(result) > 0
        # Validate it's a valid ZIP (xlsx is a ZIP)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names

    def test_row_with_data_included(self):
        """Lines 781-789: data rows are included in the worksheet XML."""
        import zipfile, io
        rows = [{"tlc_code": "TLC-001", "cte_type": "harvesting"}]
        result = _render_fda_export_xlsx_fallback(rows)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        # At least 2 rows (header + data row)
        assert 'r="2"' in sheet_xml

    def test_special_chars_in_data_are_escaped(self):
        """Lines 785, 758 combined: XML special chars in data are escaped."""
        import zipfile, io
        rows = [{"tlc_code": "<test>&'\"</test>"}]
        result = _render_fda_export_xlsx_fallback(rows)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        # Raw < should not appear (it would break XML)
        assert "<test>" not in sheet_xml
        assert "&lt;test&gt;" in sheet_xml
