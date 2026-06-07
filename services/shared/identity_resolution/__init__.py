"""
Identity Resolution — re-exports from submodules.

Package layout:
    shared/identity_resolution/constants.py  — thresholds and valid enum values
    shared/identity_resolution/service.py    — IdentityResolutionService class
"""

from shared.identity_resolution.constants import (  # noqa: F401
    AMBIGUOUS_THRESHOLD_HIGH,
    AMBIGUOUS_THRESHOLD_LOW,
    VALID_ALIAS_TYPES,
    VALID_ENTITY_TYPES,
    VALID_REVIEW_STATUSES,
)
from shared.identity_resolution.service import IdentityResolutionService  # noqa: F401
