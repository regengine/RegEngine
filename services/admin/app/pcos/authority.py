"""
PCOS Authority & Fact Lineage Models — Re-export from canonical pcos_models.py

This module re-exports authority/lineage models from the authoritative pcos_models.py
to avoid dual class definitions on the same SQLAlchemy Base.
"""

from ..pcos_models import (
    PCOSAuthorityDocumentModel,
    PCOSExtractedFactModel,
    PCOSFactCitationModel,
)

__all__ = [
    "PCOSAuthorityDocumentModel",
    "PCOSExtractedFactModel",
    "PCOSFactCitationModel",
]
