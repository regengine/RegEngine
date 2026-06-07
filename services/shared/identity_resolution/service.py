"""
Identity Resolution Service.

Provides a durable cross-record identity layer for entities, facilities,
products, and lots within the FSMA traceability system. Supports canonical
entity registration, alias management, fuzzy matching, merge/split
operations, and human review queues for ambiguous matches.

Database tables (V047):
    - fsma.canonical_entities
    - fsma.entity_aliases
    - fsma.entity_merge_history
    - fsma.identity_review_queue

This module composes :class:`IdentityResolutionService` from focused
sibling modules (a mechanical split of the original single-file
implementation — no logic changes):

    normalization.py — structured-identifier normalization (#1212)
    registration.py  — register_entity / add_alias / _insert_alias
    matching.py      — find_entity_by_alias / find_potential_matches / get_entity
    merging.py       — merge_entities / merge_entities_bulk / split_entity
    review.py        — queue_for_review / resolve_review / list_pending_reviews
    resolver.py      — auto_register_from_event / _resolve_or_register

Backward compatibility: this module re-exports the full original module
surface (``_normalize_identifier``, ``_STRUCTURED_IDENTIFIER_ALIAS_TYPES``,
the PII mask helpers, the validation constants, and ``logger``) so that
``from shared.identity_resolution.service import X`` keeps working for
every symbol the original 1987-line module exposed.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from shared.identity_resolution.constants import (  # noqa: F401
    VALID_ENTITY_TYPES,
    VALID_ALIAS_TYPES,
    VALID_REVIEW_STATUSES,
    AMBIGUOUS_THRESHOLD_LOW,
    AMBIGUOUS_THRESHOLD_HIGH,
)
from shared.identity_resolution.normalization import (  # noqa: F401
    _STRUCTURED_IDENTIFIER_ALIAS_TYPES,
    _normalize_identifier,
)
from shared.identity_resolution.matching import MatchingMixin
from shared.identity_resolution.merging import MergeMixin
from shared.identity_resolution.registration import RegistrationMixin
from shared.identity_resolution.resolver import ResolverMixin
from shared.identity_resolution.review import ReviewMixin
# #1233: PII masking helpers for log emission. Raw alias_value /
# canonical_name must never reach the log sinks — log retention is
# typically longer than DB retention and sinks are accessible to a
# wider personnel surface (SRE, observability vendors). Re-exported
# here for backward compatibility (the log call sites now live in
# registration.py and resolver.py, which import these directly).
from shared.pii import mask_alias_value, mask_name  # noqa: F401

logger = logging.getLogger("identity-resolution")


# ---------------------------------------------------------------------------
# Identity Resolution Service
# ---------------------------------------------------------------------------

class IdentityResolutionService(
    RegistrationMixin,
    MatchingMixin,
    MergeMixin,
    ReviewMixin,
    ResolverMixin,
):
    """
    Cross-record identity resolution for FSMA supply-chain entities.

    All methods are tenant-scoped. The caller must supply ``tenant_id``
    explicitly; this service never infers it.

    #1230 tenant lock: when constructed with ``principal_tenant_id``,
    every write method verifies that the caller-supplied ``tenant_id``
    matches the principal's tenant. This blocks cross-tenant writes
    even if a router bug — e.g. the pattern seen in #1106 where an
    ``X-Tenant-ID`` header is forwarded without cross-check — lets
    a mismatched tenant_id reach the service. Callers that legitimately
    need cross-tenant access (admin tooling, platform jobs) construct
    the service without ``principal_tenant_id`` OR set
    ``allow_cross_tenant=True`` on construction.
    """

    def __init__(
        self,
        session: Session,
        *,
        principal_tenant_id: Optional[str] = None,
        allow_cross_tenant: bool = False,
    ):
        self.session = session
        # Keyword-only to prevent positional-arg drift from accidentally
        # disabling the lock in a new call site.
        self._principal_tenant_id = principal_tenant_id
        self._allow_cross_tenant = allow_cross_tenant

    # ------------------------------------------------------------------
    # Tenant-access guard (#1230)
    # ------------------------------------------------------------------

    def _verify_tenant_access(self, tenant_id: str) -> None:
        """Raise PermissionError if the caller-supplied ``tenant_id``
        doesn't match the principal the service was constructed with.

        No-op when:
        - ``principal_tenant_id`` is None (backwards-compatible path
          for background jobs / ingestion consumers that run with a
          service account not bound to a tenant).
        - ``allow_cross_tenant=True`` (admin tooling explicitly
          opting out of the lock).

        The service cannot enforce the "is this user entitled to this
        tenant" question by itself — that's the router's job. But it
        CAN enforce that whatever tenant the router handed in matches
        the principal's tenant. That's defense-in-depth against
        router-level bugs like #1106.
        """
        if self._allow_cross_tenant:
            return
        if self._principal_tenant_id is None:
            return
        if not tenant_id:
            raise PermissionError(
                "identity_resolution: tenant_id is required"
            )
        if tenant_id != self._principal_tenant_id:
            logger.warning(
                "identity_tenant_mismatch principal=%s requested=%s",
                self._principal_tenant_id, tenant_id,
            )
            raise PermissionError(
                "identity_resolution: tenant_id does not match the "
                "authenticated principal's tenant. Cross-tenant writes "
                "require an explicit platform-admin grant; see #1230."
            )
