"""
Tests for CTE persistence cluster fixes:
  #1323 — product_description excluded from event hash
  #1324 — critical alerts produce validation_status='rejected'
  #1334 — append-only migration SQL present
  #1335 — module header no longer contains the word LEGACY
"""
from __future__ import annotations

import hashlib
import inspect
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# ── Module paths ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
HASHING_PY = REPO_ROOT / "services" / "shared" / "cte_persistence" / "hashing.py"
CORE_PY = REPO_ROOT / "services" / "shared" / "cte_persistence" / "core.py"
MIGRATION_DIR = REPO_ROOT / "alembic" / "sql"

# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_hash(
    product_description: str = "Organic Romaine Lettuce",
    kdes: Optional[Dict[str, Any]] = None,
) -> str:
    """Call compute_event_hash with a fixed event, varying only product_description."""
    from services.shared.cte_persistence.hashing import compute_event_hash
    return compute_event_hash(
        event_id="evt-001",
        event_type="harvesting",
        tlc="TLC-2024-ABC",
        product_description=product_description,
        quantity=100.0,
        unit_of_measure="kg",
        location_gln="0614141000005",
        location_name=None,
        timestamp="2024-01-15T08:00:00+00:00",
        kdes=kdes or {},
    )


# ============================================================
# #1323 — product_description must NOT affect the event hash
# ============================================================

class TestHashStability:
    def test_same_hash_for_different_product_description(self):
        """The same event with a reformatted description must produce the same hash."""
        h1 = _make_hash("Organic Romaine Lettuce")
        h2 = _make_hash("organic romaine lettuce")  # lowercase reformat
        h3 = _make_hash("Lechuga Romana Orgánica")  # translated
        h4 = _make_hash("")                          # empty

        assert h1 == h2, "case-reformatted description changed hash"
        assert h1 == h3, "translated description changed hash"
        assert h1 == h4, "empty description changed hash"

    def test_different_event_type_gives_different_hash(self):
        """Stable fields still differentiate events."""
        from services.shared.cte_persistence.hashing import compute_event_hash
        h_harv = compute_event_hash(
            "evt-001", "harvesting", "TLC-X", "", 10.0, "kg", None, None,
            "2024-01-01T00:00:00+00:00", {},
        )
        h_ship = compute_event_hash(
            "evt-001", "shipping", "TLC-X", "", 10.0, "kg", None, None,
            "2024-01-01T00:00:00+00:00", {},
        )
        assert h_harv != h_ship

    def test_different_tlc_gives_different_hash(self):
        """TLC change must still produce a different hash."""
        from services.shared.cte_persistence.hashing import compute_event_hash
        h1 = compute_event_hash(
            "evt-001", "harvesting", "TLC-A", "desc", 10.0, "kg", None, None,
            "2024-01-01T00:00:00+00:00", {},
        )
        h2 = compute_event_hash(
            "evt-001", "harvesting", "TLC-B", "desc", 10.0, "kg", None, None,
            "2024-01-01T00:00:00+00:00", {},
        )
        assert h1 != h2

    def test_kde_product_description_key_excluded_from_hash(self):
        """KDE values under description-like keys must not affect the hash."""
        h1 = _make_hash(kdes={"product_description": "Romaine", "lot_info": "A1"})
        h2 = _make_hash(kdes={"product_description": "ROMAINE LETTUCE", "lot_info": "A1"})
        assert h1 == h2, "KDE product_description key should be stripped from hash"

    def test_non_description_kde_values_do_affect_hash(self):
        """Non-description KDE values MUST differentiate events."""
        h1 = _make_hash(kdes={"lot_info": "batch-A"})
        h2 = _make_hash(kdes={"lot_info": "batch-B"})
        assert h1 != h2, "lot_info KDE change should produce different hash"


# ============================================================
# #1324 — critical alerts → validation_status='rejected'
# ============================================================

class TestValidationStatus:
    def _call_derive(self, alerts: List[Dict[str, Any]]) -> str:
        from services.shared.cte_persistence.core import _derive_validation_status
        return _derive_validation_status(alerts)

    def test_no_alerts_gives_valid(self):
        assert self._call_derive([]) == "valid"

    def test_warning_alert_gives_warning(self):
        alerts = [{"alert_type": "temperature_excursion", "severity": "warning"}]
        assert self._call_derive(alerts) == "warning"

    def test_critical_severity_gives_rejected(self):
        alerts = [{"alert_type": "temperature_excursion", "severity": "critical"}]
        assert self._call_derive(alerts) == "rejected"

    def test_missing_required_kde_alert_type_gives_rejected(self):
        alerts = [{"alert_type": "missing_required_kde", "severity": "warning"}]
        assert self._call_derive(alerts) == "rejected"

    def test_mixed_alerts_critical_wins(self):
        """Even if one alert is warning, a critical one forces rejected."""
        alerts = [
            {"alert_type": "deadline_approaching", "severity": "warning"},
            {"alert_type": "missing_required_kde", "severity": "critical"},
        ]
        assert self._call_derive(alerts) == "rejected"

    def test_store_event_writes_rejected_for_critical_alert(self):
        """store_event passes critical alerts → validation_status='rejected' in INSERT."""
        from services.shared.cte_persistence.core import CTEPersistence

        # Track what validation_status gets written
        captured_params: Dict[str, Any] = {}
        call_count = 0

        def fake_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result_mock = MagicMock()
            result_mock.fetchone.return_value = None
            result_mock.fetchall.return_value = []
            if params and "validation_status" in (params or {}):
                captured_params.update(params)
            return result_mock

        session = MagicMock()
        session.execute.side_effect = fake_execute
        session.begin_nested.return_value.__enter__ = MagicMock(return_value=MagicMock())
        session.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        persistence = CTEPersistence(session)
        alerts = [{"alert_type": "missing_required_kde", "severity": "critical", "message": "no harvest_date"}]

        persistence.store_event(
            tenant_id="tenant-111",
            event_type="harvesting",
            traceability_lot_code="TLC-TEST-001",
            product_description="Test Lettuce",
            quantity=50.0,
            unit_of_measure="kg",
            event_timestamp="2024-06-01T12:00:00+00:00",
            alerts=alerts,
        )

        assert captured_params.get("validation_status") == "rejected", (
            f"Expected 'rejected', got {captured_params.get('validation_status')!r}"
        )


# ============================================================
# #1334 — migration file with append-only triggers exists
# ============================================================

class TestAppendOnlyMigration:
    def _find_migration(self) -> Optional[Path]:
        """Find V053 migration (or any migration referencing prevent_cte_mutation)."""
        # First try the expected filename
        candidate = MIGRATION_DIR / "V053__cte_append_only_triggers.sql"
        if candidate.exists():
            return candidate
        # Fallback: scan all SQL files
        for p in sorted(MIGRATION_DIR.glob("V*.sql")):
            if "prevent_cte_mutation" in p.read_text():
                return p
        return None

    def test_migration_file_exists(self):
        migration = self._find_migration()
        assert migration is not None, (
            "No migration file found containing prevent_cte_mutation(). "
            "Expected alembic/sql/V053__cte_append_only_triggers.sql"
        )

    def test_migration_covers_cte_events(self):
        migration = self._find_migration()
        assert migration is not None
        sql = migration.read_text()
        assert "fsma.cte_events" in sql, "Migration must create trigger on fsma.cte_events"

    def test_migration_covers_hash_chain(self):
        migration = self._find_migration()
        assert migration is not None
        sql = migration.read_text()
        assert "fsma.hash_chain" in sql, "Migration must create trigger on fsma.hash_chain"

    def test_migration_has_allow_mutation_escape_hatch(self):
        migration = self._find_migration()
        assert migration is not None
        sql = migration.read_text()
        assert "allow_mutation" in sql, (
            "Migration must include the fsma.allow_mutation GUC escape hatch "
            "so authorized corrections are possible"
        )

    def test_trigger_function_raises_on_mutation(self):
        """Trigger function body must raise EXCEPTION (not just return NULL)."""
        migration = self._find_migration()
        assert migration is not None
        sql = migration.read_text()
        assert "RAISE EXCEPTION" in sql


# ============================================================
# #1335 — module header must not say LEGACY
# ============================================================

class TestNoLegacyLabel:
    def test_core_module_header_not_legacy(self):
        """The module-level comment block must not label this module as LEGACY."""
        source = CORE_PY.read_text()
        # Check the first 40 lines (the module header / comment block)
        header = "\n".join(source.splitlines()[:40])
        assert "LEGACY" not in header, (
            "core.py module header still contains 'LEGACY' — remove the misleading label "
            "(the module is actively written; see #1335)"
        )

    def test_hashing_module_no_legacy_in_function_names(self):
        """No function in hashing.py should be named with 'legacy' in it."""
        from services.shared.cte_persistence import hashing
        legacy_funcs = [
            name for name in dir(hashing)
            if "legacy" in name.lower() and callable(getattr(hashing, name))
        ]
        assert not legacy_funcs, f"hashing.py has legacy-named functions: {legacy_funcs}"

    def test_dual_write_reconciliation_marker_present(self):
        """DUAL_WRITE_RECONCILIATION_NEEDED constant must exist in core.py."""
        from services.shared.cte_persistence import core
        assert hasattr(core, "DUAL_WRITE_RECONCILIATION_NEEDED"), (
            "core.py must export DUAL_WRITE_RECONCILIATION_NEEDED = True "
            "as a machine-findable marker per #1335"
        )
        assert core.DUAL_WRITE_RECONCILIATION_NEEDED is True
