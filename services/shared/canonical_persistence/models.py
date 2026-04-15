"""
Canonical persistence result models.
"""

from shared.cte_persistence import StoreResult


class CanonicalStoreResult:
    """Result of persisting a canonical event."""

    __slots__ = (
        "success", "event_id", "sha256_hash", "chain_hash",
        "idempotent", "errors", "legacy_event_id",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_legacy_result(self) -> StoreResult:
        """Convert to legacy StoreResult for backward compatibility."""
        return StoreResult(
            success=self.success,
            event_id=self.event_id,
            sha256_hash=self.sha256_hash,
            chain_hash=self.chain_hash,
            idempotent=self.idempotent,
            errors=self.errors or [],
            kde_completeness=1.0,
            alerts=[],
        )
