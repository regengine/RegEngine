"""
Identity Resolution — re-exports from submodules.

Package layout:
    shared/identity_resolution/constants.py  — thresholds and valid enum values
    shared/identity_resolution/service.py    — IdentityResolutionService class
"""

from shared.identity_resolution.constants import (  # noqa: F401
    VALID_ENTITY_TYPES,
    VALID_ALIAS_TYPES,
    VALID_REVIEW_STATUSES,
    AMBIGUOUS_THRESHOLD_LOW,
    AMBIGUOUS_THRESHOLD_HIGH,
)

from shared.identity_resolution.service import IdentityResolutionService  # noqa: F401
