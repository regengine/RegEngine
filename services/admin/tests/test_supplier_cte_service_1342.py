"""
Regression coverage for ``app/supplier_cte_service.py`` — closes the 93 -> 100%
gap flagged by coverage sweep #1342.

The supplier CTE service is the hash-chained, per-tenant write path for
supplier-contributed FSMA 204 events: any regression in the naive-datetime
normalization, the tenant-not-found guard, the empty-TLC guard, or the
canonical-bridge success path silently corrupts the Merkle chain or lets
unusable rows pierce the pipeline. We pin five missing lines from the
baseline coverage survey:

* Line 35  — ``_iso_utc`` returns an ISO-8601 string with ``+00:00`` appended
             for naive datetimes (``tzinfo is None`` branch). Without this,
             supplier-submitted ``event_time`` strings would be hashed as
             "naive-UTC" in one call and tz-aware in the next, breaking
             ``payload_sha256`` reproducibility.
* Line 43  — ``_as_utc`` attaches ``timezone.utc`` to naive datetimes rather
             than dropping them or coercing astimezone(). A failure here
             would emit events with `tzinfo=None` through to ``_iso_utc``
             and ``SupplierCTEEventModel.event_time`` storage.
* Line 67  — ``_acquire_tenant_merkle_lock`` raises HTTP 400 "Tenant not
             found" when the SELECT ... FOR UPDATE returns no row. This
             guard prevents a cross-tenant or deleted-tenant write from
             extending someone else's Merkle chain (#1251 chain-lock is
             keyed on tenant_id, so a missing tenant is a hard stop).
* Line 145 — ``_bridge_to_canonical`` logs ``supplier_cte_canonical_bridged``
             on the happy path (after ``CanonicalEventStore.persist_event``
             returns). This is the FDA-export / compliance-scoring wiring;
             if this branch silently never runs, supplier events never
             reach the canonical TraceabilityEvent pipeline.
* Line 178 — ``_persist_supplier_cte_event`` raises HTTP 400 "tlc_code is
             required" when ``tlc_code.strip()`` is empty. Without this
             guard, an empty-string TLC would write a
             ``SupplierTraceabilityLotModel`` with no business key — any
             lookup would then collide across tenants.

Tests use mocked SQLAlchemy sessions and monkeypatched imports so they run
without a live Postgres (the production path uses ``SELECT ... FOR UPDATE``
which SQLite cannot honor).

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Standardized bootstrap so ``from app...`` resolves against this service's
# app/ and ``from shared...`` resolves the sibling shared package. The
# admin service's conftest.py does the same, but we duplicate here so the
# module imports survive even when the file is run standalone.
_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fastapi import HTTPException  # noqa: E402

import app.supplier_cte_service as cte_service  # noqa: E402
from app.supplier_cte_service import (  # noqa: E402
    _acquire_tenant_merkle_lock,
    _as_utc,
    _bridge_to_canonical,
    _iso_utc,
    _normalize_supplier_cte_type,
    _persist_supplier_cte_event,
)


TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000001342")


# ---------------------------------------------------------------------------
# Line 35 — ``_iso_utc`` naive-datetime branch
# ---------------------------------------------------------------------------


class TestIsoUtcNaiveBranch:

    def test_naive_datetime_is_stamped_as_utc_isoformat(self):
        """A naive datetime (``tzinfo is None``) must be treated as UTC and
        emitted with ``+00:00`` so the ``payload_sha256`` is reproducible
        regardless of the caller's local timezone."""
        naive = datetime(2026, 4, 20, 13, 45, 0)  # no tzinfo
        result = _iso_utc(naive)
        assert result == "2026-04-20T13:45:00+00:00"

    def test_aware_datetime_is_normalized_to_utc(self):
        """An aware datetime must be ``astimezone(UTC)``'d, NOT re-stamped
        as UTC. Pins that line 35 is the ``is None`` branch and line 36
        is the else branch, so neither corrupts the other."""
        aware_est = datetime(
            2026, 4, 20, 9, 45, 0, tzinfo=timezone(timedelta(hours=-4))
        )
        result = _iso_utc(aware_est)
        # 09:45 EDT -> 13:45 UTC
        assert result == "2026-04-20T13:45:00+00:00"


# ---------------------------------------------------------------------------
# Line 43 — ``_as_utc`` naive-datetime branch
# ---------------------------------------------------------------------------


class TestAsUtcNaiveBranch:

    def test_naive_datetime_gets_utc_tzinfo_attached(self):
        """A naive datetime must gain ``tzinfo=UTC`` via ``.replace`` —
        NOT via ``astimezone`` which would mis-shift by the local
        offset."""
        naive = datetime(2026, 4, 20, 13, 45, 0)
        result = _as_utc(naive)
        assert result is not None
        assert result.tzinfo is timezone.utc
        # Wall-clock components unchanged by the UTC stamping.
        assert (result.year, result.month, result.day) == (2026, 4, 20)
        assert (result.hour, result.minute, result.second) == (13, 45, 0)

    def test_aware_datetime_is_converted_to_utc(self):
        """An aware datetime is converted via ``astimezone`` — pins line
        43 (naive branch) versus line 44 (aware branch)."""
        aware_pst = datetime(
            2026, 4, 20, 6, 45, 0, tzinfo=timezone(timedelta(hours=-7))
        )
        result = _as_utc(aware_pst)
        assert result is not None
        assert result.tzinfo == timezone.utc
        # 06:45 PDT -> 13:45 UTC
        assert (result.hour, result.minute) == (13, 45)

    def test_none_short_circuits(self):
        """``None`` input returns ``None`` without touching the naive
        branch — pins the early-return guard above line 43."""
        assert _as_utc(None) is None


# ---------------------------------------------------------------------------
# Line 67 — ``_acquire_tenant_merkle_lock`` tenant-not-found branch
# ---------------------------------------------------------------------------


class TestAcquireTenantMerkleLockMissingTenant:

    def test_missing_tenant_raises_http_400(self):
        """When the ``SELECT ... FOR UPDATE`` on the tenant row returns
        ``None``, the lock acquisition must raise HTTPException(400)
        rather than silently extending another tenant's Merkle chain."""
        session = MagicMock()
        # execute(...).scalar_one_or_none() -> None  (tenant row absent)
        session.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(HTTPException) as excinfo:
            _acquire_tenant_merkle_lock(session, TENANT_ID)

        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "Tenant not found"

    def test_present_tenant_returns_silently(self):
        """When the tenant row exists, the function returns ``None``
        (no exception). Pins line 67 as the negative branch only."""
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = TENANT_ID

        # Must not raise.
        assert _acquire_tenant_merkle_lock(session, TENANT_ID) is None


# ---------------------------------------------------------------------------
# Line 145 — ``_bridge_to_canonical`` happy-path info log
# ---------------------------------------------------------------------------


class _FakeCanonicalEventStore:
    """Stand-in for ``shared.canonical_persistence.CanonicalEventStore``
    that records calls instead of touching a DB. We replace the class
    on the imported module so the ``from shared.canonical_persistence
    import CanonicalEventStore`` inside ``_bridge_to_canonical``
    resolves to this stub."""

    instances: list["_FakeCanonicalEventStore"] = []

    def __init__(self, session, dual_write: bool = True):
        self.session = session
        self.dual_write = dual_write
        self.persisted: list = []
        _FakeCanonicalEventStore.instances.append(self)

    def persist_event(self, canonical_event):
        self.persisted.append(canonical_event)
        return None


@pytest.fixture
def reset_fake_store():
    _FakeCanonicalEventStore.instances = []
    yield
    _FakeCanonicalEventStore.instances = []


class TestBridgeToCanonicalHappyPath:

    def test_success_path_logs_bridged_info(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        reset_fake_store,
    ):
        """On success, ``_bridge_to_canonical`` emits a structured
        ``supplier_cte_canonical_bridged`` INFO log with the supplier
        event id, canonical event id, and tenant id — line 145's log
        call is the only observable signal that the bridge actually
        ran, so we pin it by asserting the record lands in caplog."""
        import shared.canonical_persistence as cp_mod

        monkeypatch.setattr(cp_mod, "CanonicalEventStore", _FakeCanonicalEventStore)

        # Also patch the attribute in sys.modules' ``shared.canonical_persistence``
        # submodule so a ``from shared.canonical_persistence import
        # CanonicalEventStore`` at call-time resolves to the fake.
        import shared.canonical_persistence.writer as cp_writer
        monkeypatch.setattr(
            cp_writer, "CanonicalEventStore", _FakeCanonicalEventStore
        )

        event = MagicMock()
        event.id = uuid.UUID("00000000-0000-0000-0000-000000000aaa")
        event.cte_type = "shipping"
        event.event_time = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)

        facility = MagicMock()
        facility.id = uuid.UUID("00000000-0000-0000-0000-000000000bbb")
        # No ``gln`` attribute -> the bridge falls back to str(facility.id).
        del facility.gln

        with caplog.at_level(logging.INFO, logger="supplier-canonical-bridge"):
            _bridge_to_canonical(
                db=MagicMock(),
                tenant_id=TENANT_ID,
                event=event,
                facility=facility,
                tlc_code="TLC-2026-1342-001",
                kde_data={
                    "product_description": "Baby Spinach",
                    "quantity": 120,
                    "unit_of_measure": "cases",
                },
            )

        # The fake store was instantiated and persist_event was called.
        assert len(_FakeCanonicalEventStore.instances) == 1
        store = _FakeCanonicalEventStore.instances[0]
        assert len(store.persisted) == 1

        # Line 145 fired -> exactly one INFO record with the bridged msg.
        bridged = [
            r for r in caplog.records
            if r.name == "supplier-canonical-bridge"
            and r.levelno == logging.INFO
            and r.message == "supplier_cte_canonical_bridged"
        ]
        assert len(bridged) == 1
        record = bridged[0]
        # The ``extra={...}`` attaches these as log-record attributes.
        assert getattr(record, "supplier_event_id") == str(event.id)
        assert getattr(record, "tenant_id") == str(TENANT_ID)
        # canonical_event_id is the UUID prepare_for_persistence finalized.
        assert isinstance(getattr(record, "canonical_event_id"), str)

    def test_failure_path_swallows_and_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        reset_fake_store,
    ):
        """Counterpart to line 145 — line 153/154 warn-and-continue. A
        raising ``CanonicalEventStore`` must not propagate; the supplier
        write is authoritative even if the canonical bridge is down."""

        class _ExplodingStore:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError("canonical pipeline offline")

        import shared.canonical_persistence as cp_mod
        import shared.canonical_persistence.writer as cp_writer

        monkeypatch.setattr(cp_mod, "CanonicalEventStore", _ExplodingStore)
        monkeypatch.setattr(cp_writer, "CanonicalEventStore", _ExplodingStore)

        event = MagicMock()
        event.id = uuid.UUID("00000000-0000-0000-0000-000000000ccc")
        event.cte_type = "receiving"
        event.event_time = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
        facility = MagicMock()
        facility.id = uuid.UUID("00000000-0000-0000-0000-000000000ddd")

        with caplog.at_level(logging.WARNING, logger="supplier-canonical-bridge"):
            # Must NOT raise.
            _bridge_to_canonical(
                db=MagicMock(),
                tenant_id=TENANT_ID,
                event=event,
                facility=facility,
                tlc_code="TLC-1342-002",
                kde_data={},
            )

        failed = [
            r for r in caplog.records
            if r.name == "supplier-canonical-bridge"
            and r.levelno == logging.WARNING
            and r.message == "supplier_canonical_bridge_failed"
        ]
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# Line 178 — ``_persist_supplier_cte_event`` empty-TLC guard
# ---------------------------------------------------------------------------


class TestPersistSupplierCteEventEmptyTlc:

    def _mk_user(self):
        u = MagicMock()
        u.id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
        return u

    def _mk_facility(self):
        f = MagicMock()
        f.id = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
        return f

    def test_empty_string_tlc_raises_http_400(self):
        """``tlc_code=""`` must raise HTTPException(400) before any DB
        write — pins the guard so we never insert a
        ``SupplierTraceabilityLotModel`` with an empty business key."""
        session = MagicMock()
        with pytest.raises(HTTPException) as excinfo:
            _persist_supplier_cte_event(
                session,
                tenant_id=TENANT_ID,
                current_user=self._mk_user(),
                facility=self._mk_facility(),
                cte_type="shipping",
                tlc_code="",
                event_time=datetime(2026, 4, 20, tzinfo=timezone.utc),
                kde_data={},
                obligation_ids=[],
            )
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "tlc_code is required"

        # No DB operations attempted -- pins that line 178 fires BEFORE
        # the lot SELECT on line 192.
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_whitespace_only_tlc_raises_http_400(self):
        """``tlc_code=" \\t "`` strips to ``""`` and must hit the same
        guard — pins the ``.strip()`` normalization in line 176."""
        session = MagicMock()
        with pytest.raises(HTTPException) as excinfo:
            _persist_supplier_cte_event(
                session,
                tenant_id=TENANT_ID,
                current_user=self._mk_user(),
                facility=self._mk_facility(),
                cte_type="shipping",
                tlc_code="   \t  ",
                event_time=None,
                kde_data={},
                obligation_ids=[],
            )
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "tlc_code is required"
        session.add.assert_not_called()

    def test_unsupported_cte_type_raises_first(self):
        """Counterpart guard (line 174): pins that an unsupported
        ``cte_type`` is rejected with its own detail message, not
        conflated with the TLC guard."""
        session = MagicMock()
        with pytest.raises(HTTPException) as excinfo:
            _persist_supplier_cte_event(
                session,
                tenant_id=TENANT_ID,
                current_user=self._mk_user(),
                facility=self._mk_facility(),
                cte_type="telepathy",
                tlc_code="TLC-OK-1342",
                event_time=None,
                kde_data={},
                obligation_ids=[],
            )
        assert excinfo.value.status_code == 400
        assert "Unsupported cte_type" in excinfo.value.detail


class TestSupplierCteTypeAliases:

    def test_canonical_transformation_alias_maps_to_supplier_type(self):
        assert _normalize_supplier_cte_type("transformation") == "transforming"

    def test_canonical_first_land_based_receiving_alias_maps_to_supplier_type(self):
        assert _normalize_supplier_cte_type("first_land_based_receiving") == "first_receiver"


# Tracks GitHub issue #1342.
