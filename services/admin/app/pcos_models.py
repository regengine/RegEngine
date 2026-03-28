"""
Backward compatibility shim for PCOS models.

Models have been moved to the app.pcos package. This module re-exports
everything for compatibility with existing imports.

MIGRATION NOTE:
  Old: from app.pcos_models import SomeModel
  New: from app.pcos import SomeModel (preferred)
  Old still works via this shim.
"""

# Re-export everything from the new package
from app.pcos import *  # noqa: F401,F403
