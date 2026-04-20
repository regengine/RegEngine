"""
Tests for canonical_persistence.schema_bootstrap (#1293).

Verifies:
- The module is importable by its new name (schema_bootstrap, not migration).
- The module docstring contains "NOT an Alembic migration" so future
  contributors cannot mistake it for an Alembic step.
- The bootstrap() function exists and is callable (dry-run with a mock engine).
"""
from __future__ import annotations

import importlib
import types
from unittest.mock import MagicMock, call, patch


def test_module_importable_by_new_name():
    """schema_bootstrap is importable; the old name 'migration' is gone."""
    import shared.canonical_persistence.schema_bootstrap as sb  # noqa: F401

    assert isinstance(sb, types.ModuleType)


def test_docstring_contains_not_an_alembic_migration():
    """Module docstring must contain the phrase 'NOT an Alembic migration'."""
    import shared.canonical_persistence.schema_bootstrap as sb

    assert sb.__doc__ is not None, "schema_bootstrap must have a module docstring"
    assert "NOT an Alembic migration" in sb.__doc__, (
        "Docstring must contain 'NOT an Alembic migration' to prevent "
        "developers from adding this file to Alembic version history."
    )


def test_bootstrap_function_exists():
    """bootstrap() must be a callable exported from the module."""
    import shared.canonical_persistence.schema_bootstrap as sb

    assert callable(sb.bootstrap), "schema_bootstrap.bootstrap must be callable"


def test_bootstrap_executes_all_statements():
    """bootstrap() must call conn.execute() for each SQL statement."""
    import shared.canonical_persistence.schema_bootstrap as sb

    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    # text() is imported inside bootstrap(); patch at the sqlalchemy source
    with patch("sqlalchemy.text", side_effect=lambda s: s):
        sb.bootstrap(mock_engine)

    assert mock_conn.execute.call_count == len(sb._BOOTSTRAP_SQL), (
        f"Expected {len(sb._BOOTSTRAP_SQL)} execute() calls, "
        f"got {mock_conn.execute.call_count}"
    )


def test_migration_module_removed():
    """The old 'migration' module must no longer exist (renamed to legacy_shim)."""
    import importlib
    import sys

    # Ensure we're not seeing a cached import
    sys.modules.pop("shared.canonical_persistence.migration", None)

    try:
        importlib.import_module("shared.canonical_persistence.migration")
        imported = True
    except ImportError:
        imported = False

    assert not imported, (
        "shared.canonical_persistence.migration still importable — "
        "it should have been removed (renamed to legacy_shim) in #1293."
    )
