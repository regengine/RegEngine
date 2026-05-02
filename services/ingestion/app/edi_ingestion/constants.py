from __future__ import annotations

from ..webhook_models import WebhookCTEType
from .transaction_sets import _SUPPORTED_TRANSACTION_SETS

_X12_UOM_MAP = {
    "CA": "cases",
    "CAS": "cases",
    "LB": "lbs",
    "LBR": "lbs",
    "KG": "kg",
    "EA": "each",
    "UN": "units",
    "PL": "pallets",
    "CTN": "cartons",
    "BOX": "boxes",
    "PC": "pieces",
    "PK": "pieces",
}

_FROM_ENTITY_CODES = {"SF", "SU", "SH"}
_TO_ENTITY_CODES = {"ST", "BT", "OB"}
_REQUIRED_856_SEGMENTS = {"ISA", "GS", "ST", "BSN", "HL", "SE", "GE", "IEA"}


_REQUIRED_850_SEGMENTS = {"ISA", "GS", "ST", "BEG", "SE", "GE", "IEA"}
_REQUIRED_810_SEGMENTS = {"ISA", "GS", "ST", "BIG", "SE", "GE", "IEA"}
_REQUIRED_861_SEGMENTS = {"ISA", "GS", "ST", "BRA", "SE", "GE", "IEA"}

_REQUIRED_SEGMENTS_BY_SET: dict[str, set[str]] = {
    "856": _REQUIRED_856_SEGMENTS,
    "850": _REQUIRED_850_SEGMENTS,
    "810": _REQUIRED_810_SEGMENTS,
    "861": _REQUIRED_861_SEGMENTS,
}

_CTE_TYPE_BY_SET: dict[str, WebhookCTEType] = {
    "856": WebhookCTEType.SHIPPING,
    "850": WebhookCTEType.SHIPPING,
    "810": WebhookCTEType.SHIPPING,
    "861": WebhookCTEType.RECEIVING,
}
