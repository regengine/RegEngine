# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------


class CTERecord:
    """A persisted CTE event with all associated data."""

    __slots__ = (
        "id", "tenant_id", "event_type", "traceability_lot_code",
        "product_description", "quantity", "unit_of_measure",
        "location_gln", "location_name", "event_timestamp",
        "event_entry_timestamp",
        "source", "idempotency_key", "sha256_hash", "chain_hash",
        "validation_status", "ingested_at", "kdes", "alerts",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class ChainEntry:
    """A single entry in the hash chain ledger."""

    __slots__ = (
        "id", "tenant_id", "cte_event_id", "sequence_num",
        "event_hash", "previous_chain_hash", "chain_hash", "created_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class StoreResult:
    """Result of storing a CTE event."""

    __slots__ = (
        "success", "event_id", "sha256_hash", "chain_hash",
        "idempotent", "errors", "kde_completeness", "alerts",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class ChainVerification:
    """Result of verifying a tenant's hash chain."""

    __slots__ = (
        "valid", "chain_length", "errors", "checked_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class MerkleVerification:
    """Result of Merkle tree verification for a tenant's hash chain."""

    __slots__ = (
        "valid", "merkle_root", "chain_length", "tree_depth",
        "errors", "checked_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
