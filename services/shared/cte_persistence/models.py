# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DuplicateEventError(Exception):
    """Raised when a CTE event with the same sha256_hash already exists.

    ``fsma.cte_events`` is append-only (#1334). Any attempt to overwrite an
    existing event (same hash, different id) is a data-integrity violation.
    The duplicate is detected at the application layer before INSERT so that
    callers receive a meaningful exception rather than a DB-level error.

    The companion database trigger ``fsma.cte_events_no_update_delete`` raises
    an exception if an UPDATE or DELETE is attempted directly in SQL, providing
    a second enforcement layer that survives callers who bypass Python.
    """

    def __init__(self, event_id: str, sha256_hash: str):
        self.event_id = event_id
        self.sha256_hash = sha256_hash
        super().__init__(
            f"CTE event with sha256_hash={sha256_hash!r} already exists "
            f"(event_id={event_id!r}). fsma.cte_events is append-only (#1334)."
        )


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
    """Result of verifying a tenant's hash chain.

    The ``valid`` flag is True only when every per-chain integrity check
    passes AND the chain is consistent with the CTE event table:
      * no sequence gaps, chain linkage breaks, or hash tampering
      * no orphan chain rows (``hash_chain.cte_event_id`` that no longer
        joins to ``fsma.cte_events``)
      * no missing chain entries (non-rejected CTE events with no chain
        row — #1314 / #1307)

    Structured fields (added #1314) let callers surface specific break
    reasons without parsing ``errors`` strings:
      * ``orphan_chain_rows``: sequence numbers whose LEFT JOIN to
        ``fsma.cte_events`` returned NULL.
      * ``missing_chain_rows``: ``cte_events.id`` values that have no
        matching ``hash_chain`` row and are not rejected.
      * ``cte_events_count``: the non-rejected event count used in the
        consistency check; useful for diagnostics.
    """

    __slots__ = (
        "valid", "chain_length", "errors", "checked_at",
        "orphan_chain_rows", "missing_chain_rows", "cte_events_count",
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
