"""Backward-compatibility shim — code moved to fda_export/ package."""
from services.ingestion.app.fda_export.router import router  # noqa: F401

# Re-export helpers that existing callers (tests) import from here.
from app.fda_export_service import _generate_csv  # noqa: F401
