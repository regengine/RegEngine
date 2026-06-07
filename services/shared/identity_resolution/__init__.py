"""
Identity Resolution — re-exports from submodules.

Package layout:
    shared/identity_resolution/constants.py      — thresholds and valid enum values
    shared/identity_resolution/normalization.py  — structured-identifier normalization (#1212)
    shared/identity_resolution/registration.py   — register_entity / add_alias / _insert_alias
    shared/identity_resolution/matching.py       — exact + fuzzy lookup / get_entity
    shared/identity_resolution/merging.py        — merge_entities(_bulk) / split_entity
    shared/identity_resolution/review.py         — review queue management
    shared/identity_resolution/resolver.py       — auto_register_from_event / _resolve_or_register
    shared/identity_resolution/service.py        — composed IdentityResolutionService class
"""

from shared.identity_resolution.constants import (  # noqa: F401
    AMBIGUOUS_THRESHOLD_HIGH,
    AMBIGUOUS_THRESHOLD_LOW,
    VALID_ALIAS_TYPES,
    VALID_ENTITY_TYPES,
    VALID_REVIEW_STATUSES,
)
from shared.identity_resolution.service import IdentityResolutionService  # noqa: F401
