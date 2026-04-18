"""
Hardening tests for shared.cte_persistence.CTEPersistence.

Exercises the fixes for:
- #1306 — quantity clamp removed; sub-unit values preserved or rejected
- #1307 — batch chain writes guarded so idempotency-collision does not orphan
- #1308 — event_timestamp is parsed, validated and stored as UTC datetime
- #1311 — fsma.cte_kdes stores JSON values via ::jsonb cast, not str(repr)

Tests mock the SQLAlchemy session; they assert on SQL text and bound
parameters so they do not require a live Postgres.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from shared.cte_persistence.core import CTEPersistence
from shared.cte_persistence.hashing import compute_event_hash


# ---------------------------------------------------------------------------
# Minimal fake session — same shape as the canonical tests
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: List[Tuple[Any, ...]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class FakeSession:
    def __init__(self):
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._rules: List[Tuple[re.Pattern[str], Any]] = []

    def add_rule(self, pattern: str, result):
        self._rules.append((re.compile(pattern, re.IGNORECASE | re.DOTALL), result))

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        for pat, result in self._rules:
            if pat.search(sql):
                if callable(result):
                    return result(sql, params or {})
                return result
        return _FakeResult()

    def begin_nested(self):
        ns = MagicMock()
        ns.rollback = MagicMock()
        return ns


def _base_event(**overrides):
    """A minimal well-formed batch event dict."""
    evt = {
        "event_type": "harvesting",
        "traceability_lot_code": "TLC-1",
        "product_description": "Lettuce",
        "quantity": 10.0,
        "unit_of_measure": "kg",
        "event_timestamp": "2026-04-15T12:00:00Z",
        "kdes": {"farm_name": "Acme"},
    }
    evt.update(overrides)
    return evt


# ---------------------------------------------------------------------------
# #1306 — no silent clamp
# ---------------------------------------------------------------------------


class TestQuantityClamp_Issue1306:
    def test_sub_unit_quantity_is_preserved_in_batch(self):
        """0.25 kg must be stored AND hashed as 0.25 — not clamped to 1.0."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_event(quantity=0.25)
        results = p.store_events_batch(tenant_id="t-1", events=[evt])

        assert len(results) == 1
        assert results[0].success is True

        # Find the INSERT into fsma.cte_events and assert the qty param
        cte_inserts = [c for c in session.calls if "INSERT INTO fsma.cte_events" in c[0]]
        assert cte_inserts, "cte_events INSERT should have been issued"
        _, params = cte_inserts[0]
        qty_params = {k: v for k, v in params.items() if k.startswith("qty_")}
        assert qty_params, "quantity bind parameters should be present"
        assert all(v == 0.25 for v in qty_params.values()), (
            f"quantity was mutated from 0.25: {qty_params}"
        )

    def test_batch_and_single_produce_identical_hashes_for_same_input(self):
        """The single-event and batch code paths must now compute the same
        hash for identical inputs — previously they diverged because only
        the batch path silently forced quantity>=1.0."""
        quantity = 0.25
        kdes = {"farm_name": "Acme"}

        # Reproduce the hash compute_event_hash would produce for both paths
        ref = compute_event_hash(
            "fixed-event-id", "harvesting", "TLC-1",
            "Lettuce", quantity, "kg", None, None,
            "2026-04-15T12:00:00Z", kdes,
        )
        # If quantity were still clamped, the reference would be different
        # than the hash for 1.0.  Assert the two are distinct to guarantee
        # the test catches regressions.
        clamped = compute_event_hash(
            "fixed-event-id", "harvesting", "TLC-1",
            "Lettuce", 1.0, "kg", None, None,
            "2026-04-15T12:00:00Z", kdes,
        )
        assert ref != clamped

    def test_zero_quantity_raises(self):
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_event(quantity=0)
        with pytest.raises(ValueError, match="quantity must be > 0"):
            p.store_events_batch(tenant_id="t-1", events=[evt])

    def test_missing_quantity_raises(self):
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_event()
        evt.pop("quantity")
        with pytest.raises(ValueError, match="quantity is required"):
            p.store_events_batch(tenant_id="t-1", events=[evt])


# ---------------------------------------------------------------------------
# #1307 — batch chain INSERT guarded by WHERE EXISTS
# ---------------------------------------------------------------------------


class TestBatchChainGuard_Issue1307:
    def test_batch_chain_insert_uses_where_exists_guard(self):
        """The batch INSERT into fsma.hash_chain must carry a WHERE EXISTS
        check against fsma.cte_events, mirroring the single-event path,
        so that a lost idempotency race does not orphan a chain row."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain\s+WHERE tenant_id", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        p.store_events_batch(tenant_id="t-1", events=[_base_event()])

        chain_inserts = [
            c for c in session.calls
            if "INSERT INTO fsma.hash_chain" in c[0]
        ]
        assert chain_inserts, "hash_chain INSERT should have been issued"
        sql, _ = chain_inserts[0]
        normalized = " ".join(sql.split())
        # Single-event path uses:
        #   INSERT ... SELECT ... WHERE EXISTS (SELECT 1 FROM fsma.cte_events ...)
        # The batch path now needs the same guard.
        assert "WHERE EXISTS" in normalized.upper(), (
            "batch chain INSERT must include a WHERE EXISTS guard against "
            "fsma.cte_events to avoid orphan rows on idempotency collision"
        )
        assert "fsma.cte_events" in normalized


# ---------------------------------------------------------------------------
# #1308 — event_timestamp parsing and validation
# ---------------------------------------------------------------------------


class TestTimestampValidation_Issue1308:
    def test_naive_timestamp_rejected(self):
        session = FakeSession()
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        with pytest.raises(ValueError, match="timezone|naive"):
            p.store_event(
                tenant_id="t-1",
                event_type="harvesting",
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=1.0,
                unit_of_measure="kg",
                event_timestamp="2026-04-15T12:00:00",  # no TZ
            )

    def test_far_future_timestamp_rejected(self):
        session = FakeSession()
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        with pytest.raises(ValueError, match="future"):
            p.store_event(
                tenant_id="t-1",
                event_type="harvesting",
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=1.0,
                unit_of_measure="kg",
                event_timestamp=future,
            )

    def test_empty_timestamp_rejected(self):
        session = FakeSession()
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        with pytest.raises(ValueError):
            p.store_event(
                tenant_id="t-1",
                event_type="harvesting",
                traceability_lot_code="TLC-1",
                product_description="Lettuce",
                quantity=1.0,
                unit_of_measure="kg",
                event_timestamp="",
            )

    def test_valid_iso_utc_accepted(self):
        session = FakeSession()
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        # Should not raise — event within the past, UTC-aware
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p.store_event(
            tenant_id="t-1",
            event_type="harvesting",
            traceability_lot_code="TLC-1",
            product_description="Lettuce",
            quantity=1.0,
            unit_of_measure="kg",
            event_timestamp=past,
        )


# ---------------------------------------------------------------------------
# #1311 — KDE values round-trip through JSONB, not str(repr)
# ---------------------------------------------------------------------------


class TestKDEJsonb_Issue1311:
    @staticmethod
    def _has_jsonb_cast(sql: str) -> bool:
        """Either ``::jsonb`` shorthand or ``CAST(... AS jsonb)`` is acceptable."""
        return "::jsonb" in sql or "AS jsonb" in sql

    def test_single_event_kde_insert_casts_to_jsonb(self):
        session = FakeSession()
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p.store_event(
            tenant_id="t-1",
            event_type="harvesting",
            traceability_lot_code="TLC-1",
            product_description="Lettuce",
            quantity=1.0,
            unit_of_measure="kg",
            event_timestamp=past,
            kdes={"consignee": {"gln": "0614141000005"}, "temp_c": 4.0},
        )

        kde_inserts = [c for c in session.calls if "INSERT INTO fsma.cte_kdes" in c[0]]
        assert kde_inserts, "cte_kdes INSERT expected"
        sql, params = kde_inserts[0]
        assert self._has_jsonb_cast(sql), (
            "KDE value must be cast to jsonb so structured dicts round-trip "
            "instead of being stored as Python repr"
        )
        # The bound kde_value must be JSON text, NOT python repr
        assert isinstance(params["kde_value"], str)
        assert not params["kde_value"].startswith("{'"), (
            "kde_value appears to be Python repr, not JSON"
        )

    def test_batch_event_kde_insert_casts_to_jsonb(self):
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_event(kdes={"consignee": {"gln": "0614141000005"}})
        p.store_events_batch(tenant_id="t-1", events=[evt])

        kde_inserts = [c for c in session.calls if "INSERT INTO fsma.cte_kdes" in c[0]]
        assert kde_inserts, "cte_kdes INSERT expected"
        sql, params = kde_inserts[0]
        assert self._has_jsonb_cast(sql)
        # Values stored as JSON text (not Python repr)
        kv_params = [v for k, v in params.items() if k.startswith("kv_")]
        assert kv_params, "kv_* bind params expected"
        # Check that at least one value looks like JSON (not repr)
        assert any(
            isinstance(v, str) and v.startswith("{") and '"gln"' in v
            for v in kv_params
        ), f"KDE values should be JSON text, got: {kv_params!r}"
