"""
Identity resolution constants and thresholds.

These values mirror DB CHECK constraints and control the
auto-merge vs human-review vs auto-create decision boundaries.
"""

# Valid enum values (mirrors DB CHECK constraints from V047)
VALID_ENTITY_TYPES = frozenset({
    "firm", "facility", "product", "lot", "trading_relationship",
})

VALID_ALIAS_TYPES = frozenset({
    "name", "gln", "gtin", "fda_registration", "internal_code",
    "duns",
    # TLC aliases (#1175):
    #   - "tlc":        verbatim Traceability Lot Code, the CANONICAL storage
    #                   form for FSMA 204 traceability. Must never be
    #                   truncated or normalized.
    #   - "tlc_prefix": the GTIN-14 prefix of a TLC, used strictly for
    #                   secondary fuzzy LOOKUP. Never the primary alias.
    "tlc", "tlc_prefix",
    "address_variant", "abbreviation", "trade_name",
})

VALID_REVIEW_STATUSES = frozenset({
    "confirmed_match", "confirmed_distinct", "deferred",
})

# Confidence thresholds for identity resolution decisions:
#   < LOW  → auto-create new entity
#   LOW-HIGH → queue for human review (ambiguous)
#   >= HIGH → auto-merge
AMBIGUOUS_THRESHOLD_LOW = 0.60
AMBIGUOUS_THRESHOLD_HIGH = 0.90
