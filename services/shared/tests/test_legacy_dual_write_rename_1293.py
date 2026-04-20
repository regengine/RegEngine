"""
Tests for #1293: canonical_persistence/migration.py rename to legacy_dual_write.py.

Verifies:
  - Import from legacy_dual_write works.
  - Import from migration (deprecated shim) still works with a DeprecationWarning.
  - validate_tables_exist raises RuntimeError when tables are absent.
  - validate_tables_exist passes when tables are present.
"""
from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

def test_legacy_dual_write_importable():
    """The canonical module name imports without error."""
    from shared.canonical_persistence import legacy_dual_write  # noqa: F401
    from shared.canonical_persistence.legacy_dual_write import (  # noqa: F401
        validate_tables_exist,
        dual_write_legacy,
        publish_graph_sync,
        stage_graph_sync,
    )


def test_migration_shim_importable_with_deprecation_warning():
    """The old 'migration' name still imports but emits a DeprecationWarning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from shared.canonical_persistence import migration  # noqa: F401

    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecation_warnings, "Expected a DeprecationWarning from the migration shim"
    msg = str(deprecation_warnings[0].message)
    assert "legacy_dual_write" in msg, f"Warning should mention legacy_dual_write, got: {msg}"
    assert "1293" in msg, f"Warning should reference issue #1293, got: {msg}"


# ---------------------------------------------------------------------------
# validate_tables_exist tests
# ---------------------------------------------------------------------------

def _make_inspector(present_tables: dict[str, list[str]]) -> MagicMock:
    """Return a mock SQLAlchemy Inspector that reports the given tables."""
    inspector = MagicMock()
    inspector.get_table_names.side_effect = lambda schema=None: present_tables.get(schema, [])
    return inspector


def test_validate_tables_exist_raises_when_tables_missing():
    """validate_tables_exist raises RuntimeError with a helpful message on fresh DB."""
    from shared.canonical_persistence.legacy_dual_write import validate_tables_exist

    mock_engine = MagicMock()
    empty_inspector = _make_inspector({})

    with patch("shared.canonical_persistence.legacy_dual_write.sa_inspect", return_value=empty_inspector):
        with pytest.raises(RuntimeError) as exc_info:
            validate_tables_exist(mock_engine)

    msg = str(exc_info.value)
    assert "run Alembic migrations first" in msg, f"Expected migration hint in error, got: {msg}"
    assert "alembic/versions" in msg, f"Expected alembic/versions hint, got: {msg}"
    # At least one required table should be named in the error.
    assert "fsma." in msg


def test_validate_tables_exist_passes_when_all_tables_present():
    """validate_tables_exist does not raise when required tables exist."""
    from shared.canonical_persistence.legacy_dual_write import validate_tables_exist

    mock_engine = MagicMock()
    full_inspector = _make_inspector({
        "fsma": ["traceability_events", "cte_events", "cte_kdes"],
    })

    with patch("shared.canonical_persistence.legacy_dual_write.sa_inspect", return_value=full_inspector):
        # Should not raise.
        validate_tables_exist(mock_engine)


def test_validate_tables_exist_raises_when_partially_missing():
    """validate_tables_exist reports all missing tables, not just the first."""
    from shared.canonical_persistence.legacy_dual_write import validate_tables_exist

    mock_engine = MagicMock()
    # Only cte_events present; traceability_events and cte_kdes absent.
    partial_inspector = _make_inspector({
        "fsma": ["cte_events"],
    })

    with patch("shared.canonical_persistence.legacy_dual_write.sa_inspect", return_value=partial_inspector):
        with pytest.raises(RuntimeError) as exc_info:
            validate_tables_exist(mock_engine)

    msg = str(exc_info.value)
    assert "traceability_events" in msg
    assert "cte_kdes" in msg
    # cte_events IS present — should not appear in the error.
    assert "fsma.cte_events" not in msg
