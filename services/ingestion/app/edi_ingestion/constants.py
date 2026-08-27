from __future__ import annotations

from ..webhook_models import WebhookCTEType
from .transaction_sets import _SUPPORTED_TRANSACTION_SETS

# X12 data element 355 (Unit or Basis for Measurement Code) is ID 2/2 —
# exactly two characters. #2978: this table used to be keyed on 3- and
# 4-character values (``CAS``, ``CTN``, ``BOX``, ``LBR``) which cannot be
# DE355 codes at all, while the real two-character codes for those same
# units were absent — so ``SN1**200*CT`` (200 cartons) missed the lookup,
# fell through to ``VALID_UNITS_OF_MEASURE``, and silently degraded to
# "units" on every transaction set of the unified /edi/document route.
#
# Targets are the FSMA vocabulary in ``webhook_models.VALID_UNITS_OF_MEASURE``.
# Note the deliberate divergence from ``csv_templates._UOM_ALIASES``, which
# maps free-text ``"ct"`` to ``count``: that table normalizes what a human
# typed into a spreadsheet column, where "ct" reads as a count. This table
# decodes a wire-format code element, where CT is Carton.
_X12_UOM_MAP = {
    "CA": "cases",
    "CS": "cases",
    "CT": "cartons",
    "BX": "boxes",
    "BG": "bags",
    "LB": "lbs",
    "KG": "kg",
    "EA": "each",
    "UN": "units",
    "PL": "pallets",
    # DE355 PK is Package, not Piece. The FSMA vocabulary has no
    # "packages" target, so this approximation is retained rather than
    # swapped for a different guess — see #2978.
    "PC": "pieces",
    "PK": "pieces",
}

# Codes that are NOT X12 DE355 but that partners are already sending on
# this route (UN/CEFACT Rec 20 style, plus common vendor abbreviations).
# Kept as an explicitly-labelled tolerance layer rather than deleted, so
# a partner who works today does not start getting 422s — but kept OUT of
# ``_X12_UOM_MAP`` so nothing here is mistaken for an element-355 value.
# ``KGM``/``LBR`` are the Rec 20 codes the EPCIS path in this repo already
# carries (see ``epcis_export``/EPCIS conformance fixtures).
_NON_X12_UOM_ALIASES = {
    "CAS": "cases",
    "CTN": "cartons",
    "BOX": "boxes",
    "LBR": "lbs",
    "KGM": "kg",
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

# Line-item segment carrying the quantity element for each supported set.
# #2974: used to tell "no quantity element was sent" apart from "a
# quantity element was sent but is zero/non-numeric", so the route can
# fail closed on the latter instead of re-synthesizing 1.0.
_QUANTITY_SEGMENT_BY_SET: dict[str, str] = {
    "856": "SN1",
    "850": "PO1",
    "810": "IT1",
    "861": "RCD",
}
