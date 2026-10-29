"""SEL-549 supplier shipping readiness (preflight only).

Maps a second shipping layout (EDI 856 ASN) into the same
``REQUIRED_KDES_BY_CTE[shipping]`` set the CSV partner path uses, scores
pass / gap / failure, and flags unknown columns or segments instead of
dropping them.

Synthetic fixtures only. No production ingest.
"""

from .shipping import (
    ALBERTSONS_BUYER_FIELDS,
    FlagRecord,
    ShippingReadinessResult,
    dry_run_shipping_csv,
    map_asn856_to_shipping_kdes,
    score_shipping_readiness,
)

__all__ = [
    "ALBERTSONS_BUYER_FIELDS",
    "FlagRecord",
    "ShippingReadinessResult",
    "dry_run_shipping_csv",
    "map_asn856_to_shipping_kdes",
    "score_shipping_readiness",
]
