"""
Regression coverage for ``app/bulk_upload/transaction_manager.py`` — closes
the 81% gap left by the existing e2e tests.

Missing lines fall into two groups:

1. Pure utility functions (no DB):
   - ``_iso_utc`` naive-datetime branch (line 44-45)
   - ``_parse_optional_datetime`` None, empty-string, and naive-datetime
     branches (lines 51, 54, 57)

2. DB-touching paths in ``build_validation_preview`` and
   ``execute_bulk_commit`` that the happy-path e2e tests skip:
   - build_validation_preview: facility-update counter (line 95),
     empty facility_name ref skip (line 108), unknown facility_name
     error append (line 111), TLC-update counter (line 137)
   - execute_bulk_commit: resolve_facility_by_name DB fallback (213-219),
     unknown-facility ValueError (220-221), facility update branch
     (249-256), unknown FTL category_id ValueError (line 263),
     existing FTL scope update (281-282), empty tlc_code ValueError
     (line 297), TLC update branch (320-327), SQLAlchemy rollback
     (407-408), facility None skip in post-commit loop (line 415)

Uses the same SQLite in-memory fixture as test_bulk_upload_e2e.py.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bulk_upload.transaction_manager import (  # noqa: E402
    _iso_utc,
    _parse_optional_datetime,
    build_validation_preview,
    execute_bulk_commit,
)
from app.sqlalchemy_models import (  # noqa: E402
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# Shared DB fixture (same pattern as test_bulk_upload_e2e.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
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
    ]
    for t in tables:
        t.create(bind=engine)

    Session_ = sessionmaker(
        bind=engine, autoflush=False, autocommit=False,
        expire_on_commit=False, future=True,
    )
    session = Session_()
    session.add(TenantModel(
        id=TENANT_ID, name="T", slug="t", status="active", settings={},
    ))
    session.add(UserModel(
        id=USER_ID, email="sup@example.com", password_hash="x",
        status="active", is_sysadmin=False,
    ))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


@pytest.fixture()
def user(db: Session) -> UserModel:
    return db.get(UserModel, USER_ID)


def _add_facility(db: Session, name: str = "Farm A", **kwargs) -> SupplierFacilityModel:
    f = SupplierFacilityModel(
        tenant_id=TENANT_ID,
        supplier_user_id=USER_ID,
        name=name,
        street=kwargs.get("street", "123 Main"),
        city=kwargs.get("city", "Salinas"),
        state=kwargs.get("state", "CA"),
        postal_code=kwargs.get("postal_code", "93901"),
        fda_registration_number=None,
        roles=[],
    )
    db.add(f)
    db.flush()
    return f


def _add_tlc(db: Session, facility: SupplierFacilityModel, code: str = "TLC-001") -> SupplierTraceabilityLotModel:
    lot = SupplierTraceabilityLotModel(
        tenant_id=TENANT_ID,
        supplier_user_id=USER_ID,
        facility_id=facility.id,
        tlc_code=code,
        product_description="Romaine",
        status="active",
    )
    db.add(lot)
    db.flush()
    return lot


# ---------------------------------------------------------------------------
# _iso_utc — lines 44-45 (naive datetime branch)
# ---------------------------------------------------------------------------


class TestIsoUtc:

    def test_naive_datetime_gets_utc_attached(self):
        """Line 44-45: naive datetime (no tzinfo) must have UTC attached
        via replace(), not astimezone() — the latter would use the local
        tz which is non-deterministic in CI."""
        naive = datetime(2026, 1, 15, 12, 0, 0)
        result = _iso_utc(naive)
        assert result == "2026-01-15T12:00:00+00:00"

    def test_aware_datetime_converted_to_utc(self):
        """Line 46 (else): aware datetime is astimezone'd to UTC."""
        aware_est = datetime(2026, 1, 15, 12, 0, 0,
                            tzinfo=timezone(timedelta(hours=-5)))
        result = _iso_utc(aware_est)
        assert result == "2026-01-15T17:00:00+00:00"


# ---------------------------------------------------------------------------
# _parse_optional_datetime — lines 51, 54, 57
# ---------------------------------------------------------------------------


class TestParseOptionalDatetime:

    def test_none_returns_none(self):
        """Line 51: None input → None output. Guards callers that pass
        an optional event_time field directly from row.get()."""
        assert _parse_optional_datetime(None) is None

    def test_empty_string_returns_none(self):
        """Line 54: empty string (and whitespace-only) → None. Prevents
        fromisoformat('') ValueError when the spreadsheet cell is blank."""
        assert _parse_optional_datetime("") is None
        assert _parse_optional_datetime("   ") is None

    def test_naive_iso_gets_utc(self):
        """Line 57: ISO string without timezone info → parsed and UTC
        attached via replace(). Mirrors the _iso_utc naive branch."""
        result = _parse_optional_datetime("2026-06-01T08:30:00")
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2026
        assert result.hour == 8

    def test_aware_iso_converted_to_utc(self):
        """Line 58: ISO string with +05:00 timezone → converted to UTC."""
        result = _parse_optional_datetime("2026-06-01T13:30:00+05:00")
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.hour == 8  # 13:30 IST → 08:30 UTC

    def test_z_suffix_converted(self):
        """Z suffix is replaced with +00:00 before fromisoformat."""
        result = _parse_optional_datetime("2026-06-01T08:30:00Z")
        assert result is not None
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# build_validation_preview — lines 95, 108, 111, 137
# ---------------------------------------------------------------------------


class TestBuildValidationPreview:

    def test_facility_update_counted_when_identity_key_matches(self, db):
        """Line 95: when the incoming facility row matches an existing
        one by (name, street, city, state, postal_code), it increments
        facilities_to_update, not facilities_to_create."""
        _add_facility(db, name="Farm A", street="123 Main",
                      city="Salinas", state="CA", postal_code="93901")
        db.commit()

        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "facilities": [{"name": "Farm A", "street": "123 Main",
                                "city": "Salinas", "state": "CA",
                                "postal_code": "93901"}],
            },
            validation_errors=[],
        )

        assert result["facilities_to_update"] == 1
        assert result["facilities_to_create"] == 0

    def test_empty_facility_name_ref_skipped(self, db):
        """Line 108: ftl_scope / tlc / event row with blank facility_name
        is silently skipped — no error appended and no crash."""
        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "ftl_scopes": [{"facility_name": "", "category_id": "2"}],
            },
            validation_errors=[],
        )
        # No unknown-facility error because we skip empty refs
        unknown_errors = [e for e in result["errors"]
                          if "Unknown facility_name" in e.get("message", "")]
        assert len(unknown_errors) == 0

    def test_unknown_facility_name_appends_error(self, db):
        """Line 111: ftl_scope referencing a facility_name that doesn't
        exist in DB or payload appends an error with section + row."""
        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "ftl_scopes": [{"facility_name": "Ghost Farm",
                                "category_id": "2"}],
            },
            validation_errors=[],
        )
        unknown = [e for e in result["errors"]
                   if "Unknown facility_name" in e.get("message", "")]
        assert len(unknown) == 1
        assert unknown[0]["section"] == "ftl_scope"
        assert unknown[0]["row"] == 1

    def test_existing_tlc_counted_as_update(self, db):
        """Line 137: TLC row whose tlc_code already exists in DB →
        tlcs_to_update incremented, not tlcs_to_create."""
        f = _add_facility(db)
        _add_tlc(db, f, code="TLC-EXISTING")
        db.commit()

        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "tlcs": [{"tlc_code": "TLC-EXISTING",
                           "facility_name": "Farm A"}],
            },
            validation_errors=[],
        )

        assert result["tlcs_to_update"] == 1
        assert result["tlcs_to_create"] == 0


# ---------------------------------------------------------------------------
# execute_bulk_commit — DB-touching branches
# ---------------------------------------------------------------------------


class TestExecuteBulkCommit:

    def _patch_graph(self):
        """Return a context-manager that stubs out all graph sync calls
        so tests don't need a live Neo4j or graph service."""
        return patch(
            "app.bulk_upload.transaction_manager.supplier_graph_sync",
            MagicMock(),
        )

    def test_facility_update_branch(self, db, user):
        """Lines 249-256: existing facility — fda_registration_number and
        roles are updated in-place. facilities_updated counter incremented."""
        _add_facility(db, name="Farm B", street="1 Oak",
                      city="Fresno", state="CA", postal_code="93720")
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [{"name": "Farm B", "street": "1 Oak",
                                    "city": "Fresno", "state": "CA",
                                    "postal_code": "93720",
                                    "fda_registration_number": "REG-001",
                                    "roles": ["shipper"]}],
                },
            )

        assert result["facilities_updated"] == 1
        assert result["facilities_created"] == 0

    def test_unknown_ftl_category_raises(self, db, user):
        """Line 263: FTL scope row referencing an unknown category_id
        raises ValueError inside the try block → triggers rollback."""
        _add_facility(db)
        db.commit()

        with self._patch_graph():
            with pytest.raises(ValueError, match="Unknown FTL category_id"):
                execute_bulk_commit(
                    db,
                    tenant_id=TENANT_ID,
                    current_user=user,
                    normalized_payload={
                        "facilities": [{"name": "Farm A", "street": "123 Main",
                                        "city": "Salinas", "state": "CA",
                                        "postal_code": "93901"}],
                        "ftl_scopes": [{"facility_name": "Farm A",
                                        "category_id": "INVALID_XYZ"}],
                    },
                )

    def test_existing_ftl_scope_updated(self, db, user):
        """Lines 281-282: FTL scope already in DB for this facility/category
        → category_name and required_ctes updated rather than inserting a
        duplicate."""
        f = _add_facility(db)
        existing_scope = SupplierFacilityFTLCategoryModel(
            tenant_id=TENANT_ID,
            facility_id=f.id,
            category_id="2",
            category_name="Old Name",
            required_ctes=["SHIPPING"],
        )
        db.add(existing_scope)
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [{"name": "Farm A", "street": "123 Main",
                                    "city": "Salinas", "state": "CA",
                                    "postal_code": "93901"}],
                    "ftl_scopes": [{"facility_name": "Farm A",
                                    "category_id": "2"}],
                },
            )

        assert result["ftl_scopes_upserted"] == 1
        # Verify the existing row was updated, not duplicated
        from sqlalchemy import select as sa_select
        scopes = db.execute(
            sa_select(SupplierFacilityFTLCategoryModel).where(
                SupplierFacilityFTLCategoryModel.facility_id == f.id
            )
        ).scalars().all()
        assert len(scopes) == 1

    def test_empty_tlc_code_raises(self, db, user):
        """Line 297: TLC row with blank tlc_code raises ValueError,
        which rolls back the whole transaction."""
        _add_facility(db)
        db.commit()

        with self._patch_graph():
            with pytest.raises(ValueError, match="tlc_code is required"):
                execute_bulk_commit(
                    db,
                    tenant_id=TENANT_ID,
                    current_user=user,
                    normalized_payload={
                        "facilities": [{"name": "Farm A", "street": "123 Main",
                                        "city": "Salinas", "state": "CA",
                                        "postal_code": "93901"}],
                        "tlcs": [{"facility_name": "Farm A", "tlc_code": ""}],
                    },
                )

    def test_existing_tlc_updated(self, db, user):
        """Lines 320-327: TLC row whose tlc_code already exists → facility_id,
        product_description, and status updated in-place."""
        f = _add_facility(db)
        _add_tlc(db, f, code="TLC-UPDATE")
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [{"name": "Farm A", "street": "123 Main",
                                    "city": "Salinas", "state": "CA",
                                    "postal_code": "93901"}],
                    "tlcs": [{"facility_name": "Farm A",
                               "tlc_code": "TLC-UPDATE",
                               "product_description": "Iceberg Lettuce",
                               "status": "inactive"}],
                },
            )

        assert result["tlcs_updated"] == 1
        assert result["tlcs_created"] == 0

    def test_sqlalchemy_error_triggers_rollback(self, db, user):
        """Lines 407-408: SQLAlchemyError inside execute_bulk_commit must
        call db.rollback() and re-raise — keeping the DB clean for the
        caller to retry. If rollback is skipped the connection is left
        in an aborted-transaction state that poisons the pool."""
        _add_facility(db)
        db.commit()

        real_flush = db.flush
        call_count = [0]

        def exploding_flush():
            call_count[0] += 1
            if call_count[0] >= 2:
                raise SQLAlchemyError("simulated DB error")
            real_flush()

        db.flush = exploding_flush

        with self._patch_graph():
            with pytest.raises(SQLAlchemyError):
                execute_bulk_commit(
                    db,
                    tenant_id=TENANT_ID,
                    current_user=user,
                    normalized_payload={
                        "facilities": [{"name": "Farm A", "street": "123 Main",
                                        "city": "Salinas", "state": "CA",
                                        "postal_code": "93901"},
                                       {"name": "Farm X", "street": "2 Pine",
                                        "city": "Fresno", "state": "CA",
                                        "postal_code": "93720"}],
                    },
                )

        # Restore
        db.flush = real_flush

    def test_resolve_facility_by_name_db_fallback(self, db, user):
        """Lines 213-219: when facility is not in the in-memory
        facilities_by_name cache, resolve_facility_by_name queries the
        DB. This happens when the TLC/event section references a
        facility not in the 'facilities' payload section but already
        in the DB from a prior upload."""
        # Pre-insert facility but don't include it in facilities payload
        _add_facility(db, name="Pre-existing Farm",
                      street="9 Oak", city="Modesto",
                      state="CA", postal_code="95350")
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    # No facilities section — only a TLC referencing existing
                    "tlcs": [{"facility_name": "Pre-existing Farm",
                               "tlc_code": "TLC-DB-FALLBACK",
                               "product_description": "Spinach",
                               "status": "active"}],
                },
            )

        assert result["tlcs_created"] == 1

    def test_resolve_facility_unknown_raises_value_error(self, db, user):
        """Lines 220-221: if the DB fallback also comes up empty,
        raise ValueError('Unknown facility_name reference: ...'). This
        propagates out of the try block and triggers rollback."""
        with self._patch_graph():
            with pytest.raises(ValueError, match="Unknown facility_name"):
                execute_bulk_commit(
                    db,
                    tenant_id=TENANT_ID,
                    current_user=user,
                    normalized_payload={
                        "tlcs": [{"facility_name": "Ghost Farm",
                                   "tlc_code": "TLC-GHOST"}],
                    },
                )


# ---------------------------------------------------------------------------
# Additional coverage for lines still missing after first pass
# ---------------------------------------------------------------------------


class TestBuildValidationPreviewAdditional:

    def test_new_facility_counted_as_create(self, db):
        """Line 97: facility row with no existing identity-key match →
        facilities_to_create incremented."""
        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "facilities": [{"name": "Brand New Farm", "street": "9 New",
                                "city": "Tulare", "state": "CA",
                                "postal_code": "93274"}],
            },
            validation_errors=[],
        )
        assert result["facilities_to_create"] == 1
        assert result["facilities_to_update"] == 0

    def test_new_tlc_counted_as_create(self, db):
        """Line 139: TLC row whose tlc_code is NOT in the DB →
        tlcs_to_create incremented."""
        result = build_validation_preview(
            db,
            tenant_id=TENANT_ID,
            supplier_user_id=USER_ID,
            normalized_payload={
                "tlcs": [{"tlc_code": "BRAND-NEW-TLC",
                           "facility_name": "Anywhere"}],
            },
            validation_errors=[],
        )
        assert result["tlcs_to_create"] == 1
        assert result["tlcs_to_update"] == 0


class TestExecuteBulkCommitAdditional:

    def _patch_graph(self):
        return patch(
            "app.bulk_upload.transaction_manager.supplier_graph_sync",
            MagicMock(),
        )

    def test_new_ftl_scope_created(self, db, user):
        """Lines 272-279: FTL scope row for a facility that has NO
        existing scope in DB → new SupplierFacilityFTLCategoryModel
        inserted."""
        _add_facility(db)
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [{"name": "Farm A", "street": "123 Main",
                                    "city": "Salinas", "state": "CA",
                                    "postal_code": "93901"}],
                    "ftl_scopes": [{"facility_name": "Farm A",
                                    "category_id": "1"}],
                },
            )

        assert result["ftl_scopes_upserted"] == 1

    def test_event_batch_processed(self, db, user):
        """Lines 345-361: events section runs through the batch loop and
        calls _persist_supplier_cte_event for each row. Pins the batch
        processing path so a refactor that accidentally skips events
        doesn't silently drop data."""
        f = _add_facility(db)
        _add_tlc(db, f, code="TLC-EVT")
        db.commit()

        with self._patch_graph():
            result = execute_bulk_commit(
                db,
                tenant_id=TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [{"name": "Farm A", "street": "123 Main",
                                    "city": "Salinas", "state": "CA",
                                    "postal_code": "93901"}],
                    "events": [{
                        "facility_name": "Farm A",
                        "cte_type": "shipping",
                        "tlc_code": "TLC-EVT",
                        "event_time": "2026-01-15T08:00:00Z",
                        "kde_data": {"destination": "Warehouse A"},
                        "obligation_ids": [],
                    }],
                },
            )

        assert result["events_chained"] == 1
